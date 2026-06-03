"""평가 골든셋 — judge LLM의 변별력·일관성을 검증하는 라벨링된 답변 모음.

이 파일이 "교수 초과" 주장의 증거 기반이다. 각 도메인마다 같은 질문에 대해
우수/보통/미흡 3개 답변을 두고, judge가 그 순서를 일관되게 매기는지 측정한다.

설계 원칙:
  - 절대 점수가 아니라 **순서 일관성**(우수 > 보통 > 미흡)이 진짜 변별력 지표다.
    LLM은 비결정적이라 절대 점수는 흔들리지만 상대 순위는 훨씬 안정적이다.
  - 점수대(min/max)는 느슨한 sanity 가드일 뿐, 경계에서 겹쳐도 된다.
  - 우수 답변은 모범답안 수준(원리+수식+전문용어), 미흡은 흔한 오개념/모호함에서 만든다.

같은 question_family를 가진 3개 케이스가 한 묶음 = 1개 순서 검증 단위.
"""
from __future__ import annotations

from dataclasses import dataclass

from semiconductor.domain.entities import Question


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    question_family: str  # 같은 family = 같은 질문, 순서 비교 단위
    question: Question
    answer: str
    expected_grade: str   # 우수 | 보통 | 미흡
    min_total: int        # 느슨한 하한 (sanity)
    max_total: int        # 느슨한 상한 (sanity)
    rationale: str        # 왜 이 등급인지 (라벨 근거)


# 점수대 프리셋 — 경계에서 의도적으로 겹친다 (band는 보조, 순서가 주지표).
_BAND = {
    "우수": (75, 100),
    "보통": (45, 78),
    "미흡": (0, 45),
}


def _case(case_id, family, question, answer, grade, rationale) -> GoldenCase:
    lo, hi = _BAND[grade]
    return GoldenCase(case_id, family, question, answer, grade, lo, hi, rationale)


# ── 소자: MOSFET Vth 온도 의존성 ──────────────────────────────────
_Q_VTH = Question(
    domain="소자",
    question="MOSFET의 문턱전압(Vth)이 무엇인지 설명하고, 온도가 올라가면 Vth가 "
    "어떻게 변하는지 이유와 함께 설명하세요.",
    key_points=[
        "Vth: 채널이 형성되기 시작하는 최소 게이트 전압",
        "온도 상승 → 진성 캐리어 농도 ni 증가 → 페르미 전위 Φf 감소 → Vth 감소",
        "이동도 감소(phonon scattering)와 Vth 변화 구분",
    ],
)

# ── 공정: CVD vs ALD ──────────────────────────────────────────────
_Q_ALD = Question(
    domain="공정",
    question="CVD와 ALD의 증착 메커니즘 차이를 설명하고, ALD가 고종횡비 구조에 "
    "유리한 이유를 말씀해 주세요.",
    key_points=[
        "CVD: 전구체 동시 공급, gas-phase 반응",
        "ALD: 전구체 A→purge→B→purge, self-limiting 표면 반응",
        "surface saturation → 고종횡비 측벽까지 conformal (step coverage ~100%)",
    ],
)

# ── 회로: DRAM 센스앰프 ───────────────────────────────────────────
_Q_SA = Question(
    domain="회로",
    question="DRAM 센스앰프의 동작 원리를 설명하고, 오프셋(offset)이 작아야 하는 "
    "이유를 말씀해 주세요.",
    key_points=[
        "비트라인 미세 전압차를 차동 증폭",
        "크로스커플 인버터의 positive feedback으로 풀스윙",
        "오프셋이 신호보다 크면 오독 → 트랜지스터 매칭·offset cancellation 필요",
    ],
)

# ── 트렌드: HBM ───────────────────────────────────────────────────
_Q_HBM = Question(
    domain="트렌드",
    question="HBM이 GDDR 대비 갖는 구조적 이점과 한계를 설명하세요.",
    key_points=[
        "TSV로 DRAM die 수직 적층 + 넓은 I/O(스택당 1024-bit)",
        "낮은 클럭으로도 높은 대역폭 + GB당 전력 효율 우수",
        "한계: 인터포저(CoWoS) 패키징 비용·발열·수율",
    ],
)


GOLDEN_CASES: list[GoldenCase] = [
    # ── 소자 ──
    _case(
        "device-vth-strong", "device-vth", _Q_VTH,
        "Vth는 게이트 아래에 반전층(채널)이 형성되기 시작하는 최소 게이트 전압입니다. "
        "Vth = Φms - Qf/Cox + 2Φf + √(2·εsi·q·Na·2Φf)/Cox 로 표현됩니다. 온도가 올라가면 "
        "진성 캐리어 농도 ni가 지수적으로 증가하고, 페르미 전위 Φf = (kT/q)·ln(Na/ni)가 "
        "감소합니다. 2Φf 항과 공핍전하 항이 함께 줄어들어 Vth는 감소하며, 대략 "
        "-1~-3 mV/°C 수준입니다. 한편 캐리어 이동도는 phonon scattering 증가로 감소하지만 "
        "이는 Vth가 아니라 구동 전류에 영향을 줍니다. 단채널에서는 DIBL·roll-off가 겹쳐 "
        "Vth 변화가 더 복잡해집니다.",
        "우수",
        "정의·수식·온도 의존 원리(Φf, ni)·이동도와의 구분·단채널 효과까지 포함한 만점급 답변",
    ),
    _case(
        "device-vth-mid", "device-vth", _Q_VTH,
        "Vth는 트랜지스터가 켜지기 시작하는 전압입니다. 온도가 올라가면 Vth는 "
        "낮아집니다. 열에너지 때문에 캐리어가 더 쉽게 움직여서 더 낮은 전압에서도 "
        "채널이 만들어지기 때문입니다.",
        "보통",
        "방향(감소)은 맞지만 Φf·ni 원리나 수식 없이 직관적 설명에 그침",
    ),
    _case(
        "device-vth-weak", "device-vth", _Q_VTH,
        "Vth는 문턱전압입니다. 온도가 올라가면 저항이 커지니까 Vth도 높아질 것 "
        "같습니다. 정확한 이유는 잘 모르겠습니다.",
        "미흡",
        "방향이 틀렸고(증가로 답함) 원리 설명 없음",
    ),

    # ── 공정 ──
    _case(
        "proc-ald-strong", "proc-ald", _Q_ALD,
        "CVD는 두 전구체를 동시에 공급해 기상(gas-phase)에서 반응시켜 박막을 쌓습니다. "
        "반면 ALD는 전구체 A 주입 → 퍼지 → 전구체 B 주입 → 퍼지의 사이클을 반복하는 "
        "self-limiting 표면 반응으로, 한 사이클당 원자층 수준의 두께를 정밀하게 증착합니다. "
        "표면이 saturation에 도달하면 더 이상 흡착이 일어나지 않기 때문에, sticking "
        "probability가 낮은 전구체라도 고종횡비(>50:1) trench의 측벽 깊은 곳까지 균일하게 "
        "흡착되어 step coverage가 거의 100%에 가깝습니다. 그래서 DRAM 커패시터나 3D NAND "
        "같은 깊은 구조의 conformal 증착에 ALD가 필수적입니다.",
        "우수",
        "메커니즘(self-limiting)·saturation 원리·conformality·실제 응용까지 정확",
    ),
    _case(
        "proc-ald-mid", "proc-ald", _Q_ALD,
        "CVD는 한 번에 증착하고 ALD는 한 층씩 순서대로 쌓습니다. ALD가 더 얇고 균일하게 "
        "올릴 수 있어서 깊고 좁은 구조에 더 적합합니다.",
        "보통",
        "차이의 방향은 맞지만 self-limiting·saturation 같은 핵심 원리 누락",
    ),
    _case(
        "proc-ald-weak", "proc-ald", _Q_ALD,
        "CVD랑 ALD는 둘 다 박막을 만드는 공정입니다. ALD가 더 최신이고 좋은 방법입니다. "
        "구체적인 차이는 잘 기억이 안 납니다.",
        "미흡",
        "메커니즘 차이를 전혀 설명하지 못함",
    ),

    # ── 회로 ──
    _case(
        "circuit-sa-strong", "circuit-sa", _Q_SA,
        "센스앰프는 읽기 동작에서 비트라인에 나타나는 수십~수백 mV의 미세한 전압차를 "
        "차동으로 증폭합니다. 보통 비트라인을 Vdd/2로 프리차지한 뒤 셀의 charge sharing으로 "
        "생긴 미세 차이를, 크로스커플된 두 인버터의 positive feedback이 빠르게 풀스윙(0/Vdd)으로 "
        "키웁니다. 이때 두 입력 트랜지스터의 문턱전압 미스매치 등으로 생기는 오프셋이 신호 "
        "전압보다 크면 0과 1을 거꾸로 읽는 오독이 발생합니다. 그래서 트랜지스터 매칭(레이아웃 "
        "대칭, 큰 면적)과 offset cancellation 기법으로 오프셋을 신호 마진 이하로 낮춰야 합니다.",
        "우수",
        "프리차지·charge sharing·positive feedback·오프셋과 신호 마진 관계까지 정확",
    ),
    _case(
        "circuit-sa-mid", "circuit-sa", _Q_SA,
        "센스앰프는 비트라인의 작은 전압 차이를 증폭해서 셀에 저장된 값이 0인지 1인지 "
        "판별하는 회로입니다. 오프셋이 크면 잘못 읽을 수 있어서 작아야 합니다.",
        "보통",
        "기능과 오프셋 영향은 맞지만 feedback 동작 원리·매칭 대책 없음",
    ),
    _case(
        "circuit-sa-weak", "circuit-sa", _Q_SA,
        "센스앰프는 신호를 증폭하는 회로이고 메모리에서 데이터를 읽을 때 씁니다. "
        "오프셋은 잘 모르겠습니다.",
        "미흡",
        "동작 원리·오프셋 질문 모두 미답",
    ),

    # ── 트렌드 ──
    _case(
        "trend-hbm-strong", "trend-hbm", _Q_HBM,
        "HBM은 여러 DRAM die를 TSV(Through-Silicon Via)로 수직 적층하고, 스택당 1024-bit급의 "
        "매우 넓은 I/O를 제공합니다. 덕분에 GDDR보다 낮은 동작 클럭으로도 훨씬 높은 총 "
        "대역폭을 얻고, 데이터 이동 거리가 짧아 GB당 전력 효율도 우수합니다. 그래서 HBM3E가 "
        "AI 가속기(GPU)의 표준 메모리로 자리잡았습니다. 다만 로직 die 옆에 실리콘 인터포저로 "
        "붙이는 2.5D(CoWoS) 패키징이 필요해 비용이 높고, 적층 하부 die의 발열 방출과 TSV 수율이 "
        "수율·원가의 핵심 한계입니다.",
        "우수",
        "TSV·광폭 I/O·전력효율·CoWoS·발열/수율 한계까지 균형 있게 정확",
    ),
    _case(
        "trend-hbm-mid", "trend-hbm", _Q_HBM,
        "HBM은 메모리를 위로 쌓아서 대역폭이 매우 높은 메모리입니다. GDDR보다 빠르고 "
        "전력도 적게 써서 요즘 AI 칩에 많이 들어갑니다.",
        "보통",
        "이점 방향은 맞지만 TSV·인터포저·한계(비용/발열) 누락",
    ),
    _case(
        "trend-hbm-weak", "trend-hbm", _Q_HBM,
        "HBM은 고대역폭 메모리라서 좋은 메모리입니다. 비싸다고 들었습니다.",
        "미흡",
        "구조적 이점·한계 모두 설명 없음",
    ),
]


# question_family → 등급별 case_id (순서 검증 테스트가 사용)
def cases_by_family() -> dict[str, dict[str, GoldenCase]]:
    out: dict[str, dict[str, GoldenCase]] = {}
    for c in GOLDEN_CASES:
        out.setdefault(c.question_family, {})[c.expected_grade] = c
    return out
