"""Phase 2a — 1차 평가 (Judge only). Critic은 다음 노드에서."""
from __future__ import annotations

from langchain_core.messages import HumanMessage

from semiconductor.adapters.nodes.mock_interviewer.serialization import serialize_eval
from semiconductor.adapters.state import InterviewState
from semiconductor.application.use_cases.evaluate_answer import EvaluateAnswerUseCase
from semiconductor.domain.entities import Question
from semiconductor.infrastructure.llm import LangChainLLMService


def _default_judge():
    # 모듈 글로벌 지연 조회 — patch 호환 + composition root 주입 지점.
    return LangChainLLMService.judge()


def make_mock_evaluate_node(judge_factory=_default_judge):
    """1차 평가 노드를 judge factory에 바인딩해 생성 (composition root용)."""

    def mock_evaluate_node(state: InterviewState) -> dict:
        """1차 평가: 도메인 전문가 페르소나로 judge가 답변 평가."""
        eval_uc = EvaluateAnswerUseCase(llm_judge=judge_factory())

        human_msgs = [m for m in state.get("messages", []) if isinstance(m, HumanMessage)]
        user_answer = human_msgs[-1].content if human_msgs else ""

        q = Question(
            domain=state["current_question_domain"],
            question=state["current_question_text"],
            key_points=state.get("current_question_key_points") or [],
        )

        result = eval_uc.execute(question=q, user_answer=user_answer)

        return {
            "pending_evaluation": serialize_eval(result, domain=q.domain),
        }

    return mock_evaluate_node


mock_evaluate_node = make_mock_evaluate_node()
