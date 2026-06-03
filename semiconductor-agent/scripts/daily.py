#!/usr/bin/env python3
"""일일 면접 루틴 — 한 줄 명령으로 5분 면접 자동 시작.

사용:
    uv run python scripts/daily.py
    # 또는 alias 등록:
    alias inv="cd ~/.../semiconductor-agent && uv run python scripts/daily.py"

동작:
1. SqliteSaver로 thread_id="hans" 영속 상태 로드
2. 누적 평가에서 가장 약한 도메인 자동 감지
3. 해당 도메인으로 면접 1세트 (3문제) 시작
4. 답변 입력 → 평가 → 다음 문제 → 진단

매일 같은 thread_id를 쓰므로 어제 진도가 그대로 이어짐.
중간에 종료해도 다음 실행 시 이어서.
"""
from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

# 레포 루트가 sys.path에 있어야 함
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from semiconductor.adapters.graph import create_app_with_sqlite

load_dotenv()

DB_PATH = os.getenv("AGENT_DB", ".agent_state.db")
THREAD_ID = os.getenv("THREAD_ID", "hans")
COMPANY = os.getenv("DAILY_COMPANY", "samsung_ds")
MAX_Q = int(os.getenv("DAILY_MAX_Q", "3"))


def detect_weak_domain(state: dict) -> str | None:
    """누적 evaluations에서 도메인별 평균 점수 → 가장 낮은 도메인 반환."""
    evals = state.get("evaluations", []) or []
    if not evals:
        return None
    domain_totals: dict[str, list[int]] = {}
    for e in evals:
        # eval dict에서 question text의 domain 매핑은 없음 — current_question_domain은 turn-local
        # 대신 evaluations[].question 텍스트로 매칭은 어려움. 단순화: 마지막 N개에서 평균 낮은 쪽
        # Phase 3에서 진단 결과 저장 시 도메인 명시 → 그때 정확화
        pass
    # 데모용 단순 구현: 가장 최근 평가들의 평균이 50 미만이면 그 도메인 추정 어려움
    # → diagnostic 결과에서 weak_topics를 가져오는 게 정확
    return None  # Phase 1.5에서 weak_domain 영속 저장 후 활용


def main() -> int:
    print("🎯 [일일 면접 루틴] 시작")
    print(f"  DB: {DB_PATH}")
    print(f"  Thread: {THREAD_ID}")
    print(f"  Company: {COMPANY}")
    print(f"  Questions: {MAX_Q}")
    print()

    app, state = create_app_with_sqlite(
        db_path=DB_PATH, company=COMPANY, max_questions=MAX_Q,
    )
    config = {"configurable": {"thread_id": THREAD_ID}, "recursion_limit": 25}

    # 이전 state 로드 시도
    snap = app.get_state(config)
    has_history = snap.values is not None and snap.values.get("evaluations")
    if has_history:
        prev = snap.values
        n = len(prev.get("evaluations", []))
        print(f"📚 이전 진도 발견: 누적 {n}개 평가. 이어서 진행.")
        weak = detect_weak_domain(prev)
        if weak:
            print(f"  💡 약점 도메인 감지: {weak} — 이번 라운드 집중\n")
    else:
        print("✨ 첫 세션. 새 면접 시작.\n")

    # 면접 시작
    state["messages"] = [HumanMessage(content="/인터뷰")]
    out = app.invoke(state, config=config)
    if out.get("display_output"):
        print(out["display_output"])
        print()

    # 답변 루프
    while True:
        try:
            user = input("\n>>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n💾 진도 저장됨. 내일 같은 명령으로 이어서.")
            return 0

        if not user:
            continue
        if user.lower() in ("quit", "exit", "종료", "/종료"):
            print("💾 진도 저장됨. 내일 같은 명령으로 이어서.")
            return 0

        out = app.invoke(
            {"messages": [HumanMessage(content=user)]}, config=config,
        )
        if out.get("display_output"):
            print("\n" + out["display_output"])

        # 면접 완료 시 자동 진단 — display 문자열 대신 권위 있는 상태 신호로 판정.
        # critic 노드가 마지막 문제(remaining<=0) 평가 후에만 mode를 "idle"로 바꾼다.
        if out.get("mode") == "idle":
            print("\n🔬 자동 진단 실행 중...")
            diag = app.invoke(
                {"messages": [HumanMessage(content="/진단")]}, config=config,
            )
            if diag.get("display_output"):
                print(diag["display_output"])
            print("\n💾 진도 저장됨. 내일 다시 시작하면 누적 약점 기반 출제.")
            return 0


if __name__ == "__main__":
    sys.exit(main())
