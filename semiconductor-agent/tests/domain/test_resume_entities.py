"""TDD: 이력서 가이드 도메인 엔티티."""
import pytest

from semiconductor.domain.entities import (
    AlignmentItem,
    JobPosting,
    ResumeGuidance,
    ResumeProfile,
)


class TestJobPosting:
    def test_생성_정상(self):
        p = JobPosting(raw_text="자격요건: 반도체 소자 지식", company="samsung_ds", source="a.pdf")
        assert p.company == "samsung_ds"
        assert "자격요건" in p.raw_text

    def test_company_기본값은_빈문자열(self):
        assert JobPosting(raw_text="내용").company == ""

    def test_빈_텍스트는_거부(self):
        with pytest.raises(ValueError, match="비어있을 수 없"):
            JobPosting(raw_text="   ")


class TestResumeProfile:
    def test_생성_정상(self):
        r = ResumeProfile(raw_text="수강: 반도체공학, 회로이론", source="resume.md")
        assert "회로이론" in r.raw_text

    def test_빈_텍스트는_거부(self):
        with pytest.raises(ValueError, match="비어있을 수 없"):
            ResumeProfile(raw_text="")


class TestAlignmentItem:
    def test_생성_정상(self):
        item = AlignmentItem(
            requirement="ALD 공정 이해", status="부분충족",
            evidence="박막공정 수강", action="ALD 프로젝트 경험 추가", priority="우대",
        )
        assert item.status == "부분충족"
        assert item.priority == "우대"

    def test_priority_기본값은_필수(self):
        item = AlignmentItem(requirement="x", status="충족", evidence="y", action="z")
        assert item.priority == "필수"

    def test_잘못된_status_거부(self):
        with pytest.raises(ValueError, match="status"):
            AlignmentItem(requirement="x", status="애매", evidence="", action="")

    def test_잘못된_priority_거부(self):
        with pytest.raises(ValueError, match="priority"):
            AlignmentItem(requirement="x", status="충족", evidence="", action="", priority="옵션")

    def test_빈_requirement_거부(self):
        with pytest.raises(ValueError, match="requirement"):
            AlignmentItem(requirement="  ", status="충족", evidence="", action="")


class TestResumeGuidance:
    def _items(self):
        return [
            AlignmentItem(requirement="소자 지식", status="충족", evidence="반도체공학", action=""),
            AlignmentItem(requirement="ALD 경험", status="누락", evidence="", action="프로젝트 추가", priority="우대"),
            AlignmentItem(requirement="회로 이해", status="부분충족", evidence="회로이론", action="심화"),
        ]

    def test_생성_및_grade(self):
        g = ResumeGuidance(
            match_score=72, alignment_items=self._items(),
            summary="전반적으로 양호", priority_actions=["ALD 보완"],
            rewrite_suggestions=["수치 추가"],
        )
        assert g.grade == "보통"
        assert g.match_score == 72

    def test_grade_경계(self):
        assert ResumeGuidance(80, [], "", []).grade == "우수"
        assert ResumeGuidance(50, [], "", []).grade == "보통"
        assert ResumeGuidance(49, [], "", []).grade == "미흡"

    def test_match_score_범위_초과_거부(self):
        with pytest.raises(ValueError, match="match_score"):
            ResumeGuidance(101, [], "", [])

    def test_status_counts(self):
        g = ResumeGuidance(70, self._items(), "", [])
        assert g.status_counts == {"충족": 1, "부분충족": 1, "누락": 1}

    def test_rewrite_suggestions_기본값은_빈리스트(self):
        g = ResumeGuidance(70, [], "summary", ["action"])
        assert g.rewrite_suggestions == []
