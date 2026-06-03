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

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Send

from semiconductor.adapters.composition import Dependencies
from semiconductor.adapters.nodes.aptitude_test import (
    aptitude_evaluate_node,
    aptitude_present_node,
)
from semiconductor.adapters.nodes.behavioral_coach import (
    behavioral_evaluate_node,
    behavioral_present_node,
    make_behavioral_evaluate_node,
)
from semiconductor.adapters.nodes.diagnostic import diagnostic_node, make_diagnostic_node
from semiconductor.adapters.nodes.essay_coach import (
    essay_evaluate_node,
    essay_present_node,
    make_essay_evaluate_node,
)
from semiconductor.adapters.nodes.mock_interviewer import (
    make_mock_critic_node,
    make_mock_evaluate_node,
    make_mock_present_node,
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
from semiconductor.adapters.nodes.web_enrichment import (
    make_web_enrichment_node,
    web_enrichment_node,
)
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
    deps: Optional[Dependencies] = None,
):
    """Build and compile the interview StateGraph.

    Args:
        checkpointer: LangGraph 체크포인터 (MemorySaver, SqliteSaver 등).
                      None이면 영속화 없이 기본 동작.
        deps: 인프라 의존성 컨테이너 (composition root). None이면 각 노드의
              기본 서비스 사용. 주입하면 monkeypatch 없이 대체 LLM/repo를 끼운다.

    Returns:
        (app, state) — compiled LangGraph app and an initialized state dict.
    """
    builder = StateGraph(InterviewState)

    # ── Composition root: deps 주입 시 factory로 노드 바인딩, 아니면 기본 노드 ──
    if deps is None:
        present_node, evaluate_node, critic_node = (
            mock_present_node, mock_evaluate_node, mock_critic_node
        )
        web_node = web_enrichment_node
        essay_eval_node, behavioral_eval_node = essay_evaluate_node, behavioral_evaluate_node
        diag_node = diagnostic_node
    else:
        present_node = make_mock_present_node(deps.question_repo_factory)
        evaluate_node = make_mock_evaluate_node(deps.judge_factory)
        critic_node = make_mock_critic_node(deps.critic_factory)
        web_node = make_web_enrichment_node(deps.search_factory)
        essay_eval_node = make_essay_evaluate_node(deps.essay_factory)
        behavioral_eval_node = make_behavioral_evaluate_node(deps.behavioral_factory)
        diag_node = make_diagnostic_node(deps.diagnostic_factory)

    # ── Nodes ────────────────────────────────────────────────────
    builder.add_node("orchestrator", orchestrator_node)
    builder.add_node("mock_present", present_node)
    builder.add_node("eval_dispatch", lambda s: {})  # no-op fan-out 진입점
    builder.add_node("mock_evaluate", evaluate_node)
    builder.add_node("web_enrichment", web_node)
    builder.add_node("mock_critic", critic_node)
    builder.add_node("qa_coach", qa_coach_node)
    builder.add_node("coach_tools", coach_tools_node)
    builder.add_node("essay_present", essay_present_node)
    builder.add_node("essay_evaluate", essay_eval_node)
    builder.add_node("behavioral_present", behavioral_present_node)
    builder.add_node("behavioral_evaluate", behavioral_eval_node)
    builder.add_node("aptitude_present", aptitude_present_node)
    builder.add_node("aptitude_evaluate", aptitude_evaluate_node)
    builder.add_node("diagnostic", diag_node)

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
    import atexit
    import sqlite3

    from langgraph.checkpoint.sqlite import SqliteSaver

    # check_same_thread=False — Jupyter / Chainlit 같이 다른 thread에서 invoke 가능하게
    conn = sqlite3.connect(db_path, check_same_thread=False)
    # 연결 소유자가 없으면 누수된다. 단발 스크립트(daily/weekly) 수명과 맞춰
    # 프로세스 종료 시 확실히 닫는다. (이미 닫혀 있어도 sqlite close는 no-op)
    # 장기 실행 서버에 임베딩한다면 SqliteSaver.from_conn_string(...) 컨텍스트매니저로 교체.
    atexit.register(conn.close)
    saver = SqliteSaver(conn)
    return create_app(
        company=company,
        domain=domain,
        max_questions=max_questions,
        checkpointer=saver,
    )
