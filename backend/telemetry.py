from __future__ import annotations

import json
import logging
import math
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.similarity import has_cjk

logger = logging.getLogger("llm_wiki.telemetry")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)


# Pricing in USD per 1,000,000 tokens: (input_usd_per_1m, output_usd_per_1m)
MODEL_PRICING_PER_1M_TOKENS: dict[str, tuple[float, float]] = {
    "gemini-3.5-flash-lite": (0.075, 0.30),
    "gemini-2.5-flash-lite": (0.075, 0.30),
    "gemini-2.0-flash-lite": (0.075, 0.30),
    "gemini-3-flash": (0.15, 0.60),
    "gemini-2.5-flash": (0.15, 0.60),
    "gemini-2.0-flash": (0.15, 0.60),
    "gemini-4-hydrogen": (0.15, 0.60),
    "gemini-3.1-pro": (1.25, 5.00),
    "gemini-2.5-pro": (1.25, 5.00),
    "gemini-1.5-pro": (1.25, 5.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-mini": (0.15, 0.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1": (2.00, 8.00),
    "local_smart": (0.0, 0.0),
}

# Reference model used to estimate how much cloud cost was saved when local_smart / dedup pre-filter runs
REFERENCE_SAVINGS_MODEL = "gemini-3.5-flash-lite"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def estimate_tokens(text: str) -> int:
    """
    Fast, deterministic token count estimator when an API omits usage metadata
    or when calculating tokens saved by deterministic local_smart execution.
    - English/ASCII technical prose: ~3.8 characters per token.
    - Japanese/CJK prose: ~1.5 characters per token.
    """
    if not text:
        return 0
    if has_cjk(text):
        return max(1, int(math.ceil(len(text) / 1.5)))
    return max(1, int(math.ceil(len(text) / 3.8)))


def resolve_model_pricing(provider: str, model: str) -> tuple[float, float]:
    """Return (input_usd_per_1m, output_usd_per_1m) for a given provider and model."""
    p_low = (provider or "").lower()
    m_low = (model or "").strip().lower()
    if p_low in ("local_smart", "ollama") or m_low in ("local_smart", "deterministic", "none"):
        return (0.0, 0.0)
    if m_low in MODEL_PRICING_PER_1M_TOKENS:
        return MODEL_PRICING_PER_1M_TOKENS[m_low]
    for prefix, rates in MODEL_PRICING_PER_1M_TOKENS.items():
        if prefix != "local_smart" and (m_low.startswith(prefix) or prefix in m_low):
            return rates
    if p_low == "gemini":
        if "lite" in m_low:
            return (0.075, 0.30)
        if "pro" in m_low:
            return (1.25, 5.00)
        return (0.15, 0.60)
    if p_low == "openai":
        if "mini" in m_low:
            return (0.15, 0.60)
        if "nano" in m_low:
            return (0.10, 0.40)
        return (2.50, 10.00)
    return (0.15, 0.60)


def compute_cost_usd(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    thought_tokens: int = 0,
) -> float:
    in_rate, out_rate = resolve_model_pricing(provider, model)
    billable_out = output_tokens + thought_tokens
    cost = (input_tokens / 1_000_000.0) * in_rate + (billable_out / 1_000_000.0) * out_rate
    return round(cost, 8)


@dataclass
class TelemetryEvent:
    event_id: int
    timestamp: str
    operation: str  # e.g. "extract_candidates", "synthesize_page_update", "answer_wiki_query", "similarity_search"
    llm_used: bool
    execution_mode: str  # "llm_api" | "local_smart" | "local_dedup_prefilter" | "llm_fallback_to_local"
    provider: str  # "gemini" | "openai" | "ollama" | "local_smart"
    model: str  # e.g. "gemini-3.5-flash-lite", "gpt-4o-mini", "local_smart"
    status: str  # "ok" | "error" | "fallback"
    input_tokens: int
    output_tokens: int
    thought_tokens: int
    cached_tokens: int
    total_tokens: int
    token_source: str  # "api_usage" | "estimated" | "none"
    cost_usd: float
    estimated_tokens_saved: int
    estimated_cost_saved_usd: float
    latency_ms: float
    target_slug: str = ""
    reason: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TelemetryTracker:
    """
    Central observability & telemetry logger for LLM Wiki.
    Logs every LLM call and every deterministic local execution to:
      1. Python standard logger (`llm_wiki.telemetry`)
      2. Persistent JSONL log (`vault/telemetry.jsonl`)
      3. In-memory ring buffer & aggregated metrics for the UI and `/api/telemetry`
    """

    def __init__(self, log_file: Path | None = None, max_recent: int = 200):
        self.log_file = log_file
        self.max_recent = max_recent
        self._events: deque[TelemetryEvent] = deque(maxlen=max_recent)
        self._all_events_list: list[TelemetryEvent] = []
        self._next_id = 1
        self._load_existing_from_disk()

    def _load_existing_from_disk(self) -> None:
        if not self.log_file or not self.log_file.exists():
            return
        try:
            lines = self.log_file.read_text(encoding="utf-8").splitlines()
            for raw in lines[-self.max_recent :]:
                raw = raw.strip()
                if not raw:
                    continue
                data = json.loads(raw)
                ev = TelemetryEvent(
                    event_id=int(data.get("event_id", self._next_id)),
                    timestamp=str(data.get("timestamp", "")),
                    operation=str(data.get("operation", "unknown")),
                    llm_used=bool(data.get("llm_used", False)),
                    execution_mode=str(data.get("execution_mode", "local_smart")),
                    provider=str(data.get("provider", "local_smart")),
                    model=str(data.get("model", "local_smart")),
                    status=str(data.get("status", "ok")),
                    input_tokens=int(data.get("input_tokens", 0)),
                    output_tokens=int(data.get("output_tokens", 0)),
                    thought_tokens=int(data.get("thought_tokens", 0)),
                    cached_tokens=int(data.get("cached_tokens", 0)),
                    total_tokens=int(data.get("total_tokens", 0)),
                    token_source=str(data.get("token_source", "none")),
                    cost_usd=float(data.get("cost_usd", 0.0)),
                    estimated_tokens_saved=int(data.get("estimated_tokens_saved", 0)),
                    estimated_cost_saved_usd=float(data.get("estimated_cost_saved_usd", 0.0)),
                    latency_ms=float(data.get("latency_ms", 0.0)),
                    target_slug=str(data.get("target_slug", "")),
                    reason=str(data.get("reason", "")),
                    error=str(data.get("error", "")),
                )
                self._events.append(ev)
                self._all_events_list.append(ev)
                self._next_id = max(self._next_id, ev.event_id + 1)
        except Exception:
            pass

    def cursor(self) -> int:
        """Return current event count cursor to slice per-request telemetry events."""
        return len(self._all_events_list)

    def summarize_slice(self, start_cursor: int) -> dict[str, Any]:
        """Summarize only the telemetry events emitted during a single API request."""
        slice_events = self._all_events_list[start_cursor:]
        llm_calls = sum(1 for e in slice_events if e.llm_used)
        local_ops = sum(1 for e in slice_events if not e.llm_used)
        in_tok = sum(e.input_tokens for e in slice_events)
        out_tok = sum(e.output_tokens for e in slice_events)
        thought_tok = sum(e.thought_tokens for e in slice_events)
        tot_tok = sum(e.total_tokens for e in slice_events)
        saved_tok = sum(e.estimated_tokens_saved for e in slice_events)
        cost = round(sum(e.cost_usd for e in slice_events), 8)
        saved_cost = round(sum(e.estimated_cost_saved_usd for e in slice_events), 8)
        lat_ms = round(sum(e.latency_ms for e in slice_events), 2)
        models_used = list(dict.fromkeys(e.model for e in slice_events if e.model))
        providers_used = list(dict.fromkeys(e.provider for e in slice_events if e.provider))

        return {
            "llm_used": llm_calls > 0,
            "llm_calls": llm_calls,
            "local_operations": local_ops,
            "providers": providers_used,
            "models": models_used,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "thought_tokens": thought_tok,
            "total_tokens": tot_tok,
            "estimated_tokens_saved": saved_tok,
            "cost_usd": cost,
            "estimated_cost_saved_usd": saved_cost,
            "total_latency_ms": lat_ms,
            "events": [e.to_dict() for e in slice_events],
        }

    def record_event(
        self,
        *,
        operation: str,
        llm_used: bool,
        execution_mode: str,
        provider: str,
        model: str,
        status: str = "ok",
        input_tokens: int = 0,
        output_tokens: int = 0,
        thought_tokens: int = 0,
        cached_tokens: int = 0,
        total_tokens: int | None = None,
        token_source: str = "none",
        estimated_tokens_saved: int = 0,
        latency_ms: float = 0.0,
        target_slug: str = "",
        reason: str = "",
        error: str = "",
        savings_reference_model: str = REFERENCE_SAVINGS_MODEL,
    ) -> TelemetryEvent:
        tot = (
            total_tokens
            if total_tokens is not None and total_tokens > 0
            else (input_tokens + output_tokens + thought_tokens)
        )
        cost_usd = (
            compute_cost_usd(provider, model, input_tokens, output_tokens, thought_tokens)
            if llm_used
            else 0.0
        )
        saved_cost_usd = 0.0
        if not llm_used and estimated_tokens_saved > 0:
            # Assume ~85% input tokens and ~15% output tokens for avoided LLM synthesis
            est_in = int(estimated_tokens_saved * 0.85)
            est_out = max(estimated_tokens_saved - est_in, 0)
            saved_cost_usd = compute_cost_usd("gemini", savings_reference_model, est_in, est_out)

        ev = TelemetryEvent(
            event_id=self._next_id,
            timestamp=utc_now_iso(),
            operation=operation,
            llm_used=llm_used,
            execution_mode=execution_mode,
            provider=provider,
            model=model,
            status=status,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thought_tokens=thought_tokens,
            cached_tokens=cached_tokens,
            total_tokens=tot,
            token_source=token_source,
            cost_usd=cost_usd,
            estimated_tokens_saved=estimated_tokens_saved,
            estimated_cost_saved_usd=saved_cost_usd,
            latency_ms=round(latency_ms, 2),
            target_slug=target_slug,
            reason=reason,
            error=error,
        )
        self._next_id += 1
        self._events.append(ev)
        self._all_events_list.append(ev)

        # 1. Emit structured Python log line
        log_msg = (
            f"op={ev.operation} | llm_used={ev.llm_used} | mode={ev.execution_mode} | "
            f"provider={ev.provider} | model={ev.model} | status={ev.status} | "
            f"tokens={ev.input_tokens}in/{ev.output_tokens}out/{ev.total_tokens}tot ({ev.token_source}) | "
            f"cost=${ev.cost_usd:.6f} | saved_tokens={ev.estimated_tokens_saved} (saved=${ev.estimated_cost_saved_usd:.6f}) | "
            f"latency={ev.latency_ms:.2f}ms"
        )
        if ev.target_slug:
            log_msg += f" | slug={ev.target_slug}"
        if ev.reason:
            log_msg += f" | reason={ev.reason}"
        if ev.error:
            log_msg += f" | error={ev.error}"

        if ev.status == "error":
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

        # 2. Persist to vault/telemetry.jsonl if configured
        if self.log_file is not None:
            try:
                self.log_file.parent.mkdir(parents=True, exist_ok=True)
                with self.log_file.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(ev.to_dict(), ensure_ascii=False) + "\n")
            except Exception:
                pass

        return ev

    def reset(self) -> None:
        self._events.clear()
        self._all_events_list.clear()
        self._next_id = 1
        if self.log_file and self.log_file.exists():
            try:
                self.log_file.write_text("", encoding="utf-8")
            except Exception:
                pass

    def summary(self, limit_recent: int = 60) -> dict[str, Any]:
        events = self._all_events_list
        llm_events = [e for e in events if e.llm_used]
        local_events = [e for e in events if not e.llm_used]
        dedup_skipped = [e for e in events if e.execution_mode == "local_dedup_prefilter"]
        fallback_events = [e for e in events if e.execution_mode == "llm_fallback_to_local"]

        in_tokens = sum(e.input_tokens for e in events)
        out_tokens = sum(e.output_tokens for e in events)
        thought_tokens = sum(e.thought_tokens for e in events)
        cached_tokens = sum(e.cached_tokens for e in events)
        total_tokens = sum(e.total_tokens for e in events)
        saved_tokens = sum(e.estimated_tokens_saved for e in events)

        total_cost_usd = round(sum(e.cost_usd for e in events), 8)
        saved_cost_usd = round(sum(e.estimated_cost_saved_usd for e in events), 8)

        llm_lat_total = round(sum(e.latency_ms for e in llm_events), 2)
        local_lat_total = round(sum(e.latency_ms for e in local_events), 2)

        by_model: dict[str, dict[str, Any]] = {}
        for e in events:
            m_key = f"{e.provider}:{e.model}"
            entry = by_model.setdefault(
                m_key,
                {
                    "provider": e.provider,
                    "model": e.model,
                    "llm_used": e.llm_used,
                    "calls": 0,
                    "succeeded": 0,
                    "failed": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "thought_tokens": 0,
                    "total_tokens": 0,
                    "cost_usd": 0.0,
                    "estimated_tokens_saved": 0,
                    "estimated_cost_saved_usd": 0.0,
                    "total_latency_ms": 0.0,
                },
            )
            entry["calls"] += 1
            if e.status == "ok":
                entry["succeeded"] += 1
            else:
                entry["failed"] += 1
            entry["input_tokens"] += e.input_tokens
            entry["output_tokens"] += e.output_tokens
            entry["thought_tokens"] += e.thought_tokens
            entry["total_tokens"] += e.total_tokens
            entry["cost_usd"] = round(entry["cost_usd"] + e.cost_usd, 8)
            entry["estimated_tokens_saved"] += e.estimated_tokens_saved
            entry["estimated_cost_saved_usd"] = round(
                entry["estimated_cost_saved_usd"] + e.estimated_cost_saved_usd, 8
            )
            entry["total_latency_ms"] = round(entry["total_latency_ms"] + e.latency_ms, 2)

        by_operation: dict[str, dict[str, Any]] = {}
        for e in events:
            op_entry = by_operation.setdefault(
                e.operation,
                {
                    "operation": e.operation,
                    "total_count": 0,
                    "llm_count": 0,
                    "local_count": 0,
                    "total_tokens": 0,
                    "cost_usd": 0.0,
                    "estimated_tokens_saved": 0,
                    "estimated_cost_saved_usd": 0.0,
                    "avg_latency_ms": 0.0,
                    "_sum_lat": 0.0,
                },
            )
            op_entry["total_count"] += 1
            if e.llm_used:
                op_entry["llm_count"] += 1
            else:
                op_entry["local_count"] += 1
            op_entry["total_tokens"] += e.total_tokens
            op_entry["cost_usd"] = round(op_entry["cost_usd"] + e.cost_usd, 8)
            op_entry["estimated_tokens_saved"] += e.estimated_tokens_saved
            op_entry["estimated_cost_saved_usd"] = round(
                op_entry["estimated_cost_saved_usd"] + e.estimated_cost_saved_usd, 8
            )
            op_entry["_sum_lat"] += e.latency_ms
            op_entry["avg_latency_ms"] = round(op_entry["_sum_lat"] / op_entry["total_count"], 2)

        for op_entry in by_operation.values():
            op_entry.pop("_sum_lat", None)

        recent_list = [e.to_dict() for e in list(self._events)[-limit_recent:]][::-1]

        return {
            "log_file": str(self.log_file) if self.log_file else None,
            "totals": {
                "total_events": len(events),
                "llm_calls_total": len(llm_events),
                "llm_calls_succeeded": sum(1 for e in llm_events if e.status == "ok"),
                "llm_calls_failed": sum(1 for e in llm_events if e.status != "ok"),
                "local_smart_executions": len(local_events),
                "llm_calls_skipped_by_dedup": len(dedup_skipped),
                "llm_fallbacks_to_local": len(fallback_events),
                "input_tokens": in_tokens,
                "output_tokens": out_tokens,
                "thought_tokens": thought_tokens,
                "cached_tokens": cached_tokens,
                "total_tokens": total_tokens,
                "estimated_tokens_saved": saved_tokens,
                "total_cost_usd": total_cost_usd,
                "estimated_cost_saved_usd": saved_cost_usd,
                "total_llm_latency_ms": llm_lat_total,
                "avg_llm_latency_ms": round(llm_lat_total / len(llm_events), 2) if llm_events else 0.0,
                "total_local_latency_ms": local_lat_total,
                "avg_local_latency_ms": round(local_lat_total / len(local_events), 2) if local_events else 0.0,
            },
            "by_model": list(by_model.values()),
            "by_operation": list(by_operation.values()),
            "pricing_per_1m_tokens_usd": {
                k: {"input_usd": v[0], "output_usd": v[1]}
                for k, v in MODEL_PRICING_PER_1M_TOKENS.items()
            },
            "recent_events": recent_list,
        }

