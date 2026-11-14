"""Token accounting for supervised worker dispatches.

The provider formats are intentionally kept at this boundary.  Callers get a
small, provider-neutral result and can distinguish a measured zero from a
runtime that has no usable usage record.
"""

from __future__ import annotations

import json
import math
import os
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


RUNTIME_NAMES = frozenset({"codex", "claude", "agy", "cursor"})
DEFAULT_QUOTA_THRESHOLD_PERCENT = 15.0


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


def read_codex_rollout(path: str | Path) -> dict[str, object]:
    """Read the latest cumulative ``token_count`` event from a Codex rollout."""

    latest: Mapping[str, object] | None = None
    for event in _read_jsonl(path):
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


def read_claude_transcript(path: str | Path) -> dict[str, object]:
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
    for event in _read_jsonl(path):
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


def p90(values: Iterable[int]) -> int | None:
    """Return an inclusive, rounded-up p90, or ``None`` for no records."""

    numbers = sorted(value for value in values if isinstance(value, int) and value >= 0)
    if not numbers:
        return None
    if len(numbers) == 1:
        return numbers[0]
    return int(math.ceil(statistics.quantiles(numbers, n=10, method="inclusive")[8]))


def _record_model(runtime: str, path: Path) -> str | None:
    for event in _read_jsonl(path):
        if runtime == "codex":
            if event.get("type") == "session_meta":
                payload = event.get("payload")
                if isinstance(payload, Mapping):
                    model = payload.get("model") or payload.get("model_id")
                    if isinstance(model, str) and model:
                        return model
            payload = event.get("payload")
            if isinstance(payload, Mapping) and payload.get("type") == "turn_context":
                model = payload.get("model")
                if isinstance(model, str) and model:
                    return model
        elif runtime == "claude":
            message = event.get("message")
            model = message.get("model") if isinstance(message, Mapping) else None
            model = model or event.get("requestedModel")
            if isinstance(model, str) and model:
                return model
    return None


def _codex_roots(root: str | Path | None = None) -> tuple[Path, ...]:
    """Resolve Codex session roots without treating an empty value as ``.``."""

    if root:
        candidate = Path(root).expanduser()
        return (candidate,) if candidate.is_dir() else ()
    explicit = os.environ.get("DISPATCH_CODEX_SESSION_ROOT", "").strip()
    if explicit:
        candidate = Path(explicit).expanduser()
        return (candidate,) if candidate.is_dir() else ()
    accounts = os.environ.get("CODEX_ACCOUNTS_DIR", "").strip()
    if accounts:
        account_root = Path(accounts).expanduser()
    elif (Path.home() / ".codex" / "sessions").is_dir():
        return ((Path.home() / ".codex" / "sessions").resolve(),)
    elif os.name == "posix" and sys_platform_is_darwin():
        account_root = Path.home() / "Library" / "Application Support" / "orca" / "codex-accounts"
    else:
        account_root = Path.home() / ".local" / "share" / "orca" / "codex-accounts"
    try:
        return tuple(
            (account / "home" / "sessions").resolve()
            for account in account_root.iterdir()
            if account.is_dir() and (account / "home" / "sessions").is_dir()
        )
    except OSError:
        return ()


def sys_platform_is_darwin() -> bool:
    return os.uname().sysname == "Darwin" if hasattr(os, "uname") else False


def tier_defaults(
    tier_policy: str | Path,
    *,
    codex_root: str | Path | None = None,
    claude_root: str | Path | None = None,
    basis: str = "total",
) -> tuple[dict[str, int], dict[str, int]]:
    """Compute per-tier p90 totals from existing Codex and Claude records.

    The second return value is the number of records contributing to each tier.
    A missing tier is deliberately absent from both mappings.
    """

    if basis not in {"total", "uncached"}:
        raise ValueError("tokens_basis must be total or uncached")
    try:
        policy = json.loads(Path(tier_policy).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}, {}
    tiers = policy.get("tiers") if isinstance(policy, Mapping) else None
    if not isinstance(tiers, Mapping):
        return {}, {}
    model_tiers = {
        str(model).casefold(): str(tier)
        for tier, models in tiers.items()
        if isinstance(models, list)
        for model in models
    }
    claude_value = (
        str(claude_root).strip()
        if claude_root is not None
        else os.environ.get("DISPATCH_CLAUDE_SESSION_ROOT", "").strip()
    )
    claude_path = Path(claude_value).expanduser() if claude_value else Path.home() / ".claude" / "projects"
    roots: dict[str, tuple[Path, ...]] = {
        "codex": _codex_roots(codex_root),
        "claude": (claude_path,),
    }
    totals: dict[str, list[int]] = {}
    counts: dict[str, int] = {}
    for runtime, runtime_roots in roots.items():
        for root in runtime_roots:
            if not root.is_dir():
                continue
            for path in root.rglob("*.jsonl"):
                model = _record_model(runtime, path)
                tier = model_tiers.get(model.casefold()) if model else None
                if tier is None:
                    continue
                usage = read_runtime(runtime, path)
                total = cap_total(usage, basis)
                if total is None:
                    continue
                totals.setdefault(tier, []).append(total)
                counts[tier] = counts.get(tier, 0) + 1
    return {tier: value for tier, values in totals.items() if (value := p90(values)) is not None}, counts


def latest_codex_quota(
    root: str | Path | None = None,
    *,
    now: float | None = None,
) -> dict[str, object]:
    """Return the newest valid Codex weekly quota snapshot."""

    roots = _codex_roots(root)
    if not roots:
        return {"known": False, "runtime": "codex", "why": "no session root"}
    current = time.time() if now is None else now
    newest: tuple[float, Mapping[str, object]] | None = None
    for base in roots:
        if not base.is_dir():
            continue
        for path in base.rglob("*.jsonl"):
            for event in _read_jsonl(path):
                payload = event.get("payload")
                if not isinstance(payload, Mapping) or payload.get("type") != "token_count":
                    continue
                rate_limits = payload.get("rate_limits")
                if not isinstance(rate_limits, Mapping):
                    rate_limits = event.get("rate_limits")
                if not isinstance(rate_limits, Mapping):
                    continue
                weekly = None
                weekly_name = ""
                for key in ("primary", "secondary"):
                    candidate_limit = rate_limits.get(key)
                    if not isinstance(candidate_limit, Mapping):
                        continue
                    window_minutes = _integer(candidate_limit.get("window_minutes"))
                    if window_minutes == 10080 or (key == "secondary" and window_minutes is None):
                        weekly = candidate_limit
                        weekly_name = key
                        break
                if weekly is None:
                    continue
                used = weekly.get("used_percent")
                reset = _number(weekly.get("resets_at"))
                stamp = _timestamp(event.get("timestamp")) or path.stat().st_mtime
                if not isinstance(used, (int, float)) or isinstance(used, bool) or not math.isfinite(float(used)):
                    continue
                candidate = {
                    "used_percent": float(used),
                    "resets_at": reset,
                    "timestamp": stamp,
                    "source_name": weekly_name,
                }
                if newest is None or stamp > newest[0]:
                    newest = (stamp, candidate)
    if newest is None:
        return {"known": False, "runtime": "codex", "why": "no weekly snapshot"}
    stamp, candidate = newest
    reset = candidate.get("resets_at")
    if isinstance(reset, (int, float)) and current >= reset:
        return {"known": False, "runtime": "codex", "why": "snapshot passed reset"}
    window = 10080 * 60
    if current - stamp > window:
        return {"known": False, "runtime": "codex", "why": "snapshot older than weekly window"}
    return {
        "known": True,
        "runtime": "codex",
        "remaining_percent": max(0.0, 100.0 - float(candidate["used_percent"])),
        "used_percent": float(candidate["used_percent"]),
        "timestamp": stamp,
        "age_seconds": max(0.0, current - stamp),
        "resets_at": reset,
        "source": f"codex:token_count.rate_limits.{candidate['source_name']}",
    }


def quota_status(runtime: str, *, root: str | Path | None = None, now: float | None = None) -> dict[str, object]:
    if runtime.casefold() == "codex":
        return latest_codex_quota(root, now=now)
    return {"known": False, "runtime": runtime, "why": f"no non-interactive source for {runtime}"}


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def _timestamp(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if not isinstance(value, str):
        return None
    try:
        from datetime import datetime

        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError, OverflowError):
        return None
