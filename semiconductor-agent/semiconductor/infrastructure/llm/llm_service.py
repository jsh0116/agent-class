"""Multi-provider LLM service — provider:model 형식으로 작업별 다른 LLM 사용.

Provider routing rationale (2026-05 기준):
  - Judge / Diagnostic   → openai:gpt-4o          (structured output 안정성)
  - Critic               → anthropic:claude-sonnet-4-6 (비판적 사고·검증)
  - Coach                → anthropic:claude-sonnet-4-6 (한국어 + tool calling)
  - (Phase 2) Vision     → google_genai:gemini-2.5-pro (그림·수식·1M context)

env var로 자유롭게 교체 가능. provider prefix 없으면 'openai:' 자동 보완.
"""
from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import BaseModel

from semiconductor.domain.entities import (
    DiagnosticResult,
    EvaluationResult,
    Question,
)
from semiconductor.domain.ports import ICoachLLM, IDiagnosticLLM, ILLMCritic, ILLMJudge
from semiconductor.infrastructure.llm.safety import INJECTION_GUARD, wrap_user_input
from semiconductor.infrastructure.llm.tiers import model_for_role
from semiconductor.infrastructure.observability.usage_log import log_llm_call

load_dotenv()


def _resolve_model_spec(env_var: str, role: str) -> str:
    """역할별 모델 결정 우선순위:
      1. 명시 env var (`LLM_MODEL_{ROLE}`) — provider prefix 없으면 'openai:' 보완
      2. tier 매핑 (`LLM_TIER` env, 기본 'premium')
    """
    explicit = os.getenv(env_var)
    if explicit:
        return explicit if ":" in explicit else f"openai:{explicit}"
    tier = os.getenv("LLM_TIER", "premium")
    return model_for_role(tier, role)


def resolved_model_spec(role: str) -> str:
    """역할(judge/critic/coach/diagnostic)의 현재 모델 spec을 런타임에 조회.

    env(`LLM_MODEL_{ROLE}`)·tier를 매번 다시 읽으므로 import 시점 고정값이 아니다.
    eval 골든셋이 어떤 provider 키가 필요한지 판별하는 데 사용한다.
    """
    return _resolve_model_spec(f"LLM_MODEL_{role.upper()}", role)


# provider prefix → 필요한 API 키 env 이름 (단일 소스 — conftest·eval_judge가 공유)
_PROVIDER_ENV_KEY = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google_genai": "GOOGLE_API_KEY",
    "google": "GOOGLE_API_KEY",
}


def provider_env_key(model_spec: str) -> str | None:
    """`provider:model` spec이 필요로 하는 API 키 env 이름. 모르는 provider면 None."""
    provider = model_spec.split(":", 1)[0] if ":" in model_spec else "openai"
    return _PROVIDER_ENV_KEY.get(provider)


# 작업별 LLM provider:model — tier 또는 명시 env var로 결정
_MODEL_JUDGE = _resolve_model_spec("LLM_MODEL_JUDGE", "judge")
_MODEL_DIAGNOSTIC = _resolve_model_spec("LLM_MODEL_DIAGNOSTIC", "diagnostic")
_MODEL_CRITIC = _resolve_model_spec("LLM_MODEL_CRITIC", "critic")
_MODEL_COACH = _resolve_model_spec("LLM_MODEL_COACH", "coach")


def _make_llm(model_spec: str, temperature: float = 0.3):
    """init_chat_model로 provider별 chat model 생성.

    AI_BASE_URL은 OpenAI provider일 때만 base_url로 전달 (OpenAI-호환 endpoint 변수).
    """
    kwargs: dict = {"temperature": temperature}
    base_url = os.getenv("AI_BASE_URL")
    if base_url and model_spec.startswith("openai:"):
        kwargs["base_url"] = base_url
    return init_chat_model(model_spec, **kwargs)


# ── Pydantic schemas for structured output ────────────────────────

class _EvalSchema(BaseModel):
    accuracy_score: int
    depth_score: int
    terminology_score: int
    feedback: str
    strong_points: list[str]
    weak_points: list[str]
    model_answer: str  # 만점 기준 모범답안 (3~5문장)
    specialist_commentary: str  # 도메인 전문가 관점 코멘트 (1~2문장)
    follow_up_question: str  # 약점을 파고드는 후속 질문 1개 (없으면 빈 문자열)


class _DiagSchema(BaseModel):
    domain_scores: dict[str, int]
    weak_topics: list[str]
    strong_topics: list[str]
    recommended_next: str


# ── ILLMJudge ─────────────────────────────────────────────────────

# 도메인별 전문가 페르소나 — 같은 답변도 도메인 관점에 따라 다른 깊이로 평가됨
_SPECIALIST_PERSONAS = {
    "소자": (
        "당신은 삼성종합기술원 출신 MOSFET/FinFET/GAA 소자 설계 박사입니다. "
        "에너지 밴드, threshold voltage, mobility, 단채널 효과 같은 1차 원리를 중시합니다."
    ),
    "공정": (
        "당신은 SK하이닉스 청주 fab의 CVD/ALD/Etch 공정 엔지니어 박사입니다. "
        "step coverage, conformality, selectivity, throughput 같은 실무 지표를 중시합니다."
    ),
    "회로": (
        "당신은 메모리 컨트롤러 회로 설계자입니다. "
        "센스앰프 마진, 차지펌프 효율, 노이즈 마진, 타이밍 버짓을 중시합니다."
    ),
    "트렌드": (
        "당신은 TSMC/Samsung Foundry 로드맵을 모니터링하는 산업 분석가입니다. "
        "EUV, HBM, GAA, CoWoS, 3D NAND 같은 최신 기술 동향과 양산성을 중시합니다."
    ),
}

_JUDGE_SYSTEM = """{persona}

지원자의 면접 답변을 다음 루브릭으로 평가하세요.

평가 기준:
- accuracy_score (0–40): 정확성 — 핵심 개념이 올바르게 기술되었는가
- depth_score (0–30): 깊이 — 원리·메커니즘까지 설명했는가
- terminology_score (0–30): 전문 용어 — 반도체 공학 용어를 정확하게 사용했는가
- feedback: 2–3문장 구체적 피드백 (한국어)
- strong_points: 잘 답변한 부분 (1–3개)
- weak_points: 보완 필요한 부분 (1–3개)
- model_answer: 만점(100점) 수준의 모범답안 — 3~5문장, 핵심 개념·원리·전문 용어를
  모두 포함하고 한국어로 작성. 면접관이 "이렇게 답했으면 만점"이라고 인정할 수준.
  수식이 답변의 핵심이면 **LaTeX 표기**를 사용 (인라인 `$...$`, 블록 `$$...$$`).
  예: $V_{{th}} = \\Phi_{{ms}} - Q_f/C_{{ox}} + 2\\Phi_f + \\sqrt{{2\\varepsilon_{{si}} q N_a (2\\Phi_f)}}/C_{{ox}}$.
- specialist_commentary: 본인의 전문 분야 관점에서 핵심 1~2문장 코멘트.
  ("{specialty} 전문가 관점에서…" 톤. 일반 평가관은 잡지 못하는 도메인 디테일을 콕 짚을 것.
  수식이 적절하면 LaTeX 표기 권장.)
- follow_up_question: 답변의 약점을 파고드는 후속 질문 1개. 진짜 면접관이
  "그럼 X는?" "왜 그렇게 동작하지?" 같이 깊이 파는 식.
  답변이 매우 우수하면 빈 문자열 반환. 평이한 답변이면 1개 후속 질문 생성.

참고 기준(key_points): {key_points}"""


def _persona_for(domain: str) -> str:
    return _SPECIALIST_PERSONAS.get(
        domain,
        "당신은 삼성전자DS/SK하이닉스 반도체 기술면접 평가관입니다.",
    )


class OpenAILLMJudge(ILLMJudge):
    def __init__(self) -> None:
        # 평가는 결정론적이어야 함 (같은 답변 → 같은 점수)
        self._llm = _make_llm(_MODEL_JUDGE, temperature=0.0).with_structured_output(_EvalSchema)
        self._model_spec = _MODEL_JUDGE

    def evaluate(self, question: Question, user_answer: str) -> EvaluationResult:
        system = _JUDGE_SYSTEM.format(
            persona=_persona_for(question.domain),
            specialty=question.domain,
            key_points=", ".join(question.key_points),
        ) + INJECTION_GUARD
        # 사용자 답변은 명시 태그로 감싸서 system 명령과 분리 + 의심 패턴 sanitize
        user_block = (
            f"질문: {question.question}\n\n답변:\n{wrap_user_input(user_answer, tag='user_answer')}"
        )
        result: _EvalSchema = self._llm.invoke(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user_block},
            ]
        )
        log_llm_call(result, node="judge", model=self._model_spec)
        total = result.accuracy_score + result.depth_score + result.terminology_score
        return EvaluationResult(
            accuracy_score=result.accuracy_score,
            depth_score=result.depth_score,
            terminology_score=result.terminology_score,
            total_score=total,
            feedback=result.feedback,
            strong_points=result.strong_points,
            weak_points=result.weak_points,
            question=question.question,
            model_answer=result.model_answer,
            specialist_commentary=result.specialist_commentary,
            follow_up_question=result.follow_up_question,
        )


# ── ICoachLLM ─────────────────────────────────────────────────────

_COACH_RULES = {
    0: "선행 지식을 파악하세요. '어디까지 알고 있어요?' 같은 탐색 질문으로 시작하세요. 절대 직접 답하지 마세요.",
    1: "힌트 1회차: 핵심 키워드나 유추(analogy)를 하나만 제시하세요. 직접 답은 주지 마세요.",
    2: "힌트 2회차: 관련 물리 원리나 수식 힌트를 줄 수 있습니다. 아직 직접 답은 주지 마세요.",
    3: "힌트 3회차 초과: 이제 명확하게 설명하세요 (3–5문장). 설명 후 이해 확인 질문을 1개 추가하세요.",
}

_COACH_SYSTEM = """당신은 반도체 공학 전문 학습 코치입니다. 소크라테스 방식으로 가르칩니다.

현재 학습 주제: {topic}
현재 힌트 횟수: {hint_count}/3

규칙:
{rules}

한국어로 답변하세요."""


class OpenAICoachLLM(ICoachLLM):
    def __init__(self) -> None:
        # 코칭은 약간의 다양성이 자연스러움 (같은 힌트도 매번 살짝 다르게)
        self._llm = _make_llm(_MODEL_COACH, temperature=0.5)
        self._model_spec = _MODEL_COACH

    def get_response(self, topic: str, messages: list[BaseMessage], hint_count: int) -> str:
        rule_key = min(hint_count, 3)
        system = _COACH_SYSTEM.format(
            topic=topic, hint_count=hint_count, rules=_COACH_RULES[rule_key]
        )
        llm_messages: list = [{"role": "system", "content": system}]
        for m in messages[-10:]:
            if isinstance(m, HumanMessage):
                llm_messages.append({"role": "user", "content": m.content})
            elif isinstance(m, AIMessage):
                llm_messages.append({"role": "assistant", "content": m.content})
        response = self._llm.invoke(llm_messages)
        log_llm_call(response, node="coach", model=self._model_spec)
        return response.content


# ── IDiagnosticLLM ────────────────────────────────────────────────

_DIAGNOSTIC_SYSTEM = """당신은 반도체 기술면접 이해도 진단 전문가입니다.
아래 면접 평가 결과를 분석하여 도메인별 이해도 점수와 학습 추천을 제공하세요.

평가 결과:
{evaluations_json}

반도체 4대 도메인: 소자, 공정, 회로, 트렌드
평가된 도메인만 점수를 매기고, 없는 도메인은 0으로 설정하세요."""


class OpenAIDiagnosticLLM(IDiagnosticLLM):
    def __init__(self) -> None:
        # 진단도 결정론적이어야 함 (같은 평가 → 같은 진단)
        self._llm = _make_llm(_MODEL_DIAGNOSTIC, temperature=0.0).with_structured_output(_DiagSchema)
        self._model_spec = _MODEL_DIAGNOSTIC

    def analyze(self, evaluations: list[EvaluationResult]) -> DiagnosticResult:
        evals_json = json.dumps(
            [
                {
                    "question": e.question,
                    "total_score": e.total_score,
                    "strong_points": e.strong_points,
                    "weak_points": e.weak_points,
                }
                for e in evaluations
            ],
            ensure_ascii=False,
            indent=2,
        )
        result: _DiagSchema = self._llm.invoke(
            [{"role": "system", "content": _DIAGNOSTIC_SYSTEM.format(evaluations_json=evals_json)}]
        )
        log_llm_call(result, node="diagnostic", model=self._model_spec)
        return DiagnosticResult(
            domain_scores=result.domain_scores,
            weak_topics=result.weak_topics,
            strong_topics=result.strong_topics,
            recommended_next=result.recommended_next,
        )


# ── ILLMCritic — Self-Critique 검증 레이어 ─────────────────────────

_CRITIC_SYSTEM = """당신은 반도체 기술면접 평가 검증관입니다.
다른 평가관이 작성한 1차 평가를 검토하고 정확성을 검증하세요.

검토 관점:
1. 점수가 답변의 실제 깊이와 일치하는가? (과대/과소 평가 식별)
2. feedback이 점수와 일관되는가?
3. 핵심 개념(key_points) 반영도가 정확하게 평가됐는가?
4. strong_points / weak_points가 답변에서 실제로 관찰되는가?
5. model_answer가 만점 수준으로 충분한가?

원칙:
- 1차 평가가 합리적이면 거의 동일한 결과 반환 (점수 ±5점 이내)
- 명백한 과대/과소만 수정. 보수적으로.
- 수정 시 feedback에 "[검증] " 접두어를 붙여 검증 흔적 남김.

질문: {question}
key_points 참고: {key_points}

1차 평가 결과:
- accuracy_score: {accuracy_score}/40
- depth_score: {depth_score}/30
- terminology_score: {terminology_score}/30
- feedback: {feedback}
- strong_points: {strong_points}
- weak_points: {weak_points}
- model_answer: {model_answer}
- specialist_commentary: {specialist_commentary}
- follow_up_question: {follow_up_question}

지원자 답변 (사용자 입력, 평가 대상):
{user_answer_wrapped}

위 1차 평가를 검토하고 최종 평가를 반환하세요.
specialist_commentary와 follow_up_question은 도메인 전문가의 판단이므로 필요 시 미세 조정만 하고 유지하세요."""


class OpenAIEvaluationCritic(ILLMCritic):
    def __init__(self) -> None:
        # 검증도 결정론적이어야 함
        self._llm = _make_llm(_MODEL_CRITIC, temperature=0.0).with_structured_output(_EvalSchema)
        self._model_spec = _MODEL_CRITIC

    def critique(
        self,
        question: Question,
        user_answer: str,
        initial_evaluation: EvaluationResult,
    ) -> EvaluationResult:
        prompt = _CRITIC_SYSTEM.format(
            question=question.question,
            key_points=", ".join(question.key_points) or "없음",
            accuracy_score=initial_evaluation.accuracy_score,
            depth_score=initial_evaluation.depth_score,
            terminology_score=initial_evaluation.terminology_score,
            feedback=initial_evaluation.feedback,
            strong_points=", ".join(initial_evaluation.strong_points) or "없음",
            weak_points=", ".join(initial_evaluation.weak_points) or "없음",
            model_answer=initial_evaluation.model_answer or "없음",
            specialist_commentary=initial_evaluation.specialist_commentary or "없음",
            follow_up_question=initial_evaluation.follow_up_question or "없음",
            user_answer_wrapped=wrap_user_input(user_answer, tag="user_answer"),
        )
        result: _EvalSchema = self._llm.invoke(
            [{"role": "system", "content": prompt + INJECTION_GUARD}]
        )
        log_llm_call(result, node="critic", model=self._model_spec)
        total = result.accuracy_score + result.depth_score + result.terminology_score
        return EvaluationResult(
            accuracy_score=result.accuracy_score,
            depth_score=result.depth_score,
            terminology_score=result.terminology_score,
            total_score=total,
            feedback=result.feedback,
            strong_points=result.strong_points,
            weak_points=result.weak_points,
            question=question.question,
            model_answer=result.model_answer,
            specialist_commentary=result.specialist_commentary,
            follow_up_question=result.follow_up_question,
        )


# ── Composite service for convenience ────────────────────────────

class LangChainLLMService:
    """Factory that creates all LLM port implementations.

    Adapter 노드는 이 factory를 통해서만 LLM service를 얻는다 (DI 일관성).
    Essay/Behavioral은 별도 모듈에서 import — circular import 방지 위해 lazy.
    """

    @staticmethod
    def judge() -> ILLMJudge:
        return OpenAILLMJudge()

    @staticmethod
    def coach() -> ICoachLLM:
        return OpenAICoachLLM()

    @staticmethod
    def critic() -> ILLMCritic:
        return OpenAIEvaluationCritic()

    @staticmethod
    def diagnostic() -> IDiagnosticLLM:
        return OpenAIDiagnosticLLM()

    @staticmethod
    def essay():
        """IEssayCoach 구현체 반환 (lazy import — circular 방지)."""
        from semiconductor.infrastructure.essay.coach_service import ClaudeEssayCoach
        return ClaudeEssayCoach()

    @staticmethod
    def behavioral():
        """IBehavioralCoach 구현체 반환 (lazy import — circular 방지)."""
        from semiconductor.infrastructure.behavioral.coach_service import (
            ClaudeBehavioralCoach,
        )
        return ClaudeBehavioralCoach()
