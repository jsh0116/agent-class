"""EvaluationResult ↔ dict 직렬화 유틸 — 노드 간 state 전달용."""
from __future__ import annotations

from typing import Optional

from semiconductor.domain.entities import EvaluationResult


def serialize_eval(e: EvaluationResult, domain: Optional[str] = None) -> dict:
    """평가 결과를 dict로. domain을 함께 실어 영속 데이터에서 도메인이 보이게 한다.

    (EvaluationResult 엔티티엔 domain이 없어 과거엔 누락 → weekly_review가 질문
    텍스트로 추정해야 했다. 직렬화 시점엔 current_question_domain을 알고 있다.)
    """
    return {
        "domain": domain,
        "question": e.question,
        "accuracy_score": e.accuracy_score,
        "depth_score": e.depth_score,
        "terminology_score": e.terminology_score,
        "total_score": e.total_score,
        "grade": e.grade,
        "feedback": e.feedback,
        "strong_points": list(e.strong_points),
        "weak_points": list(e.weak_points),
        "model_answer": e.model_answer,
        "specialist_commentary": e.specialist_commentary,
        "follow_up_question": e.follow_up_question,
    }


def deserialize_eval(d: dict) -> EvaluationResult:
    return EvaluationResult(
        accuracy_score=d["accuracy_score"],
        depth_score=d["depth_score"],
        terminology_score=d["terminology_score"],
        total_score=d["total_score"],
        feedback=d.get("feedback", ""),
        strong_points=d.get("strong_points", []),
        weak_points=d.get("weak_points", []),
        question=d["question"],
        model_answer=d.get("model_answer", ""),
        specialist_commentary=d.get("specialist_commentary", ""),
        follow_up_question=d.get("follow_up_question", ""),
    )
