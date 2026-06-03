"""Essay Coach nodes — 자소서 첨삭 모듈.

Phase 패턴 (interview와 동일):
  essay_present  → 항목 prompt 표시 (phase: present → evaluate)
  essay_evaluate → 사용자가 입력한 자소서 평가 + 출력
"""
from __future__ import annotations

import functools

from langchain_core.messages import HumanMessage

from semiconductor.adapters.state import InterviewState
from semiconductor.application.use_cases.coach_essay import CoachEssayUseCase
from semiconductor.infrastructure.essay.prompts import (
    get_essay_prompt,
    list_companies,
    list_items,
)
from semiconductor.infrastructure.llm import LangChainLLMService


def _default_essay():
    # 모듈 글로벌 지연 조회 — patch 호환 + composition root 주입 지점.
    return LangChainLLMService.essay()


def essay_present_node(state: InterviewState) -> dict:
    """선택된 (회사, 항목)에 해당하는 prompt 표시. phase: present → evaluate."""
    company = state.get("essay_company")
    item = state.get("essay_item")

    if not company or not item:
        # 명령어가 부족 — 사용 가이드 표시 후 idle 복귀
        companies = list_companies()
        items_per = "\n".join(
            f"  {c}: {', '.join(list_items(c))}" for c in companies
        )
        return {
            "mode": "idle",
            "display_output": (
                "📝 자소서 첨삭 사용법:\n"
                "  /자소서 [회사] [항목]\n\n"
                "지원 가능 회사·항목:\n" + items_per +
                "\n\n예: /자소서 samsung_ds 지원동기"
            ),
        }

    prompt = get_essay_prompt(company, item)
    if prompt is None:
        return {
            "mode": "idle",
            "display_output": (
                f"❌ 알 수 없는 항목: {company} / {item}\n"
                f"  지원 항목: {list_items(company)}"
            ),
        }

    output = (
        f"📝 [{company}] {item} 자소서 항목\n\n"
        f"{prompt.description}\n\n"
        f"📏 글자 수 제한: {prompt.word_limit}자\n\n"
        "자소서를 입력하세요:"
    )
    return {
        "essay_phase": "evaluate",
        "display_output": output,
    }


def essay_evaluate_node(state: InterviewState, *, essay_factory=_default_essay) -> dict:
    """사용자가 입력한 자소서를 Claude essay coach로 평가."""
    company = state.get("essay_company")
    item = state.get("essay_item")
    prompt = get_essay_prompt(company, item) if company and item else None
    if prompt is None:
        return {
            "mode": "idle",
            "essay_phase": "present",
            "essay_company": None,
            "essay_item": None,
            "display_output": "❌ 자소서 컨텍스트가 손실되었습니다. /자소서 명령으로 다시 시작해주세요.",
        }

    human_msgs = [m for m in state.get("messages", []) if isinstance(m, HumanMessage)]
    user_essay = human_msgs[-1].content if human_msgs else ""

    if not user_essay.strip():
        return {
            "display_output": "❌ 자소서 텍스트가 비어있습니다. 다시 입력해주세요.",
        }

    use_case = CoachEssayUseCase(essay_factory())
    result = use_case.execute(prompt=prompt, user_essay=user_essay)

    output_lines = [
        f"📝 [{company}] {item} 첨삭 결과 [{result.grade}] {result.total_score}/100점",
        "",
        f"  부합도(인재상) {result.fit_score}/30 | 구조 {result.structure_score}/25"
        f" | 구체성 {result.specificity_score}/25 | 작문 {result.writing_score}/20",
        "",
        f"💬 {result.feedback}",
        "",
        f"✅ 잘된 점: {', '.join(result.strong_points) or '없음'}",
        f"📌 보완점:  {', '.join(result.weak_points) or '없음'}",
    ]
    if result.culture_alignment:
        output_lines.append(f"\n🎯 인재상 부합도: {result.culture_alignment}")
    if result.revised_excerpt:
        output_lines.append(f"\n✍️  첨삭 예시:\n{result.revised_excerpt}")

    output_lines.append("\n다른 항목 첨삭은 /자소서 명령으로 다시 시작하세요.")

    eval_dict = {
        "company": company,
        "item": item,
        "fit_score": result.fit_score,
        "structure_score": result.structure_score,
        "specificity_score": result.specificity_score,
        "writing_score": result.writing_score,
        "total_score": result.total_score,
        "grade": result.grade,
        "feedback": result.feedback,
        "strong_points": result.strong_points,
        "weak_points": result.weak_points,
        "revised_excerpt": result.revised_excerpt,
        "culture_alignment": result.culture_alignment,
    }

    return {
        "essays_evaluated": state.get("essays_evaluated", []) + [eval_dict],
        "essay_company": None,
        "essay_item": None,
        "essay_phase": "present",
        "mode": "idle",
        "display_output": "\n".join(output_lines),
    }


def make_essay_evaluate_node(essay_factory=_default_essay):
    """composition root용 — essay coach factory를 노드에 바인딩."""
    return functools.partial(essay_evaluate_node, essay_factory=essay_factory)
