"""judge 품질 골든셋 검증 — 평가 파이프라인이 우수/보통/미흡을 변별하는지 측정.

`evaluations` fixture가 judge → adaptive critic skip → 최종 점수, 즉 사용자가
graph에서 실제로 받는 점수를 계산한다 (judge 단독이 아님).

실행:
    uv run pytest -m eval tests/eval/ -v        # OPENAI_API_KEY + ANTHROPIC_API_KEY 필요

두 가지를 검증한다:
  1. band: 각 답변 점수가 라벨 등급의 느슨한 점수대 안에 있는가 (보조 지표)
  2. ordering: 같은 질문에서 우수 > 보통 > 미흡 순서가 유지되는가 (주지표)

ordering이 진짜 변별력 신호다 — LLM 절대 점수는 흔들려도 상대 순위는 안정적이다.
"""
from __future__ import annotations

import pytest

from tests.eval.golden_set import GOLDEN_CASES, cases_by_family

pytestmark = pytest.mark.eval

_FAMILIES = sorted(cases_by_family().keys())


@pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda c: c.case_id)
def test_score_within_band(case, evaluations):
    """각 답변 점수가 라벨 등급의 점수대 안인지 (느슨한 sanity 가드)."""
    score = evaluations[case.case_id]
    assert case.min_total <= score <= case.max_total, (
        f"[{case.case_id}] 등급={case.expected_grade} "
        f"기대 {case.min_total}~{case.max_total}, 실제 {score}. 근거: {case.rationale}"
    )


@pytest.mark.parametrize("family", _FAMILIES)
def test_ordering_consistency(family, evaluations):
    """같은 질문에서 우수 > 보통 > 미흡 점수 순서가 유지되는가 (주지표)."""
    cases = cases_by_family()[family]
    strong = evaluations[cases["우수"].case_id]
    mid = evaluations[cases["보통"].case_id]
    weak = evaluations[cases["미흡"].case_id]

    assert strong > mid, (
        f"[{family}] 우수({strong})가 보통({mid})보다 높아야 함 — judge 변별 실패"
    )
    assert mid > weak, (
        f"[{family}] 보통({mid})이 미흡({weak})보다 높아야 함 — judge 변별 실패"
    )


def test_strong_answers_clearly_separated(evaluations):
    """우수 답변 평균이 미흡 평균보다 최소 25점 이상 높은지 — 전반적 변별폭."""
    by_family = cases_by_family()
    strong_avg = sum(
        evaluations[f["우수"].case_id] for f in by_family.values()
    ) / len(by_family)
    weak_avg = sum(
        evaluations[f["미흡"].case_id] for f in by_family.values()
    ) / len(by_family)
    gap = strong_avg - weak_avg
    assert gap >= 25, (
        f"우수 평균({strong_avg:.1f}) - 미흡 평균({weak_avg:.1f}) = {gap:.1f}점. "
        f"변별폭이 25점 미만이면 judge가 품질을 충분히 구분하지 못하는 것."
    )
