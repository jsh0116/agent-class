"""Diagnostic node — domain-score analysis and matplotlib chart."""
from __future__ import annotations
import functools
import io

from semiconductor.adapters.state import InterviewState
from semiconductor.application.use_cases.diagnose_session import DiagnoseSessionUseCase
from semiconductor.domain.entities import EvaluationResult
from semiconductor.infrastructure.llm import LangChainLLMService


def _default_diagnostic():
    # 모듈 글로벌 지연 조회 — patch 호환 + composition root 주입 지점.
    return LangChainLLMService.diagnostic()


def _deserialize(evals: list[dict]) -> list[EvaluationResult]:
    results = []
    for e in evals:
        total = e["accuracy_score"] + e["depth_score"] + e["terminology_score"]
        results.append(EvaluationResult(
            accuracy_score=e["accuracy_score"],
            depth_score=e["depth_score"],
            terminology_score=e["terminology_score"],
            total_score=total,
            feedback=e.get("feedback", ""),
            strong_points=e.get("strong_points", []),
            weak_points=e.get("weak_points", []),
            question=e["question"],
            model_answer=e.get("model_answer", ""),
            specialist_commentary=e.get("specialist_commentary", ""),
            follow_up_question=e.get("follow_up_question", ""),
        ))
    return results


def _render_chart(domain_scores: dict[str, int]) -> bytes:
    import matplotlib.pyplot as plt

    domains = list(domain_scores.keys())
    scores = [domain_scores[d] for d in domains]
    colors = [
        "#4CAF50" if s >= 70 else "#FF9800" if s >= 40 else "#F44336"
        for s in scores
    ]

    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(domains, scores, color=colors, width=0.5)
    ax.set_ylim(0, 110)
    ax.set_ylabel("이해도 점수")
    ax.set_title("도메인별 이해도 진단 결과")
    ax.axhline(y=70, color="green", linestyle="--", alpha=0.5, label="우수 기준 (70)")
    ax.axhline(y=40, color="orange", linestyle="--", alpha=0.5, label="보통 기준 (40)")

    for bar, score in zip(bars, scores):
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            bar.get_height() + 2,
            f"{score}점",
            ha="center",
            va="bottom",
            fontweight="bold",
        )

    ax.legend()
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    buf.seek(0)
    chart_bytes = buf.read()

    plt.show()   # Jupyter inline 렌더링용 — Chainlit에서는 chart_bytes 사용
    plt.close(fig)
    return chart_bytes


def diagnostic_node(state: InterviewState, *, diagnostic_factory=_default_diagnostic) -> dict:
    evals_raw = state.get("evaluations", [])

    if not evals_raw:
        return {
            "display_output": (
                "❌ 평가 데이터가 없습니다.\n"
                "  먼저 /인터뷰 로 모의면접을 진행해주세요."
            ),
            "mode": "idle",
        }

    evals = _deserialize(evals_raw)
    diag_uc = DiagnoseSessionUseCase(diagnostic_factory())

    try:
        result = diag_uc.execute(evals)
    except Exception as exc:
        return {
            "display_output": f"❌ 진단 중 오류가 발생했습니다: {exc}",
            "mode": "idle",
        }

    lines = ["🔬 이해도 진단 결과\n", "도메인별 점수:"]
    for domain, score in result.domain_scores.items():
        icon = "🟢" if score >= 70 else "🟡" if score >= 40 else "🔴"
        lines.append(f"  {icon} {domain}: {score}점")

    lines.append(f"\n💪 강점 영역: {', '.join(result.strong_topics) or '아직 없음'}")
    lines.append(f"📚 보완 필요: {', '.join(result.weak_topics) or '없음'}")
    lines.append(f"🎯 다음 학습 추천: {result.recommended_next}")

    chart_png: bytes | None = None
    try:
        chart_png = _render_chart(result.domain_scores)
    except Exception:
        lines.append("\n(차트 렌더링 실패 — 텍스트 결과를 확인하세요)")

    return {
        "display_output": "\n".join(lines),
        "chart_png": chart_png,
        "mode": "idle",
    }


def make_diagnostic_node(diagnostic_factory=_default_diagnostic):
    """composition root용 — diagnostic LLM factory를 노드에 바인딩."""
    return functools.partial(diagnostic_node, diagnostic_factory=diagnostic_factory)
