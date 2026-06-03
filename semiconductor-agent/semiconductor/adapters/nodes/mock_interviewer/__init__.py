"""Mock Interviewer package — 3-phase state machine.

  mock_present_node  → 질문 출제 (phase: present → evaluate)
  mock_evaluate_node → judge 1차 평가 (pending_evaluation 저장)
  mock_critic_node   → critic 2차 검증 (조건부) + 출력 + 다음 질문 진행

기존 monolithic file을 SOLID·테스트 격리 위해 분리. graph.py / 테스트는
이 package import path로 그대로 호환됨.
"""
from semiconductor.adapters.nodes.mock_interviewer.critic import (
    make_mock_critic_node,
    mock_critic_node,
)
from semiconductor.adapters.nodes.mock_interviewer.evaluate import (
    make_mock_evaluate_node,
    mock_evaluate_node,
)
from semiconductor.adapters.nodes.mock_interviewer.present import (
    make_mock_present_node,
    mock_present_node,
)
from semiconductor.adapters.nodes.mock_interviewer.serialization import (
    deserialize_eval,
    serialize_eval,
)

# Backward-compat aliases (tests imported the underscored names)
_serialize_eval = serialize_eval
_deserialize_eval = deserialize_eval

__all__ = [
    "mock_present_node",
    "mock_evaluate_node",
    "mock_critic_node",
    "make_mock_present_node",
    "make_mock_evaluate_node",
    "make_mock_critic_node",
    "serialize_eval",
    "deserialize_eval",
]
