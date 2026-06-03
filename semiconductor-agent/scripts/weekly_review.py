#!/usr/bin/env python3
"""주간 누적 진단 — 도메인별 점수 추이 + 사용 통계.

사용:
    uv run python scripts/weekly_review.py
    # 출력: weekly_report_YYYYMMDD.png + 콘솔 요약

데이터 소스:
- LangGraph SqliteSaver: 누적 evaluations (도메인별 점수)
- usage.jsonl: 호출 횟수·모델별·노드별 사용량

매주 토요일 자동화하려면 cron:
    0 9 * * 6  cd ~/.../semiconductor-agent && uv run python scripts/weekly_review.py
"""
from __future__ import annotations

import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from semiconductor.adapters.graph import create_app_with_sqlite
from semiconductor.infrastructure.observability.usage_log import read_usage

load_dotenv()

DB_PATH = os.getenv("AGENT_DB", ".agent_state.db")
THREAD_ID = os.getenv("THREAD_ID", "hans")
USAGE_PATH = os.getenv("USAGE_LOG_PATH", "usage.jsonl")


def _domain_from_question(q_text: str) -> str:
    """질문 텍스트에서 도메인 추정 — 옛 영속 데이터(domain 미기록) 폴백용."""
    keywords = {
        "소자": ["MOSFET", "FinFET", "GAA", "트랜지스터", "DRAM 셀", "NAND"],
        "공정": ["CVD", "ALD", "PVD", "포토", "리소", "식각", "Etch", "CMP"],
        "회로": ["센스앰프", "차지펌프", "메모리 컨트롤러", "회로", "센스 앰프"],
        "트렌드": ["HBM", "EUV", "3D NAND", "CoWoS", "SoIC", "패키징"],
    }
    for domain, kws in keywords.items():
        for kw in kws:
            if kw in q_text:
                return domain
    return "기타"


def aggregate_eval_history(state) -> dict:
    """누적 evaluations에서 도메인별 점수·시간 분포 추출."""
    evals = state.get("evaluations", []) or []
    by_domain: dict[str, list[int]] = defaultdict(list)
    for e in evals:
        # 직렬화된 domain을 우선 사용. 없으면(옛 데이터) 질문 텍스트로 추정.
        d = e.get("domain") or _domain_from_question(e.get("question", ""))
        by_domain[d].append(e.get("total_score", 0))
    return {d: scores for d, scores in by_domain.items()}


def usage_summary(records: list[dict], days: int = 7) -> dict:
    """최근 N일 usage.jsonl 요약."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent = [
        r for r in records
        if datetime.fromisoformat(r["ts"]) >= cutoff
    ]
    by_node = Counter(r["node"] for r in recent)
    by_model = Counter(r["model"] for r in recent)
    total_cost = sum(r.get("cost_usd", 0) for r in recent)
    return {
        "total_calls": len(recent),
        "by_node": dict(by_node),
        "by_model": dict(by_model),
        "total_cost_usd": total_cost,
    }


def render_chart(by_domain: dict, usage: dict, output_path: str) -> None:
    """도메인별 점수 분포 + 노드별 호출 횟수 차트."""
    import matplotlib

    # macOS 한글 폰트 fallback (없어도 비치명적). 기본 폰트는 한글 glyph가 없어
    # 콘솔이 UserWarning 수십 줄로 도배되고 stdout 요약이 묻힌다. (eval_judge.py와 동일)
    for cand in ("AppleGothic", "Malgun Gothic", "NanumGothic"):
        try:
            matplotlib.rcParams["font.family"] = cand
            break
        except Exception:
            continue
    matplotlib.rcParams["axes.unicode_minus"] = False

    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Left: 도메인별 점수 분포 (boxplot 대신 평균 + 최근 점수)
    domains = list(by_domain.keys()) or ["없음"]
    averages = [sum(by_domain[d]) / len(by_domain[d]) if by_domain.get(d) else 0 for d in domains]
    latest = [by_domain[d][-1] if by_domain.get(d) else 0 for d in domains]

    x = range(len(domains))
    width = 0.35
    axes[0].bar([i - width / 2 for i in x], averages, width, label="평균", color="#1976D2")
    axes[0].bar([i + width / 2 for i in x], latest, width, label="최근", color="#FFA726")
    axes[0].set_xticks(list(x))
    axes[0].set_xticklabels(domains)
    axes[0].set_ylim(0, 110)
    axes[0].axhline(70, color="green", linestyle="--", alpha=0.5, label="우수 기준")
    axes[0].set_ylabel("점수")
    axes[0].set_title("도메인별 점수 (평균 vs 최근)")
    axes[0].legend()

    # Right: 최근 7일 노드별 호출 횟수
    by_node = usage.get("by_node", {})
    if by_node:
        nodes = list(by_node.keys())
        counts = [by_node[n] for n in nodes]
        axes[1].barh(nodes, counts, color="#66BB6A")
        axes[1].set_xlabel("호출 횟수")
        axes[1].set_title(f"최근 7일 노드별 호출 (총 {usage['total_calls']}회)")
        for i, v in enumerate(counts):
            axes[1].text(v + 0.1, i, str(v), va="center")
    else:
        axes[1].text(0.5, 0.5, "최근 7일 호출 기록 없음",
                     ha="center", va="center", transform=axes[1].transAxes)
        axes[1].set_title("최근 7일 호출")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def print_summary(by_domain: dict, usage: dict, total_evals: int) -> None:
    print("📊 [주간 회고]")
    print("=" * 50)
    print(f"\n📚 누적 평가: {total_evals}개\n")

    if by_domain:
        print("🎯 도메인별 점수:")
        for d, scores in sorted(by_domain.items()):
            avg = sum(scores) / len(scores)
            latest = scores[-1]
            trend = "↑" if latest > avg else ("↓" if latest < avg else "→")
            icon = "🟢" if avg >= 70 else "🟡" if avg >= 40 else "🔴"
            print(f"  {icon} {d}: 평균 {avg:.1f}점 / 최근 {latest}점 {trend} (n={len(scores)})")
    else:
        print("  (평가 기록 없음 — daily.py로 면접 시작)")

    print(f"\n💰 최근 7일 LLM 사용:")
    print(f"  총 호출: {usage['total_calls']}회")
    print(f"  추정 비용: ${usage['total_cost_usd']:.4f}")
    if usage.get("by_node"):
        print("  노드별:")
        for node, n in sorted(usage["by_node"].items(), key=lambda x: -x[1]):
            print(f"    {node}: {n}")
    if usage.get("by_model"):
        print("  모델별:")
        for model, n in sorted(usage["by_model"].items(), key=lambda x: -x[1]):
            print(f"    {model}: {n}")


def main() -> int:
    # 1. SqliteSaver에서 누적 state 로드
    app, _ = create_app_with_sqlite(db_path=DB_PATH)
    config = {"configurable": {"thread_id": THREAD_ID}}
    snap = app.get_state(config)
    state = snap.values or {}

    # 2. evaluations 도메인별 집계
    by_domain = aggregate_eval_history(state)
    total_evals = len(state.get("evaluations", []) or [])

    # 3. usage.jsonl 7일 요약
    records = read_usage(USAGE_PATH)
    usage = usage_summary(records, days=7)

    # 4. 콘솔 출력
    print_summary(by_domain, usage, total_evals)

    # 5. 차트 저장
    out_path = f"weekly_report_{datetime.now().strftime('%Y%m%d')}.png"
    try:
        render_chart(by_domain, usage, out_path)
        print(f"\n✅ 차트 저장: {out_path}")
    except Exception as exc:
        print(f"\n⚠️  차트 렌더링 실패 ({type(exc).__name__}): 콘솔 요약만 활용하세요.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
