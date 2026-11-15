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
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


RUNTIME_NAMES = frozenset({"codex", "claude", "agy", "cursor"})
DEFAULT_QUOTA_THRESHOLD_PERCENT = 15.0
TIER_DEFAULT_WINDOW_SECONDS = 30 * 24 * 60 * 60
TIER_DEFAULT_MIN_RECORDS = 10
TIER_DEFAULT_TIMEOUT_SECONDS = 2.0
CODEX_QUOTA_MAX_FILES = 20
CODEX_QUOTA_MAX_BYTES_PER_FILE = 64 * 1024


class _TierDefaultReadTimeout(Exception):
    """Signal that a transcript read crossed the bounded default deadline."""


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


def _read_jsonl(
    path: str | Path, *, deadline: float | None = None
) -> Iterable[Mapping[str, object]]:
    try:
        with Path(path).open(encoding="utf-8") as stream:
            for line in stream:
                if deadline is not None and time.monotonic() >= deadline:
                    raise _TierDefaultReadTimeout
                try:
                    value = json.loads(line)
                except (TypeError, json.JSONDecodeError):
                    continue
                if isinstance(value, Mapping):
                    yield value
    except (OSError, UnicodeError):
        return


def _read_events(
    path: str | Path, *, deadline: float | None = None
) -> tuple[Mapping[str, object], ...] | None:
    """Materialize one record so a default recompute can inspect it once."""

    try:
        return tuple(_read_jsonl(path, deadline=deadline))
    except _TierDefaultReadTimeout:
        return None


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


def p90(values: Iterable[int]) -> int | None:
    """Return an inclusive, rounded-up p90, or ``None`` for no records."""

    numbers = sorted(value for value in values if isinstance(value, int) and value >= 0)
    if not numbers:
        return None
    if len(numbers) == 1:
        return numbers[0]
    return int(math.ceil(statistics.quantiles(numbers, n=10, method="inclusive")[8]))


def _runtime_usage_from_events(
    runtime: str, events: Iterable[Mapping[str, object]]
) -> dict[str, object]:
    normalized = runtime.casefold()
    if normalized == "codex":
        return _codex_usage_from_events(events)
    if normalized == "claude":
        return _claude_usage_from_events(events)
    if normalized == "agy":
        return unmeasured("agy", "runtime reader is deferred")
    return unmeasured(normalized, "runtime has no usage reader")


def _record_model_from_events(runtime: str, events: Iterable[Mapping[str, object]]) -> str | None:
    for event in events:
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


def _record_model(runtime: str, path: Path) -> str | None:
    return _record_model_from_events(runtime, _read_jsonl(path))


def _is_worker_cwd(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    normalized = value.replace("\\", "/").rstrip("/")
    marker = "/.orca/worktrees/"
    if marker not in normalized:
        return False
    _, _, worktree = normalized.partition(marker)
    return bool(worktree)


def _record_is_worker_events(events: Iterable[Mapping[str, object]]) -> bool:
    """Use the host-recorded cwd shape to select dispatched worker sessions."""

    saw_cwd = False
    for event in events:
        values = [event.get("session_kind")]
        payload = event.get("payload")
        if isinstance(payload, Mapping):
            values.append(payload.get("session_kind"))
        for value in values:
            if isinstance(value, str) and value.casefold() in {"master", "interactive"}:
                return False
        cwd_values = [event.get("cwd")]
        if isinstance(payload, Mapping):
            cwd_values.append(payload.get("cwd"))
        for value in cwd_values:
            if value is None:
                continue
            saw_cwd = True
            if not _is_worker_cwd(value):
                return False
    return saw_cwd


def _record_is_worker(path: Path) -> bool:
    return _record_is_worker_events(_read_jsonl(path))


def _inspect_default_record(
    runtime: str, path: Path, *, deadline: float | None = None
) -> tuple[bool, str | None, dict[str, object]] | None:
    """Read one transcript once for worker evidence, model, and usage."""

    events = _read_events(path, deadline=deadline)
    if events is None:
        return None
    return (
        _record_is_worker_events(events),
        _record_model_from_events(runtime, events),
        _runtime_usage_from_events(runtime, events),
    )


def _codex_roots(root: str | Path | None = None) -> tuple[Path, ...]:
    """Resolve Codex session roots without treating an empty value as ``.``."""

    if root:
        candidate = Path(root).expanduser()
        return (candidate,) if candidate.is_dir() else ()
    explicit = os.environ.get("DISPATCH_CODEX_SESSION_ROOT", "").strip()
    if explicit:
        candidate = Path(explicit).expanduser()
        return (candidate,) if candidate.is_dir() else ()
    codex_home = os.environ.get("CODEX_HOME", "").strip()
    if codex_home:
        home = Path(codex_home).expanduser()
        candidates = (home / "sessions", home / "home" / "sessions")
        return tuple(candidate.resolve() for candidate in candidates if candidate.is_dir())
    configured_accounts = os.environ.get("CODEX_ACCOUNTS_DIR")
    if configured_accounts is not None:
        if not configured_accounts.strip():
            return ()
        account_root = Path(configured_accounts).expanduser()
    elif os.name == "posix" and sys_platform_is_darwin():
        account_root = Path.home() / "Library" / "Application Support" / "orca" / "codex-accounts"
    else:
        account_root = Path.home() / ".local" / "share" / "orca" / "codex-accounts"
    try:
        account_roots = tuple(
            (account / "home" / "sessions").resolve()
            for account in account_root.iterdir()
            if account.is_dir() and (account / "home" / "sessions").is_dir()
        )
    except OSError:
        account_roots = ()
    if account_roots:
        return account_roots
    if configured_accounts is None and (Path.home() / ".codex" / "sessions").is_dir():
        return ((Path.home() / ".codex" / "sessions").resolve(),)
    return ()


def sys_platform_is_darwin() -> bool:
    return os.uname().sysname == "Darwin" if hasattr(os, "uname") else False


def _jsonl_paths_newest_first_bounded(
    root: Path, deadline: float | None = None
) -> tuple[tuple[Path, ...], bool]:
    """List candidates newest first, stopping when a caller's deadline expires."""

    try:
        paths = root.rglob("*.jsonl")
    except OSError:
        return (), False
    candidates: list[tuple[float, Path]] = []
    timed_out = False
    try:
        for path in paths:
            if deadline is not None and time.monotonic() >= deadline:
                timed_out = True
                break
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            candidates.append((mtime, path))
    except OSError:
        timed_out = False
    ordered = tuple(
        path
        for _, path in sorted(candidates, key=lambda item: (item[0], str(item[1])), reverse=True)
    )
    return ordered, timed_out


def _jsonl_paths_newest_first(root: Path) -> tuple[Path, ...]:
    """List readable candidates newest first without trusting directory metadata."""

    paths, _ = _jsonl_paths_newest_first_bounded(root)
    return paths


def _tier_defaults_cache_path(cache_path: str | Path | None) -> Path:
    if cache_path is not None:
        return Path(cache_path).expanduser()
    configured = os.environ.get("DISPATCH_TOKEN_BUDGET_CACHE", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".mogui" / "token-budget-defaults.json"


def _tier_default_base_signature(
    tier_policy: str | Path,
    basis: str,
    roots: Mapping[str, tuple[Path, ...]],
) -> dict[str, object]:
    try:
        policy_mtime = Path(tier_policy).stat().st_mtime
    except OSError:
        policy_mtime = None
    return {
        "policy": str(Path(tier_policy).expanduser()),
        "policy_mtime": policy_mtime,
        "basis": basis,
        "window_seconds": TIER_DEFAULT_WINDOW_SECONDS,
        "minimum_records": TIER_DEFAULT_MIN_RECORDS,
        "roots": {
            runtime: [str(root) for root in runtime_roots]
            for runtime, runtime_roots in roots.items()
        },
    }


def _cache_base_signature(signature: object) -> dict[str, object] | None:
    if not isinstance(signature, Mapping):
        return None
    return {str(key): value for key, value in signature.items() if key != "inputs"}


def _cache_maps(cached: Mapping[str, object]) -> tuple[dict[str, int], dict[str, int]] | None:
    defaults = cached.get("defaults")
    counts = cached.get("counts")
    if not isinstance(defaults, Mapping) or not isinstance(counts, Mapping):
        return None
    default_values: dict[str, int] = {}
    count_values: dict[str, int] = {}
    for key, value in defaults.items():
        number = _integer(value)
        if number is not None:
            default_values[str(key)] = number
    for key, value in counts.items():
        number = _integer(value)
        if number is not None:
            count_values[str(key)] = number
    return default_values, count_values


def _cache_file_info_by_path(value: object) -> dict[str, dict[str, object]] | None:
    if not isinstance(value, list):
        return None
    result: dict[str, dict[str, object]] = {}
    for item in value:
        if not isinstance(item, Mapping):
            return None
        path = item.get("path")
        mtime = item.get("mtime")
        size = item.get("size")
        if not isinstance(path, str) or not isinstance(mtime, (int, float)) or not isinstance(size, int):
            return None
        result[path] = {"path": path, "mtime": mtime, "size": size}
    return result


def _cache_discovery(cached: Mapping[str, object]) -> dict[str, dict[str, dict[str, object]]] | None:
    discovery = cached.get("discovery")
    if not isinstance(discovery, Mapping):
        return None
    result: dict[str, dict[str, dict[str, object]]] = {}
    for runtime in ("codex", "claude"):
        files = _cache_file_info_by_path(discovery.get(runtime))
        if files is None:
            return None
        result[runtime] = files
    return result


def _cache_worker_files(cached: Mapping[str, object]) -> dict[str, dict[str, dict[str, object]]] | None:
    signature = cached.get("signature")
    if not isinstance(signature, Mapping):
        return None
    inputs = signature.get("inputs")
    if not isinstance(inputs, Mapping):
        return None
    result: dict[str, dict[str, dict[str, object]]] = {}
    for runtime in ("codex", "claude"):
        runtime_input = inputs.get(runtime)
        if not isinstance(runtime_input, Mapping):
            return None
        files = _cache_file_info_by_path(runtime_input.get("files"))
        if files is None:
            return None
        result[runtime] = files
    return result


def _cache_records(cached: Mapping[str, object]) -> dict[str, list[dict[str, object]]] | None:
    records = cached.get("records")
    if not isinstance(records, Mapping):
        return None
    result: dict[str, list[dict[str, object]]] = {}
    for runtime in ("codex", "claude"):
        runtime_records = records.get(runtime)
        if not isinstance(runtime_records, list):
            return None
        checked: list[dict[str, object]] = []
        for record in runtime_records:
            if not isinstance(record, Mapping):
                return None
            path = record.get("path")
            mtime = record.get("mtime")
            size = record.get("size")
            tier = record.get("tier")
            total = record.get("total")
            if (
                not isinstance(path, str)
                or not isinstance(mtime, (int, float))
                or not isinstance(size, int)
                or not isinstance(tier, str)
                or _integer(total) is None
            ):
                return None
            checked.append(
                {
                    "path": path,
                    "mtime": mtime,
                    "size": size,
                    "tier": tier,
                    "total": _integer(total),
                }
            )
        result[runtime] = checked
    return result


def _cache_payload(
    base_signature: Mapping[str, object],
    candidate_info: Mapping[str, Mapping[str, dict[str, object]]],
    records: Mapping[str, list[dict[str, object]]],
    defaults: Mapping[str, int],
    counts: Mapping[str, int],
) -> dict[str, object]:
    inputs: dict[str, object] = {}
    for runtime in ("codex", "claude"):
        worker_files = [
            {key: record[key] for key in ("path", "mtime", "size")}
            for record in records.get(runtime, [])
        ]
        inputs[runtime] = {
            "count": len(worker_files),
            "newest_mtime": max((item["mtime"] for item in worker_files), default=None),
            "files": sorted(worker_files, key=lambda item: str(item["path"])),
        }
    discovery = {
        runtime: sorted(files.values(), key=lambda item: str(item["path"]))
        for runtime, files in candidate_info.items()
    }
    return {
        "signature": {**dict(base_signature), "inputs": inputs},
        "discovery": discovery,
        "records": {runtime: list(records.get(runtime, [])) for runtime in ("codex", "claude")},
        "defaults": dict(defaults),
        "counts": dict(counts),
    }


def _write_cache_atomic(path: Path, payload: Mapping[str, object]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
    except OSError:
        return


def _tier_defaults_timeout(
    cached: Mapping[str, object] | None,
    *,
    base_signature: Mapping[str, object],
    status: str,
) -> tuple[dict[str, int], dict[str, int], str]:
    if cached is not None and _cache_base_signature(cached.get("signature")) == dict(base_signature):
        cached_maps = _cache_maps(cached)
        if cached_maps is not None:
            return cached_maps[0], cached_maps[1], status + "-cache"
    return {}, {}, status + "-no-default"


def tier_defaults_with_status(
    tier_policy: str | Path,
    *,
    codex_root: str | Path | None = None,
    claude_root: str | Path | None = None,
    basis: str = "total",
    now: float | None = None,
    cache_path: str | Path | None = None,
    timeout_seconds: float = TIER_DEFAULT_TIMEOUT_SECONDS,
) -> tuple[dict[str, int], dict[str, int], str]:
    """Compute per-tier p90 totals from existing Codex and Claude records.

    The second return value is the number of records contributing to each tier.
    A missing tier is deliberately absent from both mappings.
    """

    if basis not in {"total", "uncached"}:
        raise ValueError("tokens_basis must be total or uncached")
    try:
        policy = json.loads(Path(tier_policy).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}, {}, "policy-unavailable"
    tiers = policy.get("tiers") if isinstance(policy, Mapping) else None
    if not isinstance(tiers, Mapping):
        return {}, {}, "policy-unavailable"
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
    current = time.time() if now is None else now
    cutoff = current - TIER_DEFAULT_WINDOW_SECONDS
    try:
        timeout = float(timeout_seconds)
    except (TypeError, ValueError):
        timeout = TIER_DEFAULT_TIMEOUT_SECONDS
    deadline = time.monotonic() + max(timeout, 0.0)
    cache_file = _tier_defaults_cache_path(cache_path)
    try:
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        cached = None
    base_signature = _tier_default_base_signature(tier_policy, basis, roots)
    cached_mapping = cached if isinstance(cached, Mapping) else None
    if time.monotonic() >= deadline:
        return _tier_defaults_timeout(
            cached_mapping,
            base_signature=base_signature,
            status="timeout",
        )
    candidate_paths: dict[str, tuple[Path, ...]] = {}
    candidate_info: dict[str, dict[str, dict[str, object]]] = {}
    listing_timed_out = False
    for runtime, runtime_roots in roots.items():
        paths: list[Path] = []
        info: dict[str, dict[str, object]] = {}
        for root in runtime_roots:
            if time.monotonic() >= deadline:
                listing_timed_out = True
                break
            if not root.is_dir():
                continue
            root_paths, bounded_out = _jsonl_paths_newest_first_bounded(root, deadline)
            if bounded_out:
                listing_timed_out = True
                break
            for path in root_paths:
                if time.monotonic() >= deadline:
                    listing_timed_out = True
                    break
                try:
                    stat = path.stat()
                    if stat.st_mtime >= cutoff:
                        paths.append(path)
                        info[str(path)] = {
                            "path": str(path),
                            "mtime": stat.st_mtime,
                            "size": stat.st_size,
                        }
                except OSError:
                    continue
            if listing_timed_out:
                break
        candidate_paths[runtime] = tuple(paths)
        candidate_info[runtime] = info
        if listing_timed_out:
            break
    if listing_timed_out or time.monotonic() >= deadline:
        return _tier_defaults_timeout(
            cached_mapping,
            base_signature=base_signature,
            status="timeout",
        )

    cache_ready = False
    cached_discovery = None
    cached_workers = None
    cached_records = None
    cached_maps = None
    if cached_mapping is not None and _cache_base_signature(cached_mapping.get("signature")) == base_signature:
        cached_discovery = _cache_discovery(cached_mapping)
        cached_workers = _cache_worker_files(cached_mapping)
        cached_records = _cache_records(cached_mapping)
        cached_maps = _cache_maps(cached_mapping)
        cache_ready = all(value is not None for value in (cached_discovery, cached_workers, cached_records, cached_maps))
    preinspected: dict[tuple[str, str], tuple[bool, str | None, dict[str, object]]] = {}
    if cache_ready:
        assert cached_discovery is not None
        assert cached_workers is not None
        assert cached_records is not None
        assert cached_maps is not None
        worker_changed = False
        for runtime in ("codex", "claude"):
            current_info = candidate_info.get(runtime, {})
            known_info = cached_discovery.get(runtime, {})
            current_paths = set(current_info)
            known_paths = set(known_info)
            for path in current_paths - known_paths:
                if time.monotonic() >= deadline:
                    return _tier_defaults_timeout(
                        cached_mapping,
                        base_signature=base_signature,
                        status="timeout",
                    )
                inspected = _inspect_default_record(runtime, Path(path), deadline=deadline)
                if inspected is None:
                    return _tier_defaults_timeout(
                        cached_mapping,
                        base_signature=base_signature,
                        status="timeout",
                    )
                preinspected[(runtime, path)] = inspected
                if inspected[0]:
                    worker_changed = True
                    break
            if worker_changed:
                break
            for path, metadata in cached_workers.get(runtime, {}).items():
                if path not in current_info or current_info[path] != metadata:
                    worker_changed = True
                    break
            if worker_changed:
                break
        if not worker_changed:
            return cached_maps[0], cached_maps[1], "cache-hit"

    totals: dict[str, list[int]] = {}
    counts: dict[str, int] = {}
    records: dict[str, list[dict[str, object]]] = {"codex": [], "claude": []}
    for runtime, paths in candidate_paths.items():
        for path in paths:
            if time.monotonic() >= deadline:
                return _tier_defaults_timeout(
                    cached_mapping,
                    base_signature=base_signature,
                    status="timeout",
                )
            inspected = preinspected.get((runtime, str(path)))
            if inspected is None:
                inspected = _inspect_default_record(runtime, path, deadline=deadline)
            if inspected is None or time.monotonic() >= deadline:
                return _tier_defaults_timeout(
                    cached_mapping,
                    base_signature=base_signature,
                    status="timeout",
                )
            is_worker, model, usage = inspected
            if not is_worker:
                continue
            tier = model_tiers.get(model.casefold()) if model else None
            if tier is None:
                continue
            total = cap_total(usage, basis)
            if total is None:
                continue
            totals.setdefault(tier, []).append(total)
            counts[tier] = counts.get(tier, 0) + 1
            metadata = candidate_info[runtime].get(str(path))
            if metadata is None:
                continue
            records[runtime].append({**metadata, "tier": tier, "total": total})
    defaults = {
        tier: value
        for tier, values in totals.items()
        if counts.get(tier, 0) >= TIER_DEFAULT_MIN_RECORDS
        and (value := p90(values)) is not None
    }
    if time.monotonic() < deadline:
        _write_cache_atomic(
            cache_file,
            _cache_payload(base_signature, candidate_info, records, defaults, counts),
        )
    return defaults, counts, "recomputed"


def tier_defaults(
    tier_policy: str | Path,
    *,
    codex_root: str | Path | None = None,
    claude_root: str | Path | None = None,
    basis: str = "total",
    now: float | None = None,
    cache_path: str | Path | None = None,
) -> tuple[dict[str, int], dict[str, int]]:
    defaults, counts, _ = tier_defaults_with_status(
        tier_policy,
        codex_root=codex_root,
        claude_root=claude_root,
        basis=basis,
        now=now,
        cache_path=cache_path,
    )
    return defaults, counts


def _codex_quota_roots(root: str | Path | None = None) -> tuple[Path, ...]:
    """Resolve exactly one worker account for quota reads, or remain unknown."""

    if root:
        candidate = Path(root).expanduser()
        return (candidate,) if candidate.is_dir() else ()
    explicit = os.environ.get("DISPATCH_CODEX_SESSION_ROOT", "").strip()
    if explicit:
        candidate = Path(explicit).expanduser()
        return (candidate,) if candidate.is_dir() else ()
    roots = _codex_roots()
    if len(roots) == 1:
        return roots
    return ()


def _codex_quota_tail(path: Path) -> tuple[Mapping[str, object] | None, bool]:
    """Read a bounded tail and stop at the newest rate-limits event.

    The boolean records that a token-count event carried a rate-limits field,
    including a null field. A null newest event must not fall through to an
    older snapshot from the same file.
    """

    try:
        size = path.stat().st_size
        with path.open("rb") as stream:
            offset = max(0, size - CODEX_QUOTA_MAX_BYTES_PER_FILE)
            stream.seek(offset)
            data = stream.read(CODEX_QUOTA_MAX_BYTES_PER_FILE)
    except (OSError, UnicodeError):
        return None, False
    if offset:
        _, _, data = data.partition(b"\n")
    try:
        lines = data.splitlines()
    except (AttributeError, TypeError):
        return None, False
    for raw_line in reversed(lines):
        try:
            event = json.loads(raw_line)
        except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(event, Mapping):
            continue
        payload = event.get("payload")
        if not isinstance(payload, Mapping) or payload.get("type") != "token_count":
            continue
        if "rate_limits" in payload:
            rate_limits = payload.get("rate_limits")
        elif "rate_limits" in event:
            rate_limits = event.get("rate_limits")
        else:
            continue
        return event, True
    return None, False


def _codex_quota_candidate_from_event(
    path: Path, event: Mapping[str, object] | None
) -> Mapping[str, object] | None:
    if event is None:
        return None
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        return None
    rate_limits = payload.get("rate_limits")
    if not isinstance(rate_limits, Mapping):
        rate_limits = event.get("rate_limits")
    if not isinstance(rate_limits, Mapping):
        return None
    # The dispatch design defines the primary 10080-minute window as the
    # weekly account guard. A secondary window, or a limit without an
    # explicit window, is not assumed to be weekly.
    weekly = rate_limits.get("primary")
    if not isinstance(weekly, Mapping) or _integer(weekly.get("window_minutes")) != 10080:
        return None
    used = weekly.get("used_percent")
    if not isinstance(used, (int, float)) or isinstance(used, bool) or not math.isfinite(float(used)):
        return None
    reset = _number(weekly.get("resets_at"))
    try:
        path_mtime = path.stat().st_mtime
    except OSError:
        return None
    stamp = _timestamp(event.get("timestamp")) or path_mtime
    return {
        "used_percent": float(used),
        "resets_at": reset,
        "timestamp": stamp,
        "source_name": "primary",
    }

def latest_codex_quota(
    root: str | Path | None = None,
    *,
    now: float | None = None,
) -> dict[str, object]:
    """Return the newest valid Codex weekly quota snapshot."""

    roots = _codex_quota_roots(root)
    if not roots:
        return {"known": False, "runtime": "codex", "why": "account unresolved"}
    current = time.time() if now is None else now
    newest_candidate: Mapping[str, object] | None = None
    for base in roots:
        if not base.is_dir():
            continue
        for path in _jsonl_paths_newest_first(base)[:CODEX_QUOTA_MAX_FILES]:
            event, saw_rate_limits = _codex_quota_tail(path)
            if not saw_rate_limits:
                continue
            newest_candidate = _codex_quota_candidate_from_event(path, event)
            break
        else:
            continue
        break
    if newest_candidate is None:
        return {"known": False, "runtime": "codex", "why": "no weekly snapshot"}
    candidate = newest_candidate
    stamp = float(candidate["timestamp"])
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
