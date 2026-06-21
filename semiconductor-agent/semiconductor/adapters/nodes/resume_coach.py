"""Resume Advisor node — 공채 공고 PDF ↔ 이력서 정렬 가이드.

단일 shot 명령: /이력서 <공고파일> [이력서파일]
  - 공고/이력서 텍스트 로드 (PDF/md/txt, 보안 검증) → JobPosting/ResumeProfile
  - GuideResumeUseCase로 갭 분석 → 출력 포맷
이력서 경로 미지정 시 env RESUME_PATH, 그래도 없으면 'resume.md'.
"""
from __future__ import annotations

import os

from semiconductor.adapters.state import InterviewState
from semiconductor.application.use_cases.guide_resume import GuideResumeUseCase
from semiconductor.domain.entities import JobPosting, ResumeProfile
from semiconductor.infrastructure.llm import LangChainLLMService
from semiconductor.infrastructure.resume.pdf_loader import load_document_text

_USAGE_GUIDE = (
    "📄 이력서 가이드 사용법:\n"
    "  /이력서 [공고파일] [이력서파일]\n\n"
    "  - 공고/이력서는 .pdf / .md / .txt 지원\n"
    "  - 이력서 생략 시 env RESUME_PATH 또는 ./resume.md 사용\n"
    "  예: /이력서 samsung_ds_2026.pdf my_resume.md"
)


def _infer_company(text: str) -> str:
    """공고 텍스트에서 회사 추정 (페르소나 선택용). 미상이면 빈 문자열."""
    low = text.lower()
    if "하이닉스" in text or "hynix" in low:
        return "sk_hynix"
    if "삼성" in text or "samsung" in low:
        return "samsung_ds"
    return ""


def _idle(message: str) -> dict:
    return {
        "mode": "idle",
        "resume_posting_path": None,
        "resume_resume_path": None,
        "display_output": message,
    }


def _format_output(company: str, result) -> str:
    label = {"samsung_ds": "삼성DS", "sk_hynix": "SK하이닉스"}.get(company, "공고")
    counts = result.status_counts
    lines = [
        f"📄 [이력서 가이드] {label} 공고 부합도 [{result.grade}] {result.match_score}/100",
        "",
        f"  충족 {counts['충족']} | 부분충족 {counts['부분충족']} | 누락 {counts['누락']}",
        "",
        f"💬 {result.summary}",
    ]

    if result.alignment_items:
        lines.append("\n📊 요건별 갭 분석:")
        for it in result.alignment_items:
            mark = {"충족": "✅", "부분충족": "🟡", "누락": "❌"}.get(it.status, "•")
            lines.append(f"  {mark} [{it.priority}] {it.requirement}")
            if it.status == "충족" and it.evidence:
                lines.append(f"       └ 근거: {it.evidence}")
            elif it.action:
                lines.append(f"       └ 보완: {it.action}")

    if result.priority_actions:
        lines.append("\n🎯 우선 보완 액션:")
        lines.extend(f"  {i}. {a}" for i, a in enumerate(result.priority_actions, 1))

    if result.rewrite_suggestions:
        lines.append("\n✍️  이력서 문구 제안:")
        lines.extend(f"  - {s}" for s in result.rewrite_suggestions)

    lines.append("\n다른 공고로 다시: /이력서 [공고파일] [이력서파일]")
    return "\n".join(lines)


def resume_advisor_node(state: InterviewState) -> dict:
    posting_path = state.get("resume_posting_path")
    resume_path = (
        state.get("resume_resume_path")
        or os.getenv("RESUME_PATH")
        or "resume.md"
    )

    if not posting_path:
        return _idle(_USAGE_GUIDE)

    try:
        posting_text = load_document_text(posting_path)
    except (FileNotFoundError, ValueError, PermissionError) as e:
        return _idle(f"❌ 공고 파일 처리 실패: {e}\n\n{_USAGE_GUIDE}")

    try:
        resume_text = load_document_text(resume_path)
    except (FileNotFoundError, ValueError, PermissionError) as e:
        return _idle(
            f"❌ 이력서 파일 처리 실패: {e}\n"
            f"  이력서 경로를 두 번째 인자로 주거나 RESUME_PATH를 설정하세요.\n\n"
            f"{_USAGE_GUIDE}"
        )

    company = _infer_company(posting_text)
    posting = JobPosting(raw_text=posting_text, company=company, source=posting_path)
    resume = ResumeProfile(raw_text=resume_text, source=resume_path)

    use_case = GuideResumeUseCase(LangChainLLMService.resume())
    result = use_case.execute(posting=posting, resume=resume)

    guide_dict = {
        "company": company,
        "posting_source": posting_path,
        "match_score": result.match_score,
        "grade": result.grade,
        "summary": result.summary,
        "status_counts": result.status_counts,
        "priority_actions": result.priority_actions,
        "rewrite_suggestions": result.rewrite_suggestions,
        "alignment_items": [
            {
                "requirement": it.requirement,
                "status": it.status,
                "evidence": it.evidence,
                "action": it.action,
                "priority": it.priority,
            }
            for it in result.alignment_items
        ],
    }

    return {
        "resume_guides": state.get("resume_guides", []) + [guide_dict],
        "resume_posting_path": None,
        "resume_resume_path": None,
        "mode": "idle",
        "display_output": _format_output(company, result),
    }
