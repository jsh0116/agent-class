"""adaptive_critic 유스케이스 단위 테스트 — 순수 로직 + critic 호출 결정.

LLM 없이 검증한다. should_run_critic은 순수 함수, apply_adaptive_critic은
critic_factory를 mock으로 주입해 lazy 호출·graceful degradation을 검증한다.
이 로직이 graph 노드와 eval 골든셋의 단일 소스이므로 회귀 가드가 중요하다.
"""
from semiconductor.application.use_cases.adaptive_critic import (
    CriticSkipConfig,
    apply_adaptive_critic,
    should_run_critic,
)
from semiconductor.domain.entities import EvaluationResult, Question
from semiconductor.domain.ports import ILLMCritic

_DEFAULT = CriticSkipConfig()  # skip_high=85, skip_low=30


def _eval(total: int) -> EvaluationResult:
    """주어진 총점의 EvaluationResult (40/30/30 분배는 검증과 무관하게 합만 맞춤)."""
    acc = min(total, 40)
    rem = total - acc
    depth = min(rem, 30)
    term = rem - depth
    return EvaluationResult(
        accuracy_score=acc,
        depth_score=depth,
        terminology_score=term,
        total_score=total,
        feedback="",
        strong_points=[],
        weak_points=[],
        question="q",
    )


_Q = Question(domain="소자", question="질문", key_points=[])


# ── should_run_critic (순수 결정 로직) ────────────────────────────

def test_회색지대_점수면_critic을_호출한다():
    # given 31~84 사이 점수
    # when & then
    assert should_run_critic(50, _DEFAULT) is True
    assert should_run_critic(31, _DEFAULT) is True
    assert should_run_critic(84, _DEFAULT) is True


def test_우수_확신_영역이면_critic을_생략한다():
    assert should_run_critic(85, _DEFAULT) is False
    assert should_run_critic(100, _DEFAULT) is False


def test_미흡_확신_영역이면_critic을_생략한다():
    assert should_run_critic(30, _DEFAULT) is False
    assert should_run_critic(0, _DEFAULT) is False


def test_disabled면_점수와_무관하게_항상_호출한다():
    cfg = CriticSkipConfig(disabled=True)
    assert should_run_critic(100, cfg) is True
    assert should_run_critic(0, cfg) is True
    assert should_run_critic(50, cfg) is True


def test_커스텀_임계값을_반영한다():
    cfg = CriticSkipConfig(skip_high=90, skip_low=20)
    assert should_run_critic(88, cfg) is True   # 기본이면 생략됐을 점수
    assert should_run_critic(25, cfg) is True
    assert should_run_critic(90, cfg) is False
    assert should_run_critic(20, cfg) is False


def test_from_env가_env_변수를_읽는다(monkeypatch):
    monkeypatch.setenv("CRITIC_SKIP_HIGH", "70")
    monkeypatch.setenv("CRITIC_SKIP_LOW", "40")
    monkeypatch.setenv("LLM_DISABLE_CRITIC_SKIP", "1")
    cfg = CriticSkipConfig.from_env()
    assert cfg.skip_high == 70
    assert cfg.skip_low == 40
    assert cfg.disabled is True


# ── apply_adaptive_critic (lazy 호출 + degradation) ───────────────

class _SpyCritic(ILLMCritic):
    """호출 여부와 인자를 기록하는 critic. critique는 점수를 +5 보정한 결과 반환."""

    def __init__(self):
        self.called = False

    def critique(self, question, user_answer, initial_evaluation):
        self.called = True
        return _eval(min(initial_evaluation.total_score + 5, 100))


class _BoomCritic(ILLMCritic):
    def critique(self, question, user_answer, initial_evaluation):
        raise RuntimeError("provider down")


def test_확신_영역이면_critic_factory를_호출하지_않는다():
    # given 우수 확신 점수
    factory_calls = []

    def factory():
        factory_calls.append(1)
        return _SpyCritic()

    initial = _eval(90)

    # when
    final = apply_adaptive_critic(
        initial, question=_Q, user_answer="답변",
        critic_factory=factory, config=_DEFAULT,
    )

    # then critic LLM 자체가 생성되지 않아야 한다 (불필요 비용·키 회피)
    assert factory_calls == []
    assert final.total_score == 90  # 1차 평가 그대로


def test_회색지대면_critic_결과를_반환한다():
    # given 회색지대 점수
    spy = _SpyCritic()
    initial = _eval(60)

    # when
    final = apply_adaptive_critic(
        initial, question=_Q, user_answer="답변",
        critic_factory=lambda: spy, config=_DEFAULT,
    )

    # then critic이 호출되고 보정된 점수가 반환된다
    assert spy.called is True
    assert final.total_score == 65


def test_critic_실패해도_1차_평가를_보존한다():
    # given critic이 예외를 던지는 상황
    initial = _eval(55)

    # when
    final = apply_adaptive_critic(
        initial, question=_Q, user_answer="답변",
        critic_factory=_BoomCritic, config=_DEFAULT,
    )

    # then graceful degradation — 원본 평가 그대로
    assert final.total_score == 55
