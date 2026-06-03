"""Adaptive critic skip — judge 1차 평가 점수에 따라 critic 2차 검증을 조건부 호출.

확신 영역(매우 높거나 매우 낮은 점수)은 critic을 생략해 평가 비용을 절감한다.
회색지대(기본 31~84)만 critic을 호출한다.

이 모듈이 skip 판정의 **단일 소스**다. graph 노드(mock_critic_node)와
eval 골든셋이 모두 이 로직을 공유해야, "사용자가 보는 점수"와 "검증하는 점수"가
갈라지지 않는다. (과거: 노드에만 인라인 → 골든셋이 judge만 검증하는 결함 발생)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

from semiconductor.application.use_cases.critique_evaluation import CritiqueEvaluationUseCase
from semiconductor.domain.entities import EvaluationResult, Question
from semiconductor.domain.ports import ILLMCritic


@dataclass(frozen=True)
class CriticSkipConfig:
    skip_high: int = 85   # 이 점수 이상 → 우수 확신 → critic 생략
    skip_low: int = 30    # 이 점수 이하 → 미흡 확신 → critic 생략
    disabled: bool = False  # True면 항상 critic 호출 (디버깅·일관성)

    @classmethod
    def from_env(cls) -> "CriticSkipConfig":
        """그래프 노드와 동일한 env 변수에서 설정 로드."""
        return cls(
            skip_high=int(os.getenv("CRITIC_SKIP_HIGH", "85")),
            skip_low=int(os.getenv("CRITIC_SKIP_LOW", "30")),
            disabled=os.getenv("LLM_DISABLE_CRITIC_SKIP") == "1",
        )


def should_run_critic(total_score: int, config: CriticSkipConfig) -> bool:
    """회색지대(skip_low < score < skip_high)이면 critic 호출, 확신 영역이면 생략."""
    if config.disabled:
        return True
    return not (total_score >= config.skip_high or total_score <= config.skip_low)


def apply_adaptive_critic(
    initial: EvaluationResult,
    *,
    question: Question,
    user_answer: str,
    critic_factory: Callable[[], ILLMCritic],
    config: CriticSkipConfig,
) -> EvaluationResult:
    """1차 평가에 adaptive critic을 적용해 최종 평가를 반환.

    회색지대면 critic.critique()를 거친 값, 확신 영역이면 1차 평가 그대로.
    critic_factory는 회색지대일 때만 호출 — 확신 영역에선 critic LLM을 생성조차
    하지 않아 불필요한 비용·API 키 요구를 피한다.
    critic 실패는 CritiqueEvaluationUseCase가 원본 보존으로 흡수한다.
    """
    if should_run_critic(initial.total_score, config):
        return CritiqueEvaluationUseCase(llm_critic=critic_factory()).execute(
            question=question,
            user_answer=user_answer,
            initial_evaluation=initial,
        )
    return initial
