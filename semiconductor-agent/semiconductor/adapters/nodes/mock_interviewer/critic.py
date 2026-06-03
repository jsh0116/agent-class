"""Phase 2b — Self-Critique 검증 + 출력 생성 + 다음 질문 진행."""
from __future__ import annotations

from langchain_core.messages import HumanMessage

from semiconductor.adapters.nodes.mock_interviewer.serialization import (
    deserialize_eval,
    serialize_eval,
)
from semiconductor.adapters.state import InterviewState
from semiconductor.application.use_cases.adaptive_critic import (
    CriticSkipConfig,
    apply_adaptive_critic,
)
from semiconductor.domain.entities import Question
from semiconductor.infrastructure.llm import LangChainLLMService


def _default_critic():
    # 모듈 글로벌 지연 조회 — patch 호환 + composition root 주입 지점.
    return LangChainLLMService.critic()


def make_mock_critic_node(critic_factory=_default_critic):
    """2차 검증 노드를 critic factory에 바인딩해 생성 (composition root용)."""

    def mock_critic_node(state: InterviewState) -> dict:
        """2차 검증 (조건부) + 결과 출력 + 다음 질문 준비.

        Adaptive critic skip:
          total >= CRITIC_SKIP_HIGH (기본 85) 또는 <= CRITIC_SKIP_LOW (기본 30) → critic 생략
          LLM_DISABLE_CRITIC_SKIP=1 설정 시 항상 호출 (디버깅·일관성용)
        """
        pending = state.get("pending_evaluation")
        if pending is None:
            return {"display_output": "❌ 평가 데이터가 없습니다."}

        initial = deserialize_eval(pending)

        # adaptive critic skip 판정은 application 레이어와 공유 (단일 소스).
        # eval 골든셋도 동일 로직을 써서 "사용자가 보는 점수"와 검증 점수가 일치한다.
        q = Question(
            domain=state["current_question_domain"],
            question=state["current_question_text"],
            key_points=state.get("current_question_key_points") or [],
        )
        human_msgs = [m for m in state.get("messages", []) if isinstance(m, HumanMessage)]
        user_answer = human_msgs[-1].content if human_msgs else ""
        final = apply_adaptive_critic(
            initial,
            question=q,
            user_answer=user_answer,
            critic_factory=critic_factory,
            config=CriticSkipConfig.from_env(),
        )

        new_asked = state["asked_count"] + 1
        remaining = state["max_questions"] - new_asked

        domain_label = state.get("current_question_domain") or ""
        header = f"📊 평가 결과 [{final.grade}] {final.total_score}/100점"
        if domain_label:
            header = f"🎓 [{domain_label} 전문가 평가] " + header

        output = (
            f"{header}\n\n"
            f"  정확성 {final.accuracy_score}/40 | 깊이 {final.depth_score}/30 | 전문용어 {final.terminology_score}/30\n\n"
            f"💬 {final.feedback}\n\n"
            f"✅ 잘한 점: {', '.join(final.strong_points) or '없음'}\n"
            f"📌 보완점:  {', '.join(final.weak_points) or '없음'}\n"
        )

        if final.specialist_commentary:
            output += f"\n🔬 전문가 코멘트:\n{final.specialist_commentary}\n"
        if final.model_answer:
            output += f"\n📚 모범답안:\n{final.model_answer}\n"
        if final.follow_up_question:
            output += f"\n💡 심화 질문 (선택): {final.follow_up_question}\n"

        enrichment = state.get("web_enrichment")
        if enrichment:
            output += f"\n🌐 산업 최신 동향 (병렬 검색):\n{enrichment[:600]}\n"

        if remaining > 0:
            output += f"\n남은 문제: {remaining}개 | 계속하려면 답변을 입력하세요."
        else:
            output += "\n\n🎉 모든 문제를 완료했습니다! /진단 으로 이해도 진단을 받아보세요."

        return {
            "evaluations": state.get("evaluations", []) + [serialize_eval(final, domain=q.domain)],
            "asked_count": new_asked,
            "current_question_text": None,
            "current_question_domain": None,
            "current_question_key_points": [],
            "pending_evaluation": None,
            "web_enrichment": None,
            "interview_phase": "present",
            "display_output": output,
            "mode": "idle" if remaining <= 0 else "interview",
        }

    return mock_critic_node


mock_critic_node = make_mock_critic_node()
