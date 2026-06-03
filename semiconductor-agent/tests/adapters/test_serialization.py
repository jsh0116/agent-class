"""serialize_eval domain 포함 검증 — 영속 데이터에서 도메인이 보여야 한다."""
from semiconductor.adapters.nodes.mock_interviewer.serialization import (
    deserialize_eval,
    serialize_eval,
)
from semiconductor.domain.entities import EvaluationResult


def _eval() -> EvaluationResult:
    return EvaluationResult(
        accuracy_score=30, depth_score=20, terminology_score=20, total_score=70,
        feedback="f", strong_points=["s"], weak_points=["w"], question="Vth란?",
    )


def test_domain을_주면_직렬화_dict에_포함된다():
    d = serialize_eval(_eval(), domain="소자")
    assert d["domain"] == "소자"


def test_domain_생략시_None으로_직렬화된다():
    # 하위호환 — domain 인자 없이도 동작
    d = serialize_eval(_eval())
    assert d["domain"] is None


def test_round_trip은_평가_본문을_보존한다():
    d = serialize_eval(_eval(), domain="공정")
    back = deserialize_eval(d)
    assert back.total_score == 70
    assert back.question == "Vth란?"
