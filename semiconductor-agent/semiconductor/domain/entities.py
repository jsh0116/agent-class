"""Domain entities — pure business objects, no infrastructure dependencies."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

VALID_DOMAINS = frozenset(("소자", "공정", "회로", "트렌드"))


@dataclass(frozen=True)
class Question:
    domain: str
    question: str
    key_points: list[str]

    def __post_init__(self):
        if self.domain not in VALID_DOMAINS:
            raise ValueError(f"도메인은 {VALID_DOMAINS} 중 하나여야 합니다. 받은 값: {self.domain!r}")
        if not self.question.strip():
            raise ValueError("질문 텍스트는 비어있을 수 없습니다.")


class EvaluationResult:
    """LLM judge output for a single interview answer.

    Scoring rubric:
      accuracy_score:    0–40  (정확성)
      depth_score:       0–30  (깊이)
      terminology_score: 0–30  (전문 용어)
      total_score:       0–100 (= sum of above)
    """

    def __init__(
        self,
        accuracy_score: int,
        depth_score: int,
        terminology_score: int,
        total_score: int,
        feedback: str,
        strong_points: list[str],
        weak_points: list[str],
        question: str,
        model_answer: str = "",
        specialist_commentary: str = "",
        follow_up_question: str = "",
    ) -> None:
        if not (0 <= accuracy_score <= 40):
            raise ValueError(f"accuracy_score는 0–40 범위여야 합니다. 받은 값: {accuracy_score}")
        if not (0 <= depth_score <= 30):
            raise ValueError(f"depth_score는 0–30 범위여야 합니다. 받은 값: {depth_score}")
        if not (0 <= terminology_score <= 30):
            raise ValueError(f"terminology_score는 0–30 범위여야 합니다. 받은 값: {terminology_score}")
        expected_total = accuracy_score + depth_score + terminology_score
        if total_score != expected_total:
            raise ValueError(
                f"total_score({total_score})가 부분 점수의 합({expected_total})과 다릅니다."
            )
        self.accuracy_score = accuracy_score
        self.depth_score = depth_score
        self.terminology_score = terminology_score
        self.total_score = total_score
        self.feedback = feedback
        self.strong_points = list(strong_points)
        self.weak_points = list(weak_points)
        self.question = question
        self.model_answer = model_answer
        self.specialist_commentary = specialist_commentary
        self.follow_up_question = follow_up_question

    @property
    def grade(self) -> str:
        if self.total_score >= 80:
            return "우수"
        if self.total_score >= 50:
            return "보통"
        return "미흡"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EvaluationResult):
            return NotImplemented
        return (
            self.accuracy_score == other.accuracy_score
            and self.depth_score == other.depth_score
            and self.terminology_score == other.terminology_score
            and self.total_score == other.total_score
            and self.question == other.question
        )


@dataclass
class DiagnosticResult:
    domain_scores: dict[str, int]  # {"소자": 75, "공정": 42, ...}
    weak_topics: list[str]
    strong_topics: list[str]
    recommended_next: str

    def __post_init__(self):
        for domain, score in self.domain_scores.items():
            if not (0 <= score <= 100):
                raise ValueError(f"도메인 점수는 0–100 범위여야 합니다. {domain}: {score}")

    @property
    def weakest_domain(self) -> Optional[str]:
        if not self.domain_scores:
            return None
        return min(self.domain_scores, key=lambda d: self.domain_scores[d])


# ── 자소서 (Essay Coach) ─────────────────────────────────────────

VALID_ESSAY_COMPANIES = frozenset(("samsung_ds", "sk_hynix"))
VALID_ESSAY_ITEMS = frozenset(("지원동기", "직무역량", "성장과정", "갈등극복"))


@dataclass(frozen=True)
class EssayPrompt:
    company: str       # samsung_ds | sk_hynix
    item: str          # 지원동기 | 직무역량 | 성장과정 | 갈등극복
    description: str   # 회사가 묻는 의도 (system이 사용자에게 보여줌)
    word_limit: int    # 한국어 char 수 제한 (예: 1500)

    def __post_init__(self):
        if self.company not in VALID_ESSAY_COMPANIES:
            raise ValueError(f"회사는 {VALID_ESSAY_COMPANIES} 중 하나여야 합니다.")
        if self.item not in VALID_ESSAY_ITEMS:
            raise ValueError(f"항목은 {VALID_ESSAY_ITEMS} 중 하나여야 합니다.")
        if self.word_limit <= 0:
            raise ValueError(f"word_limit은 양수여야 합니다: {self.word_limit}")


class EssayEvaluation:
    """자소서 첨삭 결과.

    Rubric (총 100점):
      fit_score (0-30):         회사 인재상 부합도
      structure_score (0-25):   구조 (서론-본론-결론, STAR 등)
      specificity_score (0-25): 구체성 (수치, 사례, 액션)
      writing_score (0-20):     한국어 작문 (자연스러움, 어휘)
    """

    def __init__(
        self,
        fit_score: int,
        structure_score: int,
        specificity_score: int,
        writing_score: int,
        total_score: int,
        feedback: str,
        strong_points: list[str],
        weak_points: list[str],
        revised_excerpt: str = "",
        culture_alignment: str = "",
    ) -> None:
        if not (0 <= fit_score <= 30):
            raise ValueError(f"fit_score는 0–30 범위여야 합니다: {fit_score}")
        if not (0 <= structure_score <= 25):
            raise ValueError(f"structure_score는 0–25 범위여야 합니다: {structure_score}")
        if not (0 <= specificity_score <= 25):
            raise ValueError(f"specificity_score는 0–25 범위여야 합니다: {specificity_score}")
        if not (0 <= writing_score <= 20):
            raise ValueError(f"writing_score는 0–20 범위여야 합니다: {writing_score}")
        expected = fit_score + structure_score + specificity_score + writing_score
        if total_score != expected:
            raise ValueError(f"total_score({total_score})가 부분 점수의 합({expected})과 다릅니다.")
        self.fit_score = fit_score
        self.structure_score = structure_score
        self.specificity_score = specificity_score
        self.writing_score = writing_score
        self.total_score = total_score
        self.feedback = feedback
        self.strong_points = list(strong_points)
        self.weak_points = list(weak_points)
        self.revised_excerpt = revised_excerpt
        self.culture_alignment = culture_alignment

    @property
    def grade(self) -> str:
        if self.total_score >= 80:
            return "우수"
        if self.total_score >= 50:
            return "보통"
        return "미흡"


# ── 적성검사 (GSAT / SKCT) ────────────────────────────────────────

VALID_APTITUDE_TESTS = frozenset(("GSAT", "SKCT"))
VALID_APTITUDE_DOMAINS = frozenset(("수리", "추리", "언어", "공간"))


@dataclass(frozen=True)
class AptitudeQuestion:
    """객관식 적성검사 문제. LLM 미사용 — 정답·해설 모두 정적."""

    test_type: str           # GSAT | SKCT
    domain: str              # 수리 | 추리 | 언어 | 공간
    question: str
    choices: list[str]       # 보통 4개
    correct_index: int       # 0-based
    explanation: str         # 풀이 (정답·오답 이유 모두 포함)

    def __post_init__(self):
        if self.test_type not in VALID_APTITUDE_TESTS:
            raise ValueError(f"test_type은 {VALID_APTITUDE_TESTS} 중 하나여야 합니다.")
        if self.domain not in VALID_APTITUDE_DOMAINS:
            raise ValueError(f"domain은 {VALID_APTITUDE_DOMAINS} 중 하나여야 합니다.")
        if not self.question.strip():
            raise ValueError("question은 비어있을 수 없습니다.")
        if not (2 <= len(self.choices) <= 5):
            raise ValueError(f"choices는 2~5개여야 합니다. 받은 값: {len(self.choices)}")
        if not (0 <= self.correct_index < len(self.choices)):
            raise ValueError(f"correct_index가 범위를 벗어남: {self.correct_index}")


@dataclass
class AptitudeResult:
    test_type: str
    domain: str
    question: str
    user_choice: int          # 0-based, -1 if invalid
    correct_index: int
    explanation: str

    @property
    def is_correct(self) -> bool:
        return self.user_choice == self.correct_index


# ── 인성면접 (Behavioral STAR) ───────────────────────────────────

VALID_COMPETENCIES = frozenset(("리더십", "문제해결", "협력", "도전", "갈등극복"))


@dataclass(frozen=True)
class BehavioralQuestion:
    company: str           # samsung_ds | sk_hynix
    question: str          # "팀에서 갈등을 극복한 경험..."
    competency: str        # 평가하려는 역량 (리더십·문제해결·협력 등)

    def __post_init__(self):
        if self.company not in VALID_ESSAY_COMPANIES:
            raise ValueError(f"회사는 {VALID_ESSAY_COMPANIES} 중 하나여야 합니다.")
        if self.competency not in VALID_COMPETENCIES:
            raise ValueError(f"competency는 {VALID_COMPETENCIES} 중 하나여야 합니다.")
        if not self.question.strip():
            raise ValueError("질문 텍스트는 비어있을 수 없습니다.")


class BehavioralEvaluation:
    """STAR 기법 + 회사 인재상 평가.

    Rubric (총 100점):
      situation_score (0-20): Situation 명확도
      task_score (0-20):      Task 명확도
      action_score (0-30):    Action 구체성 (가장 중요)
      result_score (0-20):    Result 정량화·임팩트
      culture_fit (0-10):     회사 인재상·역량 매칭
    """

    def __init__(
        self,
        situation_score: int,
        task_score: int,
        action_score: int,
        result_score: int,
        culture_fit: int,
        total_score: int,
        feedback: str,
        strong_points: list[str],
        weak_points: list[str],
        improved_answer: str = "",
    ) -> None:
        ranges = (
            ("situation_score", situation_score, 20),
            ("task_score", task_score, 20),
            ("action_score", action_score, 30),
            ("result_score", result_score, 20),
            ("culture_fit", culture_fit, 10),
        )
        for name, val, max_v in ranges:
            if not (0 <= val <= max_v):
                raise ValueError(f"{name}는 0–{max_v} 범위여야 합니다: {val}")
        expected = (
            situation_score + task_score + action_score + result_score + culture_fit
        )
        if total_score != expected:
            raise ValueError(
                f"total_score({total_score})가 부분 점수의 합({expected})과 다릅니다."
            )
        self.situation_score = situation_score
        self.task_score = task_score
        self.action_score = action_score
        self.result_score = result_score
        self.culture_fit = culture_fit
        self.total_score = total_score
        self.feedback = feedback
        self.strong_points = list(strong_points)
        self.weak_points = list(weak_points)
        self.improved_answer = improved_answer

    @property
    def grade(self) -> str:
        if self.total_score >= 80:
            return "우수"
        if self.total_score >= 50:
            return "보통"
        return "미흡"


# ── 이력서 가이드 (Resume Advisor) ───────────────────────────────

VALID_ALIGNMENT_STATUS = frozenset(("충족", "부분충족", "누락"))
VALID_ALIGNMENT_PRIORITY = frozenset(("필수", "우대"))


@dataclass(frozen=True)
class JobPosting:
    """공채 공고에서 추출한 텍스트 (PDF/문서 → text). 값 객체."""

    raw_text: str
    company: str = ""   # samsung_ds | sk_hynix | "" (미상)
    source: str = ""    # 원본 파일 경로 (감사 추적용)

    def __post_init__(self):
        if not self.raw_text.strip():
            raise ValueError("공고 텍스트는 비어있을 수 없습니다.")


@dataclass(frozen=True)
class ResumeProfile:
    """사용자 이력서 원문 (수강 과목·프로젝트·경력 등). 값 객체."""

    raw_text: str
    source: str = ""

    def __post_init__(self):
        if not self.raw_text.strip():
            raise ValueError("이력서 텍스트는 비어있을 수 없습니다.")


@dataclass(frozen=True)
class AlignmentItem:
    """공고 요건 1개에 대한 이력서 부합 결과."""

    requirement: str        # 공고가 요구하는 항목
    status: str             # 충족 | 부분충족 | 누락
    evidence: str           # 이력서 근거 (없으면 빈 문자열)
    action: str             # 보완 액션 가이드
    priority: str = "필수"   # 필수 | 우대

    def __post_init__(self):
        if self.status not in VALID_ALIGNMENT_STATUS:
            raise ValueError(
                f"status는 {VALID_ALIGNMENT_STATUS} 중 하나여야 합니다: {self.status!r}"
            )
        if self.priority not in VALID_ALIGNMENT_PRIORITY:
            raise ValueError(
                f"priority는 {VALID_ALIGNMENT_PRIORITY} 중 하나여야 합니다: {self.priority!r}"
            )
        if not self.requirement.strip():
            raise ValueError("requirement는 비어있을 수 없습니다.")


class ResumeGuidance:
    """공채 공고 ↔ 이력서 정렬 가이드 결과.

    match_score (0–100): 공고 부합도 (필수 요건 충족 비중 중심).
    """

    def __init__(
        self,
        match_score: int,
        alignment_items: list[AlignmentItem],
        summary: str,
        priority_actions: list[str],
        rewrite_suggestions: list[str] | None = None,
    ) -> None:
        if not (0 <= match_score <= 100):
            raise ValueError(f"match_score는 0–100 범위여야 합니다: {match_score}")
        self.match_score = match_score
        self.alignment_items = list(alignment_items)
        self.summary = summary
        self.priority_actions = list(priority_actions)
        self.rewrite_suggestions = list(rewrite_suggestions or [])

    @property
    def grade(self) -> str:
        if self.match_score >= 80:
            return "우수"
        if self.match_score >= 50:
            return "보통"
        return "미흡"

    @property
    def status_counts(self) -> dict[str, int]:
        """상태별 요건 개수 — 출력 요약용."""
        counts = {"충족": 0, "부분충족": 0, "누락": 0}
        for item in self.alignment_items:
            counts[item.status] = counts.get(item.status, 0) + 1
        return counts
