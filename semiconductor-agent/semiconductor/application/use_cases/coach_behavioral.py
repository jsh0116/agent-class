"""인성면접 STAR 평가 유스케이스."""
from __future__ import annotations

import logging

from semiconductor.domain.entities import BehavioralEvaluation, BehavioralQuestion
from semiconductor.domain.ports import IBehavioralCoach

logger = logging.getLogger(__name__)


class CoachBehavioralUseCase:
    def __init__(self, coach: IBehavioralCoach) -> None:
        self._coach = coach

    def execute(
        self,
        question: BehavioralQuestion,
        user_answer: str,
    ) -> BehavioralEvaluation:
        try:
            return self._coach.evaluate_behavioral(question, user_answer)
        except Exception:
            logger.exception("behavioral_coach 실패 (competency=%s)", question.competency)
            return BehavioralEvaluation(
                situation_score=0, task_score=0, action_score=0,
                result_score=0, culture_fit=0, total_score=0,
                feedback="평가 중 오류가 발생했습니다. 다시 시도해주세요.",
                strong_points=[], weak_points=["평가 재시도 필요"],
                improved_answer="",
            )
