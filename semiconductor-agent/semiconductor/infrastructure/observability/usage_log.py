"""사용량·비용 로깅 — JSON Lines (`usage.jsonl`).

Dual-purpose:
  - 본인 사용 시: 월 비용 추적, 어떤 모듈을 매주 N회 쓰는지
  - 상용화 시: per-user usage tracking 인프라 그대로 (thread_id = user.id)

사용:
    from semiconductor.infrastructure.observability.usage_log import log_usage
    log_usage(thread_id="hans", node="judge", model="openai:gpt-4o",
              tokens_in=1500, tokens_out=400)

대략적 cost는 `_estimate_cost`가 모델별 단가로 계산. 정확한 청구액은 provider
대시보드에서 확인. 여기 로그는 내부 분석·예측용.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

# 모델별 가격 (USD per 1M tokens, 2026-06 기준)
# Provider 가격이 바뀌면 여기 갱신. 정확값은 provider invoice 우선.
_PRICES_PER_1M: dict[str, tuple[float, float]] = {
    # (input, output)
    "openai:gpt-4o":            (2.50, 10.00),
    "openai:gpt-4o-mini":       (0.15, 0.60),
    "openai:gpt-5":             (10.00, 30.00),
    "anthropic:claude-sonnet-4-6":           (3.00, 15.00),
    "anthropic:claude-haiku-4-5-20251001":   (0.80, 4.00),
    "anthropic:claude-opus-4-7":             (15.00, 75.00),
    "google_genai:gemini-2.5-pro":           (1.25, 10.00),
    "google_genai:gemini-2.5-flash":         (0.075, 0.30),
}

_DEFAULT_LOG_PATH = "usage.jsonl"


def _estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """대략 비용 (USD). provider invoice가 진실의 원천."""
    price = _PRICES_PER_1M.get(model)
    if price is None:
        return 0.0
    in_p, out_p = price
    return (tokens_in * in_p + tokens_out * out_p) / 1_000_000


def log_usage(
    thread_id: str,
    node: str,
    model: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    extra: dict | None = None,
    log_path: str | None = None,
) -> dict:
    """Append one JSON line to usage log. Returns the logged record.

    Args:
        thread_id: 사용자 식별자 (자체용 = "hans", 상용 = user.id)
        node: 그래프 노드 이름 (judge / critic / coach / essay / ...)
        model: provider:model 문자열
        tokens_in / tokens_out: 호출 시 토큰 수 (provider response.usage_metadata에서 추출)
        extra: 자유 메타 (cache_hit, latency_ms 등)
    """
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "thread_id": thread_id,
        "node": node,
        "model": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": round(_estimate_cost(model, tokens_in, tokens_out), 6),
    }
    if extra:
        record["extra"] = extra

    path = Path(log_path or os.getenv("USAGE_LOG_PATH", _DEFAULT_LOG_PATH))
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record


def current_thread_id() -> str:
    """현재 사용자 식별자 — env var THREAD_ID, 기본 'hans' (자체 사용)."""
    return os.getenv("THREAD_ID", "hans")


def log_llm_call(response, node: str, model: str, thread_id: str | None = None) -> None:
    """LLM 호출 결과에서 토큰 추출 후 자동 로깅. 실패 시 silent skip.

    response: LangChain AIMessage 또는 with_structured_output() 결과.
    structured output은 토큰 메타가 없을 수 있음 — 그 경우 0으로 기록 (호출 횟수는 보존).
    """
    tokens_in = 0
    tokens_out = 0
    try:
        meta = getattr(response, "usage_metadata", None)
        if meta:
            tokens_in = meta.get("input_tokens", 0) or 0
            tokens_out = meta.get("output_tokens", 0) or 0
    except Exception:
        pass

    try:
        log_usage(
            thread_id=thread_id or current_thread_id(),
            node=node,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
    except Exception:
        # 로깅 실패는 본 흐름을 깨면 안 됨
        pass


def read_usage(log_path: str | None = None) -> list[dict]:
    """usage.jsonl 전체 로드. 분석 스크립트용."""
    path = Path(log_path or os.getenv("USAGE_LOG_PATH", _DEFAULT_LOG_PATH))
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out
