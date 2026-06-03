"""eval 스위트 전용 fixture/guard.

골든셋은 **사용자가 실제로 보는 점수**(judge → adaptive critic skip → 최종)를
검증한다. judge만 호출하면 31~84점 구간에서 critic이 바꾸는 값을 놓치므로,
graph 노드와 동일한 apply_adaptive_critic 로직을 거친다.

필요한 API 키는 judge·critic의 실제 provider에 따라 달라지므로(기본 tier는
judge=openai, critic=anthropic), 둘 중 하나라도 키가 없으면 skip한다.
"""
from __future__ import annotations

import os

import pytest


def _missing_keys() -> list[str]:
    """judge·critic가 쓰는 provider 중 키가 없는 env 이름 목록.

    provider→키 매핑은 llm_service의 단일 소스를 공유한다(eval_judge.py와 동일).
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


def pytest_collection_modifyitems(config, items):
    """judge/critic provider 키가 하나라도 없으면 eval 마커 테스트 skip."""
    missing = _missing_keys()
    if not missing:
        return
    skip = pytest.mark.skip(reason=f"eval 스위트 skip — 필요한 키 미설정: {', '.join(missing)}")
    for item in items:
        if "eval" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def evaluations():
    """골든셋 전체를 judge→adaptive critic 전체 파이프라인으로 1회 평가하고
    case_id → 최종 total_score 캐시.

    이게 사용자가 graph에서 실제로 받는 점수와 동일한 경로다.
    """
    from semiconductor.application.use_cases.adaptive_critic import (
        CriticSkipConfig,
        apply_adaptive_critic,
    )
    from semiconductor.infrastructure.llm import LangChainLLMService
    from tests.eval.golden_set import GOLDEN_CASES

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
    return scores
