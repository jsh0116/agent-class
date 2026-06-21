"""TDD: Claude 이력서 advisor — LLM(init_chat_model) mock, 매핑 로직 검증."""
from unittest.mock import MagicMock

from semiconductor.domain.entities import JobPosting, ResumeProfile
from semiconductor.infrastructure.resume import advisor_service
from semiconductor.infrastructure.resume.advisor_service import (
    ClaudeResumeAdvisor,
    _AlignmentSchema,
    _GuidanceSchema,
)


def _patch_llm(monkeypatch, schema: _GuidanceSchema):
    """init_chat_model → mock 체인. invoke가 schema 반환."""
    structured = MagicMock()
    structured.invoke.return_value = schema
    chat = MagicMock()
    chat.with_structured_output.return_value = structured
    monkeypatch.setattr(advisor_service, "init_chat_model", lambda *a, **k: chat)
    monkeypatch.setattr(advisor_service, "log_llm_call", lambda *a, **k: None)
    return structured


def _schema(score=70):
    return _GuidanceSchema(
        match_score=score,
        alignment_items=[
            _AlignmentSchema(requirement="소자 지식", status="충족", evidence="반도체공학 수강", action="", priority="필수"),
            _AlignmentSchema(requirement="ALD 경험", status="누락", evidence="", action="프로젝트 추가", priority="우대"),
        ],
        summary="전반적으로 양호하나 공정 경험 보완 필요",
        priority_actions=["ALD 프로젝트 추가"],
        rewrite_suggestions=["회로이론 수강을 회로 설계 역량으로 표현"],
    )


class TestClaudeResumeAdvisor:
    def test_매핑_정상(self, monkeypatch):
        _patch_llm(monkeypatch, _schema(72))
        advisor = ClaudeResumeAdvisor()
        result = advisor.guide(
            JobPosting(raw_text="자격요건", company="samsung_ds"),
            ResumeProfile(raw_text="수강: 반도체공학"),
        )
        assert result.match_score == 72
        assert result.grade == "보통"
        assert len(result.alignment_items) == 2
        assert result.status_counts == {"충족": 1, "부분충족": 0, "누락": 1}

    def test_score_범위_clamp(self, monkeypatch):
        _patch_llm(monkeypatch, _schema(150))
        advisor = ClaudeResumeAdvisor()
        result = advisor.guide(JobPosting(raw_text="x"), ResumeProfile(raw_text="y"))
        assert result.match_score == 100

    def test_모호한_status는_부분충족으로_방어매핑(self, monkeypatch):
        schema = _GuidanceSchema(
            match_score=60,
            alignment_items=[_AlignmentSchema(requirement="x", status="모름", evidence="", action="", priority="잘못")],
            summary="s", priority_actions=[], rewrite_suggestions=[],
        )
        _patch_llm(monkeypatch, schema)
        advisor = ClaudeResumeAdvisor()
        result = advisor.guide(JobPosting(raw_text="x"), ResumeProfile(raw_text="y"))
        assert result.alignment_items[0].status == "부분충족"
        assert result.alignment_items[0].priority == "필수"

    def test_빈_requirement_항목은_제외(self, monkeypatch):
        schema = _GuidanceSchema(
            match_score=50,
            alignment_items=[
                _AlignmentSchema(requirement="   ", status="충족", evidence="", action="", priority="필수"),
                _AlignmentSchema(requirement="회로", status="충족", evidence="회로이론", action="", priority="필수"),
            ],
            summary="s", priority_actions=[], rewrite_suggestions=[],
        )
        _patch_llm(monkeypatch, schema)
        advisor = ClaudeResumeAdvisor()
        result = advisor.guide(JobPosting(raw_text="x"), ResumeProfile(raw_text="y"))
        assert len(result.alignment_items) == 1
        assert result.alignment_items[0].requirement == "회로"
