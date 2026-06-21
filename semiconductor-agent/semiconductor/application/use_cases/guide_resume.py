"""공채 공고 ↔ 이력서 정렬 가이드 유스케이스."""
from __future__ import annotations

from semiconductor.domain.entities import JobPosting, ResumeGuidance, ResumeProfile
from semiconductor.domain.ports import IResumeAdvisorLLM


class GuideResumeUseCase:
    def __init__(self, advisor: IResumeAdvisorLLM) -> None:
        self._advisor = advisor

    def execute(self, posting: JobPosting, resume: ResumeProfile) -> ResumeGuidance:
        try:
            return self._advisor.guide(posting, resume)
        except Exception:
            # graceful degradation — 가이드 실패해도 세션은 살아있게
            return ResumeGuidance(
                match_score=0,
                alignment_items=[],
                summary="이력서 가이드 중 오류가 발생했습니다. 다시 시도해주세요.",
                priority_actions=["잠시 후 다시 시도해주세요."],
                rewrite_suggestions=[],
            )
