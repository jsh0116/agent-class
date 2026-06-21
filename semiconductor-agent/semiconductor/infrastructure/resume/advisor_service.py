"""Claude 기반 이력서 가이드 — 공고 ↔ 이력서 갭 분석.

한국어 이해·작문 비중이 크고 자소서/인성과 동일하게 coach tier(Claude)를 재사용한다.
공고·이력서 모두 사용자 제공 텍스트이므로 prompt-injection 가드로 격리한다.
"""
from __future__ import annotations

import os

from langchain.chat_models import init_chat_model
from pydantic import BaseModel

from semiconductor.domain.entities import (
    AlignmentItem,
    JobPosting,
    ResumeGuidance,
    ResumeProfile,
)
from semiconductor.domain.ports import IResumeAdvisorLLM
from semiconductor.infrastructure.llm.safety import INJECTION_GUARD, wrap_user_input
from semiconductor.infrastructure.llm.tiers import model_for_role
from semiconductor.infrastructure.observability.usage_log import log_llm_call


class _AlignmentSchema(BaseModel):
    requirement: str
    status: str       # 충족 | 부분충족 | 누락
    evidence: str
    action: str
    priority: str     # 필수 | 우대


class _GuidanceSchema(BaseModel):
    match_score: int  # 0-100 공고 부합도
    alignment_items: list[_AlignmentSchema]
    summary: str
    priority_actions: list[str]
    rewrite_suggestions: list[str]


_COMPANY_PERSONA = {
    "samsung_ds": (
        "당신은 삼성전자 DS부문(메모리·파운드리·시스템LSI) 채용 담당 엔지니어입니다. "
        "공정·소자 심화, 1차 원리 이해, 미세화 스케일링 역량을 중시합니다."
    ),
    "sk_hynix": (
        "당신은 SK하이닉스(DRAM·HBM·패키징) 채용 담당 엔지니어입니다. "
        "메모리 신뢰성·대역폭, 패키징(TSV·하이브리드 본딩), AI 메모리 역량을 중시합니다."
    ),
}

_SYSTEM = """{persona}

신입 공채 **공고**와 지원자의 **이력서**를 비교해, 이력서가 공고에 얼마나 부합하는지
갭을 분석하고 현실적인 보완 가이드를 제시하세요. 한국어로 작성합니다.

분석 절차:
1. 공고에서 자격요건(필수)·우대사항·요구 기술/전공/역량을 추출한다.
2. 각 요건마다 이력서의 근거를 찾아 status를 판정한다:
   - 충족: 이력서에 명확한 근거가 있음
   - 부분충족: 관련은 있으나 약하거나 간접적
   - 누락: 근거를 찾을 수 없음
3. match_score(0-100)는 **필수 요건 충족 비중**을 중심으로 산정한다.

출력 필드:
- match_score: 0-100 정수
- alignment_items: 요건별 분석 리스트. 각 항목:
    requirement(공고 요건), status(충족|부분충족|누락),
    evidence(이력서 근거, 없으면 빈 문자열),
    action(보완 액션 — 누락/부분충족일 때 구체적으로),
    priority(필수|우대)
- summary: 2~3문장 종합 진단
- priority_actions: 우선순위 높은 보완 액션 3~5개 (필수 누락 우선)
- rewrite_suggestions: 이미 가진 경험을 공고 표현에 맞춰 더 잘 드러내는 이력서 문구 제안 2~4개

원칙:
- 사실을 지어내지 않는다. 이력서에 없는 경험을 "있다고 쓰라"고 하지 말고,
  "이렇게 채우면 된다"는 현실적 액션(수강·프로젝트·자격증)으로 안내한다.
- 과장·허위를 권하지 않는다. 지원자가 실제로 한 것을 더 잘 보이게 돕는다."""


def _resolve_resume_model() -> str:
    explicit = os.getenv("LLM_MODEL_RESUME")
    if explicit:
        return explicit if ":" in explicit else f"openai:{explicit}"
    tier = os.getenv("LLM_TIER", "premium")
    return model_for_role(tier, "coach")


def _coerce_status(value: str) -> str:
    v = (value or "").strip()
    if v in ("충족", "부분충족", "누락"):
        return v
    return "부분충족"  # 모호하면 중립값으로 (검증 예외 대신 방어적 매핑)


def _coerce_priority(value: str) -> str:
    return "우대" if (value or "").strip() == "우대" else "필수"


class ClaudeResumeAdvisor(IResumeAdvisorLLM):
    def __init__(self) -> None:
        model = _resolve_resume_model()
        kwargs: dict = {"temperature": 0.2}
        base_url = os.getenv("AI_BASE_URL")
        if base_url and model.startswith("openai:"):
            kwargs["base_url"] = base_url
        self._llm = init_chat_model(model, **kwargs).with_structured_output(_GuidanceSchema)
        self._model_spec = model

    def guide(self, posting: JobPosting, resume: ResumeProfile) -> ResumeGuidance:
        persona = _COMPANY_PERSONA.get(
            posting.company, "당신은 반도체 기업 채용 담당 엔지니어입니다."
        )
        system = _SYSTEM.format(persona=persona) + INJECTION_GUARD
        user_block = (
            f"[공채 공고]\n{wrap_user_input(posting.raw_text, tag='user_input')}\n\n"
            f"[지원자 이력서]\n{wrap_user_input(resume.raw_text, tag='user_input')}"
        )
        result: _GuidanceSchema = self._llm.invoke([
            {"role": "system", "content": system},
            {"role": "user", "content": user_block},
        ])
        log_llm_call(result, node="resume", model=self._model_spec)

        items = [
            AlignmentItem(
                requirement=it.requirement,
                status=_coerce_status(it.status),
                evidence=it.evidence,
                action=it.action,
                priority=_coerce_priority(it.priority),
            )
            for it in result.alignment_items
            if it.requirement.strip()
        ]
        score = max(0, min(100, result.match_score))
        return ResumeGuidance(
            match_score=score,
            alignment_items=items,
            summary=result.summary,
            priority_actions=result.priority_actions,
            rewrite_suggestions=result.rewrite_suggestions,
        )
