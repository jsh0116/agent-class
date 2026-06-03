"""Self-Critique 검증 use case — graph node에서 호출하기 위해 분리."""
import logging

from semiconductor.domain.entities import EvaluationResult, Question
from semiconductor.domain.ports import ILLMCritic

logger = logging.getLogger(__name__)


class CritiqueEvaluationUseCase:
    """1차 평가(Judge 결과)를 검증·수정하는 2-pass 추론.

    실패 시 원본 평가를 그대로 반환 (graceful degradation).
    """

    def __init__(self, llm_critic: ILLMCritic) -> None:
        self._critic = llm_critic

    def execute(
        self,
        question: Question,
        user_answer: str,
        initial_evaluation: EvaluationResult,
    ) -> EvaluationResult:
        try:
            return self._critic.critique(
                question=question,
                user_answer=user_answer,
                initial_evaluation=initial_evaluation,
            )
        except Exception:
            # 원본 보존하되 무음 실패 금지 — provider/schema 버그가 보이게 로깅.
            logger.exception("critic.critique 실패 (domain=%s)", question.domain)
            return initial_evaluation
