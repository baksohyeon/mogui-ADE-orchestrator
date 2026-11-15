"""Token accounting for supervised worker dispatches.

The provider formats are intentionally kept at this boundary.  Callers get a
small, provider-neutral result and can distinguish a measured zero from a
runtime that has no usable usage record.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


@dataclass(frozen=True)
class TokenUsage:
    """Normalized usage from one worker session."""

    input: int | None
    cached_input: int | None
    output: int | None
    total: int | None
    source: str
    why: str | None = None

    def as_dict(self) -> dict[str, object]:
        if self.why is not None:
            return {"source": self.source, "why": self.why}
        return {
            "input": self.input,
            "cached_input": self.cached_input,
            "output": self.output,
            "total": self.total,
            "source": self.source,
        }


def unmeasured(runtime: str, why: str) -> dict[str, object]:
    """Return the stable unmeasured shape required by the dispatch contract."""

    return {"source": "unmeasured", "why": f"{runtime}: {why}"}


def _integer(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and (not math.isfinite(value) or value != int(value)):
        return None
    number = int(value)
    return number if number >= 0 else None


def _read_jsonl(path: str | Path) -> Iterable[Mapping[str, object]]:
    try:
        with Path(path).open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    value = json.loads(line)
                except (TypeError, json.JSONDecodeError):
                    continue
                if isinstance(value, Mapping):
                    yield value
    except (OSError, UnicodeError):
        return


def _codex_usage_from_events(events: Iterable[Mapping[str, object]]) -> dict[str, object]:
    """Normalize the latest cumulative ``token_count`` event."""

    latest: Mapping[str, object] | None = None
    for event in events:
        payload = event.get("payload")
        if not isinstance(payload, Mapping) or payload.get("type") != "token_count":
            continue
        info = payload.get("info")
        if not isinstance(info, Mapping):
            continue
        usage = info.get("total_token_usage")
        if isinstance(usage, Mapping):
            latest = usage
    if latest is None:
        return unmeasured("codex", "no token_count event")
    input_tokens = _integer(latest.get("input_tokens"))
    cached = _integer(latest.get("cached_input_tokens"))
    output = _integer(latest.get("output_tokens"))
    total = _integer(latest.get("total_tokens"))
    if input_tokens is None or cached is None or output is None or total is None:
        return unmeasured("codex", "token_count event has incomplete totals")
    return TokenUsage(input_tokens, cached, output, total, "codex:token_count").as_dict()


def read_codex_rollout(path: str | Path) -> dict[str, object]:
    """Read the latest cumulative ``token_count`` event from a Codex rollout."""

    return _codex_usage_from_events(_read_jsonl(path))


def _claude_usage_from_events(events: Iterable[Mapping[str, object]]) -> dict[str, object]:
    """Sum per-message Claude ``usage`` fields.

    Claude separates new input, cache creation, and cache reads.  The
    normalized input includes all three input components; cached_input keeps
    cache reads visible, and total counts input plus output.  This keeps the
    ``uncached`` basis as input minus cached_input plus output.
    """

    input_tokens = 0
    cached = 0
    output = 0
    seen = False
    seen_messages: set[str] = set()
    for event in events:
        message = event.get("message")
        usage = message.get("usage") if isinstance(message, Mapping) else event.get("usage")
        if not isinstance(usage, Mapping):
            continue
        message_id = None
        if isinstance(message, Mapping):
            candidate_id = message.get("id") or message.get("requestId")
            if isinstance(candidate_id, str) and candidate_id:
                message_id = candidate_id
        if message_id is None:
            candidate_id = event.get("requestId")
            if isinstance(candidate_id, str) and candidate_id:
                message_id = candidate_id
        if message_id is not None:
            if message_id in seen_messages:
                continue
            seen_messages.add(message_id)
        values = {
            key: _integer(usage.get(key))
            for key in (
                "input_tokens",
                "cache_creation_input_tokens",
                "cache_read_input_tokens",
                "output_tokens",
            )
        }
        if any(value is None for value in values.values()):
            continue
        seen = True
        input_tokens += values["input_tokens"] or 0
        input_tokens += values["cache_creation_input_tokens"] or 0
        input_tokens += values["cache_read_input_tokens"] or 0
        cached += values["cache_read_input_tokens"] or 0
        output += values["output_tokens"] or 0
    if not seen:
        return unmeasured("claude", "no complete message usage")
    return TokenUsage(
        input_tokens,
        cached,
        output,
        input_tokens + output,
        "claude:usage",
    ).as_dict()


def read_claude_transcript(path: str | Path) -> dict[str, object]:
    """Sum per-message Claude ``usage`` fields."""

    return _claude_usage_from_events(_read_jsonl(path))


def read_agy_transcript(path: str | Path) -> dict[str, object]:
    """Keep Antigravity unmeasured until its host reader is contracted."""

    return unmeasured("agy", "runtime reader is deferred")


def read_runtime(runtime: str, path: str | Path) -> dict[str, object]:
    """Read one runtime record, preserving unknowns as unmeasured."""

    normalized = runtime.casefold()
    if normalized == "codex":
        return read_codex_rollout(path)
    if normalized == "claude":
        return read_claude_transcript(path)
    if normalized == "agy":
        return read_agy_transcript(path)
    return unmeasured(normalized, "runtime has no usage reader")


def cap_total(usage: Mapping[str, object], basis: str = "total") -> int | None:
    """Return the amount counted by a contract's token basis."""

    if usage.get("source") == "unmeasured":
        return None
    total = _integer(usage.get("total"))
    if basis == "total":
        return total
    if basis != "uncached":
        raise ValueError("tokens_basis must be total or uncached")
    input_tokens = _integer(usage.get("input"))
    cached = _integer(usage.get("cached_input"))
    output = _integer(usage.get("output"))
    if input_tokens is None or cached is None or output is None:
        return None
    return max(input_tokens - cached, 0) + output
