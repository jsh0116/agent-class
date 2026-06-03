"""Composition root — 그래프 노드에 주입할 인프라 의존성 컨테이너.

각 노드가 인프라 싱글톤을 직접 생성하면(LangChainLLMService.judge() 등) 그래프가
진짜 composition root가 되지 못하고, 대체 LLM/repo를 끼우려면 모듈 글로벌을
monkeypatch해야 한다. Dependencies를 create_app(deps=...)로 주입하면 patch 없이
가짜/대체 구현을 노드에 바인딩할 수 있다.

필드는 모두 무인자 factory(callable) — 노드 실행 시점에 호출돼 인스턴스를 만든다
(지연 생성: 매 호출 새 인스턴스, 불필요 생성 회피).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from semiconductor.infrastructure.llm import LangChainLLMService
from semiconductor.infrastructure.question_bank import InMemoryQuestionRepository
from semiconductor.infrastructure.tools.web_search import IndustrySearchService


@dataclass(frozen=True)
class Dependencies:
    judge_factory: Callable = LangChainLLMService.judge
    critic_factory: Callable = LangChainLLMService.critic
    diagnostic_factory: Callable = LangChainLLMService.diagnostic
    essay_factory: Callable = LangChainLLMService.essay
    behavioral_factory: Callable = LangChainLLMService.behavioral
    question_repo_factory: Callable = InMemoryQuestionRepository
    search_factory: Callable = IndustrySearchService
