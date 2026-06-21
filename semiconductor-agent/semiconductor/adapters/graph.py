"""LangGraph assembly — wires all adapter nodes into a compiled StateGraph.

Topology:
    START → orchestrator
              ├──▶ mock_present  ──▶ END                                  (질문 출제)
              ├──▶ mock_evaluate ─┐
              ├──▶ web_enrichment ┼──▶ mock_critic ──▶ END                (평가 + 트렌드면 병렬 검색)
              ├──▶ qa_coach ──tool_calls?──▶ coach_tools ──▶ qa_coach (loop)
              │                  └──no──▶ END
              ├──▶ diagnostic    ──▶ END
              └──▶ END (idle)

Optional features:
    - Checkpointer (Memory): create_app(checkpointer=...) — thread_id로 영속화
    - Parallel (Send API): 트렌드 도메인 평가 시 mock_evaluate ∥ web_enrichment
    - ReAct tools: qa_coach가 industry_search / 반도체 계산기 호출
"""
from __future__ import annotations

from typing import Optional

from langchain_core._api.deprecation import suppress_langchain_deprecation_warning

with suppress_langchain_deprecation_warning():
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, StateGraph
    from langgraph.types import Send

from semiconductor.adapters.nodes.aptitude_test import (
    aptitude_evaluate_node,
    aptitude_present_node,
)
from semiconductor.adapters.nodes.behavioral_coach import (
    behavioral_evaluate_node,
    behavioral_present_node,
)
from semiconductor.adapters.nodes.diagnostic import diagnostic_node
from semiconductor.adapters.nodes.essay_coach import essay_evaluate_node, essay_present_node
from semiconductor.adapters.nodes.mock_interviewer import (
    mock_critic_node,
    mock_evaluate_node,
    mock_present_node,
)
from semiconductor.adapters.nodes.orchestrator import orchestrator_node, route_from_orchestrator
from semiconductor.adapters.nodes.qa_coach import (
    coach_tools_node,
    qa_coach_node,
    route_after_coach,
)
from semiconductor.adapters.nodes.resume_coach import resume_advisor_node
from semiconductor.adapters.nodes.web_enrichment import web_enrichment_node
from semiconductor.adapters.state import InterviewState, create_initial_state


def _eval_dispatch(state: InterviewState) -> list:
    """평가 turn 시 fan-out: 항상 mock_evaluate, 트렌드 도메인이면 web_enrichment 병렬."""
    sends = [Send("mock_evaluate", state)]
    if state.get("current_question_domain") == "트렌드":
        sends.append(Send("web_enrichment", state))
    return sends


def create_app(
    company: str = "samsung_ds",
    domain: Optional[str] = None,
    max_questions: int = 5,
    checkpointer=None,
):
    """Build and compile the interview StateGraph.

    Args:
        checkpointer: LangGraph 체크포인터 (MemorySaver, SqliteSaver 등).
                      None이면 영속화 없이 기본 동작.

    Returns:
        (app, state) — compiled LangGraph app and an initialized state dict.
    """
    builder = StateGraph(InterviewState)

    # ── Nodes ────────────────────────────────────────────────────
    builder.add_node("orchestrator", orchestrator_node)
    builder.add_node("mock_present", mock_present_node)
    builder.add_node("eval_dispatch", lambda s: {})  # no-op fan-out 진입점
    builder.add_node("mock_evaluate", mock_evaluate_node)
    builder.add_node("web_enrichment", web_enrichment_node)
    builder.add_node("mock_critic", mock_critic_node)
    builder.add_node("qa_coach", qa_coach_node)
    builder.add_node("coach_tools", coach_tools_node)
    builder.add_node("essay_present", essay_present_node)
    builder.add_node("essay_evaluate", essay_evaluate_node)
    builder.add_node("behavioral_present", behavioral_present_node)
    builder.add_node("behavioral_evaluate", behavioral_evaluate_node)
    builder.add_node("aptitude_present", aptitude_present_node)
    builder.add_node("aptitude_evaluate", aptitude_evaluate_node)
    builder.add_node("resume_advisor", resume_advisor_node)
    builder.add_node("diagnostic", diagnostic_node)

    builder.set_entry_point("orchestrator")

    # ── Orchestrator routing ─────────────────────────────────────
    builder.add_conditional_edges(
        "orchestrator",
        route_from_orchestrator,
        {
            "mock_present": "mock_present",
            "mock_evaluate": "eval_dispatch",  # evaluate phase는 fan-out 거침
            "qa_coach": "qa_coach",
            "essay_present": "essay_present",
            "essay_evaluate": "essay_evaluate",
            "behavioral_present": "behavioral_present",
            "behavioral_evaluate": "behavioral_evaluate",
            "aptitude_present": "aptitude_present",
            "aptitude_evaluate": "aptitude_evaluate",
            "resume_advisor": "resume_advisor",
            "diagnostic": "diagnostic",
            END: END,
        },
    )

    # ── Parallel fan-out: eval_dispatch → [mock_evaluate, web_enrichment?] ──
    builder.add_conditional_edges("eval_dispatch", _eval_dispatch)

    # ── Convergence: mock_evaluate / web_enrichment → mock_critic ──
    builder.add_edge("mock_evaluate", "mock_critic")
    builder.add_edge("web_enrichment", "mock_critic")
    builder.add_edge("mock_critic", END)

    # ── qa_coach ReAct loop ──────────────────────────────────────
    builder.add_conditional_edges(
        "qa_coach",
        route_after_coach,
        {
            "coach_tools": "coach_tools",
            END: END,
        },
    )
    builder.add_edge("coach_tools", "qa_coach")  # 도구 결과로 다시 코치에게

    # ── Single-path nodes ────────────────────────────────────────
    builder.add_edge("mock_present", END)
    builder.add_edge("essay_present", END)
    builder.add_edge("essay_evaluate", END)
    builder.add_edge("behavioral_present", END)
    builder.add_edge("behavioral_evaluate", END)
    builder.add_edge("aptitude_present", END)
    builder.add_edge("aptitude_evaluate", END)
    builder.add_edge("resume_advisor", END)
    builder.add_edge("diagnostic", END)

    compile_kwargs = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer

    app = builder.compile(**compile_kwargs)
    state = create_initial_state(company=company, domain=domain, max_questions=max_questions)

    return app, state


def create_app_with_memory(
    company: str = "samsung_ds",
    domain: Optional[str] = None,
    max_questions: int = 5,
):
    """편의 팩토리: in-memory checkpointer로 영속화 활성화.

    Production 배포 시 SqliteSaver / PostgresSaver로 교체.
    """
    return create_app(
        company=company,
        domain=domain,
        max_questions=max_questions,
        checkpointer=MemorySaver(),
    )


def create_app_with_sqlite(
    db_path: str = ".agent_state.db",
    company: str = "samsung_ds",
    domain: Optional[str] = None,
    max_questions: int = 5,
):
    """디스크 영속화 팩토리 — 매일 진도 이어가기.

    프로세스 재시작 후에도 thread_id 기반으로 이전 면접·진단·자소서 상태 복원.
    상용화 시 PostgresSaver로 swap만 하면 멀티유저 지원.

    Args:
        db_path: SQLite 파일 경로 (기본 ./.agent_state.db, gitignore 처리)
    """
    from langgraph.checkpoint.sqlite import SqliteSaver
    import sqlite3

    # check_same_thread=False — Jupyter / Chainlit 같이 다른 thread에서 invoke 가능하게
    conn = sqlite3.connect(db_path, check_same_thread=False)
    saver = SqliteSaver(conn)
    return create_app(
        company=company,
        domain=domain,
        max_questions=max_questions,
        checkpointer=saver,
    )
