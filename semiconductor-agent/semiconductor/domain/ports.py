"""Domain ports (interfaces) — define contracts for infrastructure layer."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from semiconductor.domain.entities import (
    BehavioralEvaluation,
    BehavioralQuestion,
    DiagnosticResult,
    EssayEvaluation,
    EssayPrompt,
    EvaluationResult,
    JobPosting,
    Question,
    ResumeGuidance,
    ResumeProfile,
)


class IQuestionRepository(ABC):
    @abstractmethod
    def get_questions(self, company: str, domain: Optional[str] = None) -> list[Question]:
        """Return questions for a company, optionally filtered by domain."""


class ILLMJudge(ABC):
    @abstractmethod
    def evaluate(self, question: Question, user_answer: str) -> EvaluationResult:
        """Evaluate a user answer against the question rubric."""


class ICoachLLM(ABC):
    @abstractmethod
    def get_response(
        self,
        topic: str,
        messages: list,
        hint_count: int,
    ) -> str:
        """Return Socratic coaching response for the given topic and conversation."""


class IDiagnosticLLM(ABC):
    @abstractmethod
    def analyze(self, evaluations: list[EvaluationResult]) -> DiagnosticResult:
        """Analyze interview evaluations and produce domain scores."""


class IEssayCoach(ABC):
    """자소서 첨삭 LLM."""

    @abstractmethod
    def evaluate_essay(self, prompt: EssayPrompt, user_essay: str) -> EssayEvaluation:
        """회사 인재상 + STAR 구조 + 구체성 + 작문 4축으로 평가."""


class IBehavioralCoach(ABC):
    """인성면접 (STAR 기법) 평가 LLM."""

    @abstractmethod
    def evaluate_behavioral(
        self,
        question: BehavioralQuestion,
        user_answer: str,
    ) -> BehavioralEvaluation:
        """STAR 4단계 + 회사 인재상 부합도로 평가."""


class ILLMCritic(ABC):
    """Self-critique layer — LLM이 본인의 평가를 다시 검증·수정한다.

    교수 1명의 즉답보다 깊은 분석을 위해 평가→재검증 2회 추론으로 정확도를 높인다.
    """

    @abstractmethod
    def critique(
        self,
        question: Question,
        user_answer: str,
        initial_evaluation: EvaluationResult,
    ) -> EvaluationResult:
        """Review an initial evaluation and return a revised one if needed."""


class IResumeAdvisorLLM(ABC):
    """공채 공고 ↔ 이력서 정렬 가이드 LLM."""

    @abstractmethod
    def guide(self, posting: JobPosting, resume: ResumeProfile) -> ResumeGuidance:
        """공고 요건 대비 이력서 갭 분석 + 보완 가이드를 생성한다."""
