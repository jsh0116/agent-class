"""Behavioral interview (인성면접 STAR) nodes — present + evaluate."""
from __future__ import annotations

import functools

from langchain_core.messages import HumanMessage

from semiconductor.adapters.state import InterviewState
from semiconductor.application.use_cases.coach_behavioral import CoachBehavioralUseCase
from semiconductor.domain.entities import BehavioralQuestion
from semiconductor.infrastructure.behavioral.questions import pick_question
from semiconductor.infrastructure.llm import LangChainLLMService


def _default_behavioral():
    # 모듈 글로벌 지연 조회 — patch 호환 + composition root 주입 지점.
    return LangChainLLMService.behavioral()


def behavioral_present_node(state: InterviewState) -> dict:
    """질문 풀에서 다음 질문 출제. phase: present → evaluate."""
    company = state.get("behavioral_company") or "samsung_ds"
    asked = state.get("behavioral_asked_count", 0)

    q = pick_question(company, asked)
    if q is None:
        return {
            "mode": "idle",
            "behavioral_phase": "present",
            "display_output": f"❌ {company}에 해당하는 인성면접 질문이 없습니다.",
        }

    output = (
        f"💼 [인성면접 — {company}] 질문 {asked + 1}\n"
        f"평가 역량: {q.competency}\n\n"
        f"{q.question}\n\n"
        "STAR 기법(Situation/Task/Action/Result)으로 답변해주세요:"
    )
    return {
        "behavioral_phase": "evaluate",
        "behavioral_question_text": q.question,
        "behavioral_competency": q.competency,
        "display_output": output,
    }


def behavioral_evaluate_node(state: InterviewState, *, behavioral_factory=_default_behavioral) -> dict:
    """사용자 STAR 답변 평가."""
    company = state.get("behavioral_company") or "samsung_ds"
    q_text = state.get("behavioral_question_text")
    competency = state.get("behavioral_competency")
    if not q_text or not competency:
        return {
            "mode": "idle",
            "behavioral_phase": "present",
            "display_output": "❌ 인성면접 컨텍스트가 손실되었습니다. /인성 으로 다시 시작해주세요.",
        }

    human_msgs = [m for m in state.get("messages", []) if isinstance(m, HumanMessage)]
    user_answer = human_msgs[-1].content if human_msgs else ""
    if not user_answer.strip():
        return {"display_output": "❌ 답변이 비어있습니다."}

    q = BehavioralQuestion(company=company, question=q_text, competency=competency)
    use_case = CoachBehavioralUseCase(behavioral_factory())
    result = use_case.execute(q, user_answer)

    lines = [
        f"💼 [인성면접 평가] {result.grade} — {result.total_score}/100점",
        "",
        f"  Situation {result.situation_score}/20 | Task {result.task_score}/20"
        f" | Action {result.action_score}/30 | Result {result.result_score}/20"
        f" | 인재상 {result.culture_fit}/10",
        "",
        f"💬 {result.feedback}",
        "",
        f"✅ 잘된 점: {', '.join(result.strong_points) or '없음'}",
        f"📌 보완점:  {', '.join(result.weak_points) or '없음'}",
    ]
    if result.improved_answer:
        lines.append(f"\n✍️  STAR 모범답변 예시:\n{result.improved_answer}")
    lines.append("\n다음 질문은 /인성 으로 다시 시작하세요.")

    eval_dict = {
        "company": company,
        "question": q_text,
        "competency": competency,
        "situation_score": result.situation_score,
        "task_score": result.task_score,
        "action_score": result.action_score,
        "result_score": result.result_score,
        "culture_fit": result.culture_fit,
        "total_score": result.total_score,
        "grade": result.grade,
        "feedback": result.feedback,
        "strong_points": result.strong_points,
        "weak_points": result.weak_points,
        "improved_answer": result.improved_answer,
    }

    return {
        "behaviorals_evaluated": state.get("behaviorals_evaluated", []) + [eval_dict],
        "behavioral_asked_count": state.get("behavioral_asked_count", 0) + 1,
        "behavioral_question_text": None,
        "behavioral_competency": None,
        "behavioral_phase": "present",
        "mode": "idle",
        "display_output": "\n".join(lines),
    }


def make_behavioral_evaluate_node(behavioral_factory=_default_behavioral):
    """composition root용 — behavioral coach factory를 노드에 바인딩."""
    return functools.partial(behavioral_evaluate_node, behavioral_factory=behavioral_factory)
