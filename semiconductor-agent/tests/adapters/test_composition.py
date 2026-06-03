"""Composition root 검증 — monkeypatch 없이 Dependencies로 대체 서비스 주입.

#7(어댑터 노드 인프라 직접생성)의 수정 증명: 노드가 인프라 싱글톤에 묶여 있으면
이런 주입이 불가능해 모듈 글로벌을 patch해야 했다. 이제 factory 주입으로 가능하다.
"""
from langchain_core.messages import HumanMessage

from semiconductor.adapters.composition import Dependencies
from semiconductor.adapters.graph import create_app
from semiconductor.adapters.nodes.mock_interviewer import make_mock_evaluate_node
from semiconductor.adapters.state import create_initial_state
from semiconductor.domain.entities import EvaluationResult
from semiconductor.domain.ports import ILLMJudge
from semiconductor.infrastructure.llm import LangChainLLMService


class _FakeJudge(ILLMJudge):
    """고정 점수를 반환하는 가짜 judge — 실제 LLM 호출 없음."""

    def evaluate(self, question, user_answer) -> EvaluationResult:
        return EvaluationResult(
            accuracy_score=36, depth_score=27, terminology_score=27, total_score=90,
            feedback="고정", strong_points=["s"], weak_points=["w"], question=question.question,
        )


def _evaluate_state() -> dict:
    s = dict(create_initial_state(company="samsung_ds"))
    s["current_question_domain"] = "소자"
    s["current_question_text"] = "Vth란?"
    s["current_question_key_points"] = ["채널 형성 전압"]
    s["messages"] = [HumanMessage(content="제 답변입니다")]
    return s


def test_주입한_judge_factory를_노드가_사용한다():
    # given patch 없이 가짜 judge factory를 주입
    node = make_mock_evaluate_node(judge_factory=_FakeJudge)

    # when
    out = node(_evaluate_state())

    # then 가짜 judge의 고정 점수가 그대로 직렬화된다
    assert out["pending_evaluation"]["total_score"] == 90
    assert out["pending_evaluation"]["domain"] == "소자"


def test_create_app가_deps를_받아_컴파일된다():
    # given 가짜 서비스로 구성한 deps
    deps = Dependencies(judge_factory=_FakeJudge)

    # when
    app, state = create_app(deps=deps)

    # then 그래프가 정상 컴파일되고 초기 상태를 반환
    assert app is not None
    assert state["company"] == "samsung_ds"


def test_dependencies_기본값은_실서비스_factory를_가리킨다():
    d = Dependencies()
    assert d.judge_factory is LangChainLLMService.judge
    assert d.critic_factory is LangChainLLMService.critic
