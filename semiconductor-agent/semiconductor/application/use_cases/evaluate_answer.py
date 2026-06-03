import logging
from typing import Optional

from semiconductor.domain.entities import EvaluationResult, Question
from semiconductor.domain.ports import ILLMCritic, ILLMJudge

logger = logging.getLogger(__name__)


class EvaluateAnswerUseCase:
    def __init__(
        self,
        llm_judge: ILLMJudge,
        llm_critic: Optional[ILLMCritic] = None,
    ) -> None:
        self._judge = llm_judge
        self._critic = llm_critic

    def execute(self, question: Question, user_answer: str) -> EvaluationResult:
        try:
            initial = self._judge.evaluate(question=question, user_answer=user_answer)
        except Exception:
            # graceful degradation — 런타임 사용자에겐 안내 메시지.
            # 단 무음 실패 금지: 진짜 원인을 로깅해 골든셋·디버깅에서 보이게 한다.
            logger.exception("judge.evaluate 실패 (domain=%s)", question.domain)
            return EvaluationResult(
                accuracy_score=0,
                depth_score=0,
                terminology_score=0,
                total_score=0,
                feedback="평가 처리 중 오류가 발생했습니다. 다시 시도해주세요.",
                strong_points=[],
                weak_points=["평가를 다시 시도해주세요."],
                question=question.question,
            )

        if self._critic is None:
            return initial

        try:
            return self._critic.critique(
                question=question, user_answer=user_answer, initial_evaluation=initial
            )
        except Exception:
            # critic 실패 시 graceful degradation — 원본 평가 보존. 원인은 로깅.
            logger.exception("critic.critique 실패 (domain=%s)", question.domain)
            return initial
