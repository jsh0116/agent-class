"""Web enrichment node — 트렌드 도메인 평가 시 mock_evaluate와 병렬 실행.

Send API로 dispatch되어 judge LLM 호출과 동시에 산업 동향 검색을 실행.
mock_critic이 두 결과를 통합한다.
"""
from __future__ import annotations

import functools

from semiconductor.adapters.state import InterviewState
from semiconductor.infrastructure.tools.web_search import IndustrySearchService


def _default_search():
    # 모듈 글로벌 지연 조회 — patch 호환 + composition root 주입 지점.
    return IndustrySearchService()


def web_enrichment_node(state: InterviewState, *, search_factory=_default_search) -> dict:
    """질문 텍스트로 산업 동향 검색해 state에 적재."""
    question = state.get("current_question_text") or ""
    if not question.strip():
        return {"web_enrichment": None}

    svc = search_factory()
    try:
        result = svc.search(question)
        return {"web_enrichment": result}
    except Exception:
        return {"web_enrichment": None}


def make_web_enrichment_node(search_factory=_default_search):
    """composition root용 — search 서비스 factory를 노드에 바인딩."""
    return functools.partial(web_enrichment_node, search_factory=search_factory)
