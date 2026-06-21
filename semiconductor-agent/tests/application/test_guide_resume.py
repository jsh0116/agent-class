"""TDD: 이력서 가이드 유스케이스 — 포트 mock, 비즈니스 로직 검증."""
from unittest.mock import MagicMock

from semiconductor.application.use_cases.guide_resume import GuideResumeUseCase
from semiconductor.domain.entities import (
    AlignmentItem,
    JobPosting,
    ResumeGuidance,
    ResumeProfile,
)
from semiconductor.domain.ports import IResumeAdvisorLLM


def _make_guidance(score: int = 70) -> ResumeGuidance:
    return ResumeGuidance(
        match_score=score,
        alignment_items=[AlignmentItem(requirement="소자", status="충족", evidence="공학", action="")],
        summary="양호",
        priority_actions=["ALD 보완"],
        rewrite_suggestions=["수치 추가"],
    )


def _posting() -> JobPosting:
    return JobPosting(raw_text="자격요건: 반도체 소자", company="samsung_ds")


def _resume() -> ResumeProfile:
    return ResumeProfile(raw_text="수강: 반도체공학")


class TestGuideResumeUseCase:
    def test_delegates_to_advisor(self):
        mock_advisor: IResumeAdvisorLLM = MagicMock()
        expected = _make_guidance(75)
        mock_advisor.guide.return_value = expected

        p, r = _posting(), _resume()
        result = GuideResumeUseCase(advisor=mock_advisor).execute(posting=p, resume=r)

        mock_advisor.guide.assert_called_once_with(p, r)
        assert result is expected

    def test_returns_fallback_on_error(self):
        mock_advisor: IResumeAdvisorLLM = MagicMock()
        mock_advisor.guide.side_effect = Exception("LLM timeout")

        result = GuideResumeUseCase(advisor=mock_advisor).execute(
            posting=_posting(), resume=_resume()
        )

        assert result.match_score == 0
        assert "오류" in result.summary
        assert result.alignment_items == []
