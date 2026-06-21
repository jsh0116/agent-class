"""TDD: Resume Advisor (이력서 가이드) adapter."""
from unittest.mock import MagicMock, patch

from langchain_core.messages import HumanMessage

from semiconductor.adapters.nodes.orchestrator import (
    orchestrator_node,
    route_from_orchestrator,
)
from semiconductor.adapters.nodes.resume_coach import resume_advisor_node
from semiconductor.adapters.state import create_initial_state
from semiconductor.domain.entities import AlignmentItem, ResumeGuidance


def _make_guidance(score=72):
    return ResumeGuidance(
        match_score=score,
        alignment_items=[
            AlignmentItem(requirement="소자 지식", status="충족", evidence="반도체공학", action=""),
            AlignmentItem(requirement="ALD 경험", status="누락", evidence="", action="프로젝트 추가", priority="우대"),
        ],
        summary="공정 경험 보완 필요",
        priority_actions=["ALD 프로젝트 추가"],
        rewrite_suggestions=["회로이론 → 회로 설계 역량으로 표현"],
    )


# ── Orchestrator 명령어 파싱 ──────────────────────────────────────


class TestResumeOrchestratorCommand:
    def test_이력서_명령_공고_이력서_경로_파싱(self):
        s = dict(create_initial_state())
        s["messages"] = [HumanMessage(content="/이력서 posting.pdf resume.md")]
        result = orchestrator_node(s)
        assert result["mode"] == "resume"
        assert result["resume_posting_path"] == "posting.pdf"
        assert result["resume_resume_path"] == "resume.md"

    def test_이력서_명령_인자_없으면_경로_None(self):
        s = dict(create_initial_state())
        s["messages"] = [HumanMessage(content="/이력서")]
        result = orchestrator_node(s)
        assert result["mode"] == "resume"
        assert result["resume_posting_path"] is None

    def test_resume_mode는_resume_advisor로_라우팅(self):
        s = dict(create_initial_state())
        s["mode"] = "resume"
        assert route_from_orchestrator(s) == "resume_advisor"


# ── resume_advisor_node ───────────────────────────────────────────


class TestResumeAdvisorNode:
    def test_공고_경로_없으면_사용가이드_idle(self):
        s = dict(create_initial_state())
        s["resume_posting_path"] = None
        result = resume_advisor_node(s)
        assert result["mode"] == "idle"
        assert "/이력서" in result["display_output"]

    def test_공고_파일_없으면_에러_안내_idle(self, tmp_path):
        s = dict(create_initial_state())
        s["resume_posting_path"] = str(tmp_path / "nope.pdf")
        result = resume_advisor_node(s)
        assert result["mode"] == "idle"
        assert "공고 파일 처리 실패" in result["display_output"]

    @patch("semiconductor.adapters.nodes.resume_coach.LangChainLLMService")
    def test_정상_가이드_출력_및_누적(self, mock_svc, tmp_path):
        mock_advisor = MagicMock()
        mock_advisor.guide.return_value = _make_guidance(72)
        mock_svc.resume.return_value = mock_advisor

        posting = tmp_path / "samsung_2026.md"
        posting.write_text("삼성전자 DS 신입 공채. 자격요건: 반도체 소자 지식", encoding="utf-8")
        resume = tmp_path / "resume.md"
        resume.write_text("수강: 반도체공학, 회로이론", encoding="utf-8")

        s = dict(create_initial_state())
        s["resume_posting_path"] = str(posting)
        s["resume_resume_path"] = str(resume)
        result = resume_advisor_node(s)

        assert "72/100" in result["display_output"]
        assert "[보통]" in result["display_output"]
        assert "삼성DS" in result["display_output"]  # 회사 추정 반영
        assert "갭 분석" in result["display_output"]
        assert result["mode"] == "idle"
        assert result["resume_posting_path"] is None
        assert len(result["resume_guides"]) == 1
        assert result["resume_guides"][0]["match_score"] == 72

    @patch("semiconductor.adapters.nodes.resume_coach.LangChainLLMService")
    def test_이력서_파일_없으면_LLM_호출_안함(self, mock_svc, tmp_path):
        posting = tmp_path / "p.md"
        posting.write_text("공고 내용", encoding="utf-8")
        s = dict(create_initial_state())
        s["resume_posting_path"] = str(posting)
        s["resume_resume_path"] = str(tmp_path / "missing.md")
        result = resume_advisor_node(s)
        assert "이력서 파일 처리 실패" in result["display_output"]
        mock_svc.resume.assert_not_called()
