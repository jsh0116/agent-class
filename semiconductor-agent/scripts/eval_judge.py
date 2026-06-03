"""judge 품질 리포트 생성 — 골든셋을 실제 judge로 돌려 표 + 차트 출력.

  uv run python scripts/eval_judge.py

출력:
  - 콘솔: markdown 표 + 순서 일관성 요약
  - eval_report_YYYYMMDD.md : README에 첨부할 "교수 초과" 증거
  - eval_report_YYYYMMDD.png : 도메인별 우수/보통/미흡 점수 그룹 막대

OPENAI_API_KEY 필요. tests/eval/test_judge_quality.py 와 같은 골든셋을 공유한다
(검증 = 스위트, 증거물 = 이 스크립트).
"""
from __future__ import annotations

import os
import sys
from datetime import date

# 프로젝트 루트를 import 경로에 추가 (scripts/ 에서 직접 실행 대응)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.eval.golden_set import GOLDEN_CASES, cases_by_family  # noqa: E402

_GRADE_ORDER = ["우수", "보통", "미흡"]
_GRADE_COLOR = {"우수": "#4CAF50", "보통": "#FF9800", "미흡": "#F44336"}


def _evaluate_all() -> dict[str, int]:
    """사용자가 실제로 보는 점수(judge → adaptive critic skip → 최종)로 평가.

    conftest의 eval 스위트와 동일한 파이프라인 — judge만 호출하면 31~84 구간에서
    critic이 바꾸는 값을 놓친다.
    """
    from semiconductor.application.use_cases.adaptive_critic import (
        CriticSkipConfig,
        apply_adaptive_critic,
    )
    from semiconductor.infrastructure.llm import LangChainLLMService

    judge = LangChainLLMService.judge()
    config = CriticSkipConfig.from_env()
    scores: dict[str, int] = {}
    for case in GOLDEN_CASES:
        initial = judge.evaluate(question=case.question, user_answer=case.answer)
        final = apply_adaptive_critic(
            initial,
            question=case.question,
            user_answer=case.answer,
            critic_factory=LangChainLLMService.critic,
            config=config,
        )
        scores[case.case_id] = final.total_score
        print(f"  평가 완료: {case.case_id:24s} → {final.total_score:3d}점 "
              f"(기대 {case.expected_grade})")
    return scores


def _ordering_ok(scores: dict[str, int]) -> bool:
    """모든 도메인에서 우수 > 보통 > 미흡 순서가 유지되는가 (CI 게이트 기준)."""
    for cs in cases_by_family().values():
        st, mi, wk = (scores[cs[g].case_id] for g in _GRADE_ORDER)
        if not (st > mi > wk):
            return False
    return True


def _build_markdown(scores: dict[str, int]) -> str:
    lines = [
        f"# judge 품질 리포트 ({date.today().isoformat()})",
        "",
        "골든셋으로 측정한 judge LLM의 변별력. **순서 일관성**(우수>보통>미흡)이 주지표.",
        "",
        "| case | 도메인 | 기대 등급 | 점수대 | 실제 점수 | band | 근거 |",
        "|------|--------|----------|--------|----------|------|------|",
    ]
    by_id = {c.case_id: c for c in GOLDEN_CASES}
    for case in GOLDEN_CASES:
        s = scores[case.case_id]
        band_ok = "✅" if case.min_total <= s <= case.max_total else "❌"
        lines.append(
            f"| {case.case_id} | {case.question.domain} | {case.expected_grade} | "
            f"{case.min_total}~{case.max_total} | {s} | {band_ok} | {case.rationale} |"
        )

    # 순서 일관성 요약
    lines += ["", "## 순서 일관성 (주지표)", ""]
    families = cases_by_family()
    all_ok = True
    for fam, cs in sorted(families.items()):
        st, mi, wk = (scores[cs[g].case_id] for g in _GRADE_ORDER)
        ok = st > mi > wk
        all_ok = all_ok and ok
        mark = "✅" if ok else "❌ 변별 실패"
        lines.append(f"- **{fam}** ({cs['우수'].question.domain}): "
                     f"우수 {st} > 보통 {mi} > 미흡 {wk} {mark}")

    strong_avg = sum(scores[f["우수"].case_id] for f in families.values()) / len(families)
    weak_avg = sum(scores[f["미흡"].case_id] for f in families.values()) / len(families)
    lines += [
        "",
        f"**전반 변별폭**: 우수 평균 {strong_avg:.1f} − 미흡 평균 {weak_avg:.1f} "
        f"= {strong_avg - weak_avg:.1f}점",
        "",
        f"**판정**: {'모든 도메인 순서 일관성 통과 ✅' if all_ok else '일부 도메인 변별 실패 ❌'}",
        "",
        "_비결정성 주의: judge는 temperature=0이나 LLM 특성상 절대 점수는 ±몇 점 흔들릴 수 "
        "있음. 순위 일관성과 변별폭으로 품질을 판단한다._",
    ]
    return "\n".join(lines)


def _render_chart(scores: dict[str, int], out_path: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # macOS 한글 폰트 fallback (없어도 비치명적)
    for cand in ("AppleGothic", "Malgun Gothic", "NanumGothic"):
        try:
            matplotlib.rcParams["font.family"] = cand
            break
        except Exception:
            continue
    matplotlib.rcParams["axes.unicode_minus"] = False

    families = cases_by_family()
    fams = sorted(families.items(), key=lambda kv: kv[1]["우수"].question.domain)
    labels = [cs["우수"].question.domain for _, cs in fams]
    x = range(len(fams))
    width = 0.25

    fig, ax = plt.subplots(figsize=(9, 5))
    for i, grade in enumerate(_GRADE_ORDER):
        vals = [scores[cs[grade].case_id] for _, cs in fams]
        offset = (i - 1) * width
        ax.bar([xi + offset for xi in x], vals, width=width,
               label=grade, color=_GRADE_COLOR[grade])

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 110)
    ax.set_ylabel("총점 (0–100)")
    ax.set_title(f"judge 변별력: 도메인별 우수/보통/미흡 점수 ({date.today().isoformat()})")
    ax.axhline(y=80, color="green", linestyle="--", alpha=0.4, label="우수 기준 (80)")
    ax.axhline(y=50, color="orange", linestyle="--", alpha=0.4, label="보통 기준 (50)")
    ax.legend(ncol=2)
    plt.tight_layout()
    fig.savefig(out_path, dpi=150)
    print(f"\n차트 저장: {out_path}")


def _missing_api_keys() -> list[str]:
    """judge·critic가 쓰는 provider 키 중 미설정 목록 (conftest와 동일 단일 소스).

    기본 tier는 judge=openai, critic=anthropic이므로 OPENAI 키만으론 부족하다 —
    회색지대(31~84) 케이스가 critic을 호출하다 런타임 인증 실패한다.
    """
    from semiconductor.infrastructure.llm.llm_service import (
        provider_env_key,
        resolved_model_spec,
    )

    needed = {
        provider_env_key(resolved_model_spec("judge")),
        provider_env_key(resolved_model_spec("critic")),
    }
    return sorted(k for k in needed if k and not os.getenv(k))


def main() -> int:
    missing = _missing_api_keys()
    if missing:
        print(f"❌ API 키 미설정: {', '.join(missing)} — 실제 평가 불가.", file=sys.stderr)
        return 1

    print(f"골든셋 {len(GOLDEN_CASES)}개 평가 시작...\n")
    scores = _evaluate_all()

    md = _build_markdown(scores)
    print("\n" + md)

    stamp = date.today().strftime("%Y%m%d")
    md_path = f"eval_report_{stamp}.md"
    png_path = f"eval_report_{stamp}.png"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md + "\n")
    print(f"\n리포트 저장: {md_path}")

    try:
        _render_chart(scores, png_path)
    except Exception as exc:  # 차트 실패가 리포트 전체를 막지 않게
        print(f"⚠️ 차트 생성 실패 ({type(exc).__name__}: {exc})", file=sys.stderr)

    # 순서 일관성이 깨지면 non-zero 종료 — CI 품질 게이트로 쓸 수 있게.
    # (리포트는 위에서 이미 저장됐으므로 실패해도 증거물은 남는다.)
    if not _ordering_ok(scores):
        print("\n❌ 순서 일관성 실패 — judge 변별 결함. (exit 2)", file=sys.stderr)
        return 2
    print("\n✅ 순서 일관성 통과.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
