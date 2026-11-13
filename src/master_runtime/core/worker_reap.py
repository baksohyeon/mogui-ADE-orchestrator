"""Worker reap lifecycle: close settled dispatch terminals and clean up worktrees.

Exit codes:
- 2: invalid invocation or unresolved dispatch lookup
- 3: dispatch exists but is not settled
- 4: malformed JSON payload from orchestration RPC
- 5: no dispatch exists for the requested task
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Optional
from urllib.parse import urlparse


# Agent CLI comm names worth refusing a reap over — a live process here means
# a worker (or someone) is still actively sitting in this worktree, settled
# dispatch or not. Matched by basename, case-insensitively.
# ponytail: exact-name set, not a "looks like an agent" heuristic — a comm
# reported as a wrapper (e.g. `node` fronting a JS-packaged CLI) is not
# chased. Add a name here once it is measured on a real seat, not guessed.
AGENT_CLI_COMMANDS = frozenset(
    {"claude", "codex", "cursor", "cursor-agent", "agy", "grok"}
)

# Rendered media suffixes a worktree's .gitignore commonly covers. `git
# status --porcelain` never lists ignored files, so a worktree holding one of
# these loses it silently to `git worktree remove` unless this set catches it
# first. Matched by suffix, case-insensitively.
IGNORED_MEDIA_SUFFIXES = frozenset(
    {
        ".mp4",
        ".webm",
        ".mov",
        ".mkv",
        ".wav",
        ".mp3",
        ".flac",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".pdf",
    }
)

MAX_WORKER_LIST_PAGES = 20
WORKER_LIST_PAGE_LIMIT = 100

# A reaper may be given a worktree for the repository's primary branch by
# mistake. Keep the branch-protection check independent of the PR lookup.
PROTECTED_BRANCHES = frozenset({"main", "master"})

# Dropped from every subprocess env: an inherited value here would point git
# at the caller's repository (or its index/object store) instead of the one
# named by -C.
GIT_REPOSITORY_ENV_VARS = frozenset(
    {
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_COMMON_DIR",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    }
)


@dataclass(frozen=True)
class ReapRecord:
    """One dispatch reap event in the ledger."""

    task_id: str
    dispatch_id: str
    terminal_id: str
    worktree_path: Optional[str]
    actions_taken: str
    timestamp: float
    measurements: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "dispatch_id": self.dispatch_id,
            "terminal_id": self.terminal_id,
            "worktree_path": self.worktree_path,
            "actions_taken": self.actions_taken,
            "timestamp": self.timestamp,
            "measurements": self.measurements,
        }


class ReapError(Exception):
    """Reap operation failed."""

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


EXIT_NO_SUCH_TASK = 5


class DispatchState:
    """Parsed dispatch state from orca orchestration dispatch-show."""

    def __init__(self, dispatch_json: dict) -> None:
        self.raw = dispatch_json
        dispatch_payload = dispatch_json
        if isinstance(dispatch_json.get("result"), dict):
            wrapped_dispatch = dispatch_json["result"].get("dispatch")
            if isinstance(wrapped_dispatch, dict):
                dispatch_payload = wrapped_dispatch
            else:
                dispatch_payload = {}

        dispatch_id = dispatch_payload.get("dispatch_id") or dispatch_payload.get("id")
        if not dispatch_id:
            raise ReapError("Dispatch payload is missing dispatch_id/id", 4)

        self.dispatch_id = str(dispatch_id)
        self.task_id = str(dispatch_payload.get("task_id") or "")
        self.terminal_id = str(
            dispatch_payload.get("assignee_handle")
            or dispatch_payload.get("terminal_id")
            or ""
        )
        self.worktree_selector = self._first_text(
            dispatch_payload,
            "worktree_selector",
            "worktreeSelector",
            "worktree_id",
            "worktreeId",
        )
        self.agent_session_id = self._first_text(
            dispatch_payload,
            "agent_session_id",
            "agentSessionId",
            "session_id",
            "sessionId",
        )
        self.status = str(dispatch_payload.get("status", "")).upper()
        derived_worktree_path = self._derive_worktree_path(
            dispatch_payload.get("process_incarnation")
        )
        flat_worktree_path = dispatch_payload.get("worktree_path")
        self.worktree_path = (
            derived_worktree_path
            if derived_worktree_path is not None
            else (
                flat_worktree_path
                if isinstance(flat_worktree_path, str)
                and self._is_absolute_path(flat_worktree_path)
                else None
            )
        )

    def is_settled(self) -> bool:
        """True if dispatch is in a terminal state (completed/accepted/failed/abandoned)."""
        return self.status in ("COMPLETED", "ACCEPTED", "FAILED", "ABANDONED")

    def is_success(self) -> bool:
        """True if dispatch completed or was accepted."""
        return self.status in ("COMPLETED", "ACCEPTED")

    def _derive_worktree_path(self, process_incarnation: object) -> Optional[str]:
        """Extract absolute worktree path from process_incarnation when present."""
        if not isinstance(process_incarnation, str):
            return None

        match = re.fullmatch(r"[^:]+::(.+)@@.+", process_incarnation)
        if not match:
            return None

        path = match.group(1)
        if not self._is_absolute_path(path):
            return None
        return path

    def _is_absolute_path(self, path: str) -> bool:
        """True when path is absolute in either posix or windows form."""
        return PurePosixPath(path).is_absolute() or PureWindowsPath(path).is_absolute()

    @staticmethod
    def _first_text(payload: dict, *keys: str) -> Optional[str]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None


def find_worker_row_for_dispatch(workers: list, dispatch_id: str) -> Optional[dict]:
    """The worker-list row naming this dispatch id (snake_case or camelCase),
    `None` when no row matches. Shared by `WorkerReaper` and
    `dispatch_timeline` so both resolve a dispatch id to a task id the same
    way."""
    for worker in workers:
        if not isinstance(worker, dict):
            continue
        row_dispatch_id = worker.get("dispatch_id") or worker.get("dispatchId")
        if row_dispatch_id == dispatch_id:
            return worker
    return None


def resolve_task_id_from_dispatch_id(
    orca_runner: callable, dispatch_id: str
) -> Optional[str]:
    """Resolve a dispatch id to its task id via `orca orchestration
    worker-list`, the same lookup `WorkerReaper` uses. `None` on any failure
    — RPC error, malformed JSON, no matching row, or a matching row with no
    task_id — never raises."""
    code, stdout, _stderr = orca_runner(["orca", "orchestration", "worker-list", "--json"])
    if code != 0:
        return None
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    result = payload.get("result") if isinstance(payload, dict) else None
    workers = result.get("workers") if isinstance(result, dict) else None
    if not isinstance(workers, list):
        return None
    row = find_worker_row_for_dispatch(workers, dispatch_id)
    if row is None:
        return None
    task_id = row.get("task_id") or row.get("taskId")
    return str(task_id) if task_id else None


class WorkerReaper:
    """Closes settled worker terminals and cleans up worktrees."""

    def __init__(
        self,
        orca_runner: Optional[callable] = None,
        reap_ledger_path: Optional[Path] = None,
        remove_ignored_media: bool = False,
        dispatch_ledger_path: Optional[Path] = None,
    ) -> None:
        self.orca_runner = orca_runner or self._run_subprocess
        self.reap_ledger_path = reap_ledger_path
        self.remove_ignored_media = remove_ignored_media
        self.dispatch_ledger_path = dispatch_ledger_path or self._default_dispatch_ledger_path()
        self._last_landing_rule: Optional[str] = None

    def reap(
        self,
        task_id: Optional[str] = None,
        dispatch_id: Optional[str] = None,
        execute: bool = True,
        remove_ignored_media: bool = False,
    ) -> ReapRecord:
        """
        Reap a settled dispatch.

        Args:
            task_id: Task ID to look up (or dispatch_id must be provided)
            dispatch_id: Dispatch ID directly (or task_id must be provided)
            execute: If False, dry-run only
            remove_ignored_media: If True (here or on the instance), remove
                a clean, merged worktree even when it holds ignored media

        Returns:
            ReapRecord with actions taken

        Raises:
            ReapError if dispatch is not settled or reap fails
        """
        if not task_id and not dispatch_id:
            raise ReapError("Either task_id or dispatch_id must be provided", 2)

        # Fetch dispatch state
        dispatch_state = self._fetch_dispatch(task_id, dispatch_id)

        # Verify settled
        if not dispatch_state.is_settled():
            raise ReapError(
                f"Dispatch {dispatch_state.dispatch_id} is not settled "
                f"(status: {dispatch_state.status}); refusing to reap open dispatch",
                3,
            )

        actions = []
        measurements: dict[str, object] = {}
        terminal_reclaim_allowed = True

        terminal_action: Optional[str] = None
        # Measure pane membership and state before inspecting the worktree, but
        # defer the actual close whenever worktree cleanup is still conditional.
        # A settled dispatch that has not landed must retain its resume pane.
        if dispatch_state.worktree_selector:
            terminal_action, terminal_measurements = self._plan_terminal_action(
                dispatch_state, False
            )
            if not dispatch_state.worktree_path:
                terminal_action = (
                    f"terminal_left:{dispatch_state.worktree_selector}:"
                    "worktree_path_unmeasured"
                )
                terminal_measurements["terminal_reclaim_allowed"] = False
            measurements.update(terminal_measurements)
            terminal_reclaim_allowed = bool(
                terminal_measurements.get("terminal_reclaim_allowed")
            )
        elif dispatch_state.terminal_id:
            # Older ledger rows predate the worktree selector. Keep their
            # established fail-closed handle checks while new rows use the
            # worktree-membership path above.
            terminal_action, terminal_measurements = self._plan_terminal_action(
                dispatch_state, execute if not dispatch_state.worktree_path else False
            )
            measurements.update(terminal_measurements)
            # Legacy rows have no selector with which to prove worktree
            # membership. Preserve their independent terminal/worktree
            # decisions; selector-backed rows take the stricter gate above.
            terminal_reclaim_allowed = True
        if terminal_action and not dispatch_state.worktree_path:
            actions.append(terminal_action)

        # Check and possibly remove worktree
        if dispatch_state.worktree_path:
            worktree_path = Path(dispatch_state.worktree_path)
            try:
                wt_clean, wt_merged, reason = self._check_worktree_safe_to_remove(
                    worktree_path
                )
                measurements["worktree_clean"] = wt_clean
                measurements["worktree_merged"] = wt_merged
                if wt_clean and wt_merged:
                    measurements["worktree_landed_by"] = self._last_landing_rule
                    ignored_media = self._ignored_media(worktree_path)
                    measurements["worktree_ignored_media"] = (
                        None if ignored_media is None else len(ignored_media)
                    )
                    if ignored_media is None:
                        if terminal_action:
                            actions.append(terminal_action)
                        actions.append(
                            f"worktree_left:{worktree_path}:ignored_media_unmeasured"
                        )
                    elif ignored_media and not (
                        remove_ignored_media or self.remove_ignored_media
                    ):
                        if terminal_action:
                            actions.append(terminal_action)
                        actions.append(
                            f"worktree_left:{worktree_path}:ignored_media:"
                            f"{len(ignored_media)}"
                        )
                    elif dispatch_state.worktree_selector and not terminal_reclaim_allowed:
                        if terminal_action:
                            actions.append(terminal_action)
                        actions.append(
                            f"worktree_left:{worktree_path}:pane_not_idle"
                        )
                    elif execute:
                        terminals_closed = False
                        if terminal_action and terminal_action.startswith("would_close_worktree:"):
                            self._close_worktree_terminals(dispatch_state.worktree_selector or "")
                            terminals_closed = True
                            actions.append(
                                f"terminal_closed_by_worktree:{dispatch_state.worktree_selector}"
                            )
                        elif terminal_action and terminal_action.startswith("would_close_terminal:"):
                            self._close_terminal(dispatch_state.terminal_id)
                            terminals_closed = True
                            actions.append(f"terminal_closed:{dispatch_state.terminal_id}")
                        if dispatch_state.worktree_selector:
                            try:
                                self._remove_worktree(
                                    worktree_path, dispatch_state.worktree_selector
                                )
                            except ReapError as error:
                                actions.append(
                                    "cleanup_partial:"
                                    f"{'terminals_closed' if terminals_closed else 'terminals_not_closed'}:"
                                    f"worktree_remove_failed:{error}"
                                )
                                actions.append(
                                    f"worktree_remove_failed:{dispatch_state.worktree_selector}:{error}"
                                )
                            else:
                                actions.append(
                                    f"worktree_remove_requested:{worktree_path}:branch_delete_requested"
                                )
                        else:
                            (
                                branch_name,
                                branch_tip,
                                common_dir,
                                repository,
                                branch_reason,
                            ) = self._measure_branch_identity(worktree_path)
                            branch_action = self._plan_branch_deletion(
                                branch_name,
                                branch_tip,
                                common_dir,
                                repository,
                                execute=False,
                                reason=branch_reason,
                            )
                            self._remove_worktree(worktree_path)
                            actions.append(f"worktree_removed:{worktree_path}")
                            if branch_action.startswith("would_delete_branch:"):
                                actions.append(
                                    self._delete_local_branch(
                                        branch_name, branch_tip, common_dir
                                    )
                                )
                            else:
                                actions.append(branch_action)
                    else:
                        if dispatch_state.worktree_selector:
                            if terminal_action:
                                actions.append(terminal_action)
                            actions.append(
                                f"would_remove_worktree:{worktree_path}:landed_by:{self._last_landing_rule}"
                            )
                        else:
                            actions.append(f"would_remove_worktree:{worktree_path}")
                            (
                                branch_name,
                                branch_tip,
                                common_dir,
                                repository,
                                branch_reason,
                            ) = self._measure_branch_identity(worktree_path)
                            actions.append(
                                self._plan_branch_deletion(
                                    branch_name,
                                    branch_tip,
                                    common_dir,
                                    repository,
                                    execute=False,
                                    reason=branch_reason,
                                )
                            )
                else:
                    if terminal_action:
                        actions.append(terminal_action)
                    actions.append(f"worktree_left:{worktree_path}:{reason}")
            except Exception as e:
                measurements["worktree_clean"] = None
                measurements["worktree_merged"] = None
                if terminal_action:
                    actions.append(terminal_action)
                actions.append(f"worktree_left:{worktree_path}:Check failed: {e}")

        # Build record
        record = ReapRecord(
            task_id=dispatch_state.task_id,
            dispatch_id=dispatch_state.dispatch_id,
            terminal_id=dispatch_state.terminal_id,
            worktree_path=dispatch_state.worktree_path,
            actions_taken=";".join(actions),
            timestamp=time.time(),
            measurements=measurements,
        )

        # Append to ledger
        if execute and self.reap_ledger_path:
            self._append_reap_record(record)

        return record

    def _measure_branch_identity(
        self, worktree_path: Path
    ) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str], str]:
        """Measure the branch, tip, repository, and shared git directory.

        The branch and tip must be captured before removing the worktree. A
        squash merge has no ancestry signal, so the tip is later compared to
        the merged PR's ``headRefOid`` before any branch deletion is attempted.
        """

        code, branch_output, stderr = self.orca_runner(
            ["git", "-C", str(worktree_path), "branch", "--show-current"]
        )
        branch_name = branch_output.strip()
        if code != 0 or not branch_name:
            return None, None, None, None, "branch identity unavailable"

        code, tip_output, stderr = self.orca_runner(
            ["git", "-C", str(worktree_path), "rev-parse", "HEAD"]
        )
        branch_tip = tip_output.strip()
        if code != 0 or not branch_tip:
            return branch_name, None, None, None, "branch tip unavailable"

        code, common_output, stderr = self.orca_runner(
            ["git", "-C", str(worktree_path), "rev-parse", "--git-common-dir"]
        )
        raw_common_dir = common_output.rstrip("\r\n")
        if code != 0 or not raw_common_dir:
            return branch_name, branch_tip, None, None, "git common directory unavailable"

        common_dir = os.path.abspath(os.path.join(str(worktree_path), raw_common_dir))
        code, remote_output, _stderr = self.orca_runner(
            ["git", "-C", str(worktree_path), "remote", "get-url", "origin"]
        )
        repository = self._repository_from_remote(remote_output.strip())
        if code != 0 or not repository:
            return branch_name, branch_tip, common_dir, None, "repository unavailable"
        return branch_name, branch_tip, common_dir, repository, ""

    @staticmethod
    def _repository_from_remote(remote_url: str) -> Optional[str]:
        """Convert a Git remote URL to the ``gh --repo`` selector format."""

        remote_url = remote_url.strip()
        if not remote_url:
            return None
        if "://" in remote_url:
            parsed = urlparse(remote_url)
            host = parsed.hostname
            path = parsed.path
        else:
            at_index = remote_url.rfind("@")
            separator = remote_url.find(":", at_index)
            if at_index < 0 or separator <= at_index:
                return None
            host = remote_url[at_index + 1 : separator]
            path = remote_url[separator + 1 :]
        if not host or not path:
            return None
        path = path.strip("/")
        if path.endswith(".git"):
            path = path[:-4]
        if len(path.split("/")) < 2:
            return None
        return f"{host}/{path}"

    def _plan_branch_deletion(
        self,
        branch_name: Optional[str],
        branch_tip: Optional[str],
        common_dir: Optional[str],
        repository: Optional[str],
        *,
        execute: bool,
        reason: str,
    ) -> str:
        """Delete a local branch only after a merged PR proves its exact tip.

        ``git branch -d`` is an ancestry check and cannot prove a squash merge.
        ``-D`` is therefore allowed only after GitHub reports ``MERGED`` and
        the local tip equals that PR's ``headRefOid``. Any missing measurement
        leaves the branch in place with a machine-readable reason.
        """

        display_name = branch_name or "<unknown>"
        if not branch_name:
            return f"branch_left:{display_name}:{reason or 'branch name unavailable'}"
        if branch_name in PROTECTED_BRANCHES:
            return f"branch_left:{branch_name}:protected branch"
        if not branch_tip:
            return f"branch_left:{branch_name}:{reason or 'branch tip unavailable'}"
        if not common_dir:
            return f"branch_left:{branch_name}:{reason or 'git common directory unavailable'}"
        if not repository:
            return f"branch_left:{branch_name}:{reason or 'repository unavailable'}"

        code, stdout, stderr = self.orca_runner(
            [
                "gh",
                "pr",
                "view",
                branch_name,
                "--repo",
                repository,
                "--json",
                "state,headRefOid",
            ]
        )
        if code != 0:
            error = stderr.lower()
            if "no pull request" in error or "not found" in error:
                return f"branch_left:{branch_name}:no PR"
            return f"branch_left:{branch_name}:gh unavailable"
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return f"branch_left:{branch_name}:gh unavailable"
        if isinstance(payload, dict):
            prs = [payload]
        elif isinstance(payload, list):
            prs = payload
        else:
            return f"branch_left:{branch_name}:gh unavailable"
        if not prs:
            return f"branch_left:{branch_name}:no PR"

        merged_head_oid: Optional[str] = None
        merged_pr_seen = False
        for pr in prs:
            if not isinstance(pr, dict):
                continue
            if str(pr.get("state", "")).upper() == "MERGED":
                merged_pr_seen = True
                candidate = pr.get("headRefOid")
                if isinstance(candidate, str) and candidate:
                    merged_head_oid = candidate
                    break
        if merged_head_oid is None:
            if merged_pr_seen:
                return f"branch_left:{branch_name}:gh unavailable"
            return f"branch_left:{branch_name}:not merged"
        if branch_tip != merged_head_oid:
            return f"branch_left:{branch_name}:tip differs from PR head"
        if not execute:
            return f"would_delete_branch:{branch_name}"

        return self._delete_local_branch(branch_name, branch_tip, common_dir)

    def _delete_local_branch(
        self,
        branch_name: Optional[str],
        expected_tip: Optional[str],
        common_dir: Optional[str],
    ) -> str:
        """Delete a prevalidated branch through the shared git directory."""

        if not branch_name or not expected_tip or not common_dir:
            return f"branch_left:{branch_name or '<unknown>'}:branch identity unavailable"
        code, stdout, _stderr = self.orca_runner(
            [
                "git",
                f"--git-dir={common_dir}",
                "rev-parse",
                f"refs/heads/{branch_name}",
            ]
        )
        if code != 0 or stdout.strip() != expected_tip:
            return f"branch_left:{branch_name}:tip differs from PR head"
        code, _stdout, _stderr = self.orca_runner(
            [f"git", f"--git-dir={common_dir}", "branch", "-D", branch_name]
        )
        if code != 0:
            return f"branch_left:{branch_name}:git branch -D failed"
        return f"branch_deleted:{branch_name}"

    def _plan_terminal_action(
        self, dispatch_state: DispatchState, execute: bool
    ) -> tuple[str, dict[str, object]]:
        """Measure the three pane preconditions and decide the terminal action.

        A pane is closed only when all three hold: present in `orca terminal
        list`, not claimed by any currently-`dispatched` worker-list row, and
        no agent CLI process's cwd is inside the dispatch's worktree. A
        measurement that could not be taken (`None`) refuses, the same as a
        measurement that failed — a refusal is cheap, a wrong close is not.
        """
        if dispatch_state.worktree_selector:
            return self._plan_worktree_terminal_action(dispatch_state, execute)

        terminal_id = dispatch_state.terminal_id
        measurements: dict[str, object] = {}
        measurements["terminal_reclaim_allowed"] = False

        present = self._terminal_present(terminal_id)
        measurements["terminal_present"] = present
        if present is None:
            return f"terminal_left:{terminal_id}:presence_unmeasured", measurements
        if not present:
            measurements["terminal_reclaim_allowed"] = True
            return f"terminal_left:{terminal_id}:pane_absent", measurements

        reused_by = self._reused_by_dispatched(terminal_id, dispatch_state.dispatch_id)
        measurements["terminal_reused_by"] = reused_by
        if reused_by is None:
            return f"terminal_left:{terminal_id}:reuse_unmeasured", measurements
        if reused_by:
            return f"terminal_left:{terminal_id}:reused_by:{reused_by}", measurements

        if not dispatch_state.worktree_path:
            measurements["agent_process"] = None
            return f"terminal_left:{terminal_id}:worktree_unknown_for_agent_check", measurements

        agent_process = self._agent_process_in_worktree(Path(dispatch_state.worktree_path))
        measurements["agent_process"] = agent_process
        if agent_process is None:
            return f"terminal_left:{terminal_id}:agent_process_unmeasured", measurements
        if agent_process:
            return f"terminal_left:{terminal_id}:agent_process:{agent_process}", measurements

        if execute:
            self._close_terminal(terminal_id)
            measurements["terminal_reclaim_allowed"] = True
            return f"terminal_closed:{terminal_id}", measurements
        measurements["terminal_reclaim_allowed"] = True
        return f"would_close_terminal:{terminal_id}", measurements

    def _plan_worktree_terminal_action(
        self, dispatch_state: DispatchState, execute: bool
    ) -> tuple[str, dict[str, object]]:
        """Select panes by Orca worktree membership and require every pane idle."""
        selector = dispatch_state.worktree_selector or ""
        measurements: dict[str, object] = {
            "worktree_selector": selector,
            "terminal_reclaim_allowed": False,
        }
        terminals = self._terminal_entries()
        if terminals is None:
            return (
                f"terminal_left:{selector}:worktree_membership_unmeasured",
                measurements,
            )
        members = [
            terminal
            for terminal in terminals
            if self._terminal_in_worktree(terminal, selector, dispatch_state.worktree_path)
        ]
        if any(
            not isinstance(item.get("handle"), str) or not item["handle"]
            for item in members
        ):
            return (
                f"terminal_left:{selector}:worktree_membership_unmeasured",
                measurements,
            )
        handles = [item["handle"] for item in members]
        measurements["worktree_terminal_handles"] = handles
        if not handles:
            measurements["terminal_reclaim_allowed"] = True
            return f"terminal_left:{selector}:pane_absent", measurements

        reused_by = self._reused_by_dispatched_worktree(
            selector, dispatch_state.worktree_path, handles, dispatch_state.dispatch_id
        )
        measurements["worktree_reused_by"] = reused_by
        if reused_by is None:
            return f"terminal_left:{selector}:reuse_unmeasured", measurements
        if reused_by:
            return f"terminal_left:{selector}:reused_by:{reused_by}", measurements

        states = self._pane_states(handles)
        measurements["pane_states"] = states
        if states is None:
            return f"terminal_left:{selector}:pane_state_unmeasured", measurements
        busy = [handle for handle in handles if states.get(handle) != "idle"]
        if busy:
            measurements["busy_panes"] = busy
            busy_text = ",".join(f"{handle}:{states.get(handle, 'unknown')}" for handle in busy)
            return f"terminal_left:{selector}:pane_not_idle:{busy_text}", measurements

        measurements["terminal_reclaim_allowed"] = True
        if execute:
            self._close_worktree_terminals(selector)
            return f"terminal_closed_by_worktree:{selector}", measurements
        return f"would_close_worktree:{selector}", measurements

    def _terminal_entries(self) -> Optional[list[dict]]:
        code, stdout, _stderr = self.orca_runner(["orca", "terminal", "list", "--json"])
        if code != 0:
            return None
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return None
        result = payload.get("result") if isinstance(payload, dict) else None
        terminals = result.get("terminals") if isinstance(result, dict) else None
        if not isinstance(terminals, list) or not all(
            isinstance(terminal, dict) for terminal in terminals
        ):
            return None
        return terminals

    @staticmethod
    def _normalize_worktree_selector(value: str) -> str:
        return value[3:] if value.startswith("id:") else value

    @classmethod
    def _terminal_in_worktree(
        cls,
        terminal: dict,
        selector: str,
        worktree_path: Optional[str],
    ) -> bool:
        terminal_selector = str(
            terminal.get("worktreeId") or terminal.get("worktree_id") or ""
        )
        expected_selector = cls._normalize_worktree_selector(selector)
        if terminal_selector and (
            cls._normalize_worktree_selector(terminal_selector) == expected_selector
        ):
            return True

        terminal_path = str(
            terminal.get("worktreePath") or terminal.get("worktree_path") or ""
        )
        expected_path = worktree_path or (
            selector[5:] if selector.startswith("path:") else ""
        )
        if not terminal_path or not expected_path:
            return False
        return os.path.normcase(os.path.realpath(terminal_path)) == os.path.normcase(
            os.path.realpath(expected_path)
        )

    def _pane_states(self, handles: list[str]) -> Optional[dict[str, str]]:
        repo_root = Path(__file__).resolve().parents[3]
        sweep_path = repo_root / "master-ops" / "scripts" / "worker-pane-sweep"
        if not sweep_path.is_file():
            return None
        code, stdout, _stderr = self.orca_runner([str(sweep_path)])
        states: dict[str, str] = {}
        valid_states = {"working", "idle", "approval", "start-screen", "update", "limit", "shell", "unknown"}
        for line in stdout.splitlines():
            fields = line.split(None, 3)
            if len(fields) < 3 or fields[1] not in valid_states:
                continue
            prefix = fields[2]
            for handle in handles:
                if handle.startswith(prefix):
                    states[handle] = fields[1]
        if code != 0:
            return None
        if any(handle not in states for handle in handles):
            return None
        return states

    def _terminal_present(self, terminal_id: str) -> Optional[bool]:
        """`None` when presence could not be measured — never read as absent."""

        code, stdout, _stderr = self.orca_runner(["orca", "terminal", "list", "--json"])
        if code != 0:
            return None
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return None
        result = payload.get("result") if isinstance(payload, dict) else None
        terminals = result.get("terminals") if isinstance(result, dict) else None
        if not isinstance(terminals, list):
            return None
        handles = {t.get("handle") for t in terminals if isinstance(t, dict)}
        return terminal_id in handles

    def _reused_by_dispatched(
        self, terminal_id: str, own_dispatch_id: str
    ) -> Optional[str]:
        """The reusing dispatch id, `""` when not reused, `None` when unmeasured."""

        rows = self._all_worker_list_rows()
        if rows is None:
            return None
        for row in rows:
            if not isinstance(row, dict):
                continue
            handle = (
                row.get("agentTerminalHandle")
                or row.get("assignee_handle")
                or row.get("terminal_id")
            )
            if handle != terminal_id:
                continue
            status = str(row.get("dispatchStatus") or row.get("status") or "").lower()
            if status != "dispatched":
                continue
            row_dispatch_id = row.get("dispatchId") or row.get("dispatch_id")
            if row_dispatch_id == own_dispatch_id:
                continue
            return str(row_dispatch_id) if row_dispatch_id else "unknown"
        return ""

    def _reused_by_dispatched_worktree(
        self,
        selector: str,
        worktree_path: Optional[str],
        handles: list[str],
        own_dispatch_id: str,
    ) -> Optional[str]:
        """Find a newer dispatched row that still owns this worktree.

        Selector-backed cleanup closes every pane in the selected worktree, so
        matching only a terminal handle is insufficient. A row is considered
        the same worktree when its selector, canonical path, or measured pane
        handle matches the dispatch being reaped.
        """
        rows = self._all_worker_list_rows()
        if rows is None:
            return None
        expected_selector = self._normalize_worktree_selector(selector)
        expected_path = (
            os.path.normcase(os.path.realpath(worktree_path))
            if worktree_path
            else ""
        )
        for row in rows:
            if not isinstance(row, dict):
                continue
            status = str(row.get("dispatchStatus") or row.get("status") or "").lower()
            if status != "dispatched":
                continue
            row_dispatch_id = row.get("dispatchId") or row.get("dispatch_id")
            if row_dispatch_id == own_dispatch_id:
                continue
            row_selector = str(
                row.get("worktreeSelector")
                or row.get("worktree_selector")
                or row.get("worktreeId")
                or row.get("worktree_id")
                or ""
            )
            row_path = str(row.get("worktreePath") or row.get("worktree_path") or "")
            row_handle = str(
                row.get("agentTerminalHandle")
                or row.get("assignee_handle")
                or row.get("terminal_id")
                or ""
            )
            same_selector = bool(
                row_selector
                and self._normalize_worktree_selector(row_selector) == expected_selector
            )
            same_path = bool(
                expected_path
                and row_path
                and os.path.normcase(os.path.realpath(row_path)) == expected_path
            )
            if same_selector or same_path or row_handle in handles:
                return str(row_dispatch_id) if row_dispatch_id else "unknown"
        return ""

    def _all_worker_list_rows(self) -> Optional[list[dict]]:
        """Every worker-list row across every Run, paginated. `None` on a
        malformed shape or when pagination cannot finish (`hasMore` with no
        cursor, or the page limit exhausted) — a partial list is unmeasurable,
        never "no reuse"."""

        rows: list[dict] = []
        cursor: Optional[str] = None
        for page_index in range(MAX_WORKER_LIST_PAGES):
            cmd = [
                "orca",
                "orchestration",
                "worker-list",
                "--limit",
                str(WORKER_LIST_PAGE_LIMIT),
                "--json",
            ]
            if cursor:
                cmd.extend(["--cursor", cursor])
            code, stdout, _stderr = self.orca_runner(cmd)
            if code != 0:
                return None
            try:
                payload = json.loads(stdout)
            except json.JSONDecodeError:
                return None
            result = payload.get("result") if isinstance(payload, dict) else None
            if not isinstance(result, dict):
                return None
            workers = result.get("workers")
            if not isinstance(workers, list) or not all(
                isinstance(row, dict) for row in workers
            ):
                return None
            rows.extend(workers)
            page = result.get("page")
            if not isinstance(page, dict):
                return None
            cursor = page.get("nextCursor")
            if page.get("hasMore"):
                if not cursor or page_index == MAX_WORKER_LIST_PAGES - 1:
                    return None
            else:
                break
        return rows

    def _agent_process_in_worktree(self, worktree_path: Path) -> Optional[str]:
        """`"<pid>:<comm>"` for the first agent CLI found, `""` when none,
        `None` when unmeasured — including when an agent-matching process's
        cwd could not be resolved at all, not just when the scan itself fails."""

        code, stdout, _stderr = self.orca_runner(["ps", "-axo", "pid=,comm="])
        if code != 0:
            return None
        target = os.path.realpath(str(worktree_path))
        unmeasured = False
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            pid_str, comm = parts
            comm_name = os.path.basename(comm.strip()).lower()
            if comm_name not in AGENT_CLI_COMMANDS:
                continue
            cwd = self._process_cwd(pid_str)
            if not cwd:
                unmeasured = True
                continue
            resolved_cwd = os.path.realpath(cwd)
            if resolved_cwd == target or resolved_cwd.startswith(target + os.sep):
                return f"{pid_str}:{comm_name}"
        return None if unmeasured else ""

    def _process_cwd(self, pid: str) -> Optional[str]:
        """`lsof` first (the contract's primary tool), `/proc/<pid>/cwd` as fallback."""

        code, stdout, _stderr = self.orca_runner(
            ["lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"]
        )
        if code == 0:
            for line in stdout.splitlines():
                if line.startswith("n"):
                    return line[1:]
        code, stdout, _stderr = self.orca_runner(["readlink", f"/proc/{pid}/cwd"])
        if code == 0 and stdout.strip():
            return stdout.strip()
        return None

    def _fetch_dispatch(
        self, task_id: Optional[str], dispatch_id: Optional[str]
    ) -> DispatchState:
        """Fetch dispatch state via orca orchestration dispatch-show."""
        lookup_task_id = task_id
        if not lookup_task_id and dispatch_id:
            lookup_task_id = self._resolve_task_id_from_dispatch_id(dispatch_id)

        cmd = ["orca", "orchestration", "dispatch-show", "--json"]
        if lookup_task_id:
            cmd.extend(["--task", lookup_task_id])

        code, stdout, stderr = self.orca_runner(cmd)
        if code != 0:
            raise ReapError(
                f"Failed to fetch dispatch: {stderr or stdout}",
                code,
            )

        try:
            payload = json.loads(stdout)
            result = payload.get("result") if isinstance(payload, dict) else None
            if isinstance(result, dict):
                dispatch_payload = result.get("dispatch")
                if not isinstance(dispatch_payload, dict):
                    if dispatch_id and not task_id and lookup_task_id:
                        raise ReapError(
                            f"no dispatch for task {lookup_task_id}",
                            EXIT_NO_SUCH_TASK,
                        )
                    if lookup_task_id:
                        raise ReapError(
                            f"no such task: {lookup_task_id}",
                            EXIT_NO_SUCH_TASK,
                        )
                    raise ReapError("no such task", EXIT_NO_SUCH_TASK)
            dispatch_state = DispatchState(payload)
            self._apply_ledger_metadata(dispatch_state)
            return dispatch_state
        except (json.JSONDecodeError, ValueError) as e:
            raise ReapError(f"Could not parse dispatch JSON: {e}", 4)

    @staticmethod
    def _default_dispatch_ledger_path() -> Path:
        state_dir = os.environ.get("MOGUI_STATE_DIR")
        if state_dir:
            return Path(state_dir) / "dispatch-ledger.jsonl"
        return Path.home() / ".mogui" / "dispatch-ledger.jsonl"

    def _apply_ledger_metadata(self, dispatch_state: DispatchState) -> None:
        """Apply dispatch-time selector/session measurements to the RPC row."""
        paths = []
        for path in (self.dispatch_ledger_path, self.reap_ledger_path):
            if path and path not in paths:
                paths.append(path)
        for ledger_path in paths:
            try:
                lines = ledger_path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in reversed(lines):
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, dict):
                    continue
                entry_dispatch = entry.get("job_id") or entry.get("dispatch_id")
                if entry_dispatch != dispatch_state.dispatch_id:
                    continue
                selector = DispatchState._first_text(
                    entry, "worktree_selector", "worktreeSelector", "worktree_id", "worktreeId"
                )
                ledger_worktree_path = DispatchState._first_text(
                    entry, "worktree_path", "worktreePath"
                )
                session_id = DispatchState._first_text(
                    entry,
                    "agent_session_id",
                    "agentSessionId",
                    "session_id",
                    "sessionId",
                )
                if selector and not dispatch_state.worktree_selector:
                    dispatch_state.worktree_selector = selector
                if (
                    ledger_worktree_path
                    and not dispatch_state.worktree_path
                    and dispatch_state._is_absolute_path(ledger_worktree_path)
                ):
                    dispatch_state.worktree_path = ledger_worktree_path
                if session_id and not dispatch_state.agent_session_id:
                    dispatch_state.agent_session_id = session_id
                if dispatch_state.worktree_selector or dispatch_state.agent_session_id:
                    return

    def _resolve_task_id_from_dispatch_id(self, dispatch_id: str) -> str:
        """Resolve task ID from dispatch ID using worker-list rows."""
        code, stdout, stderr = self.orca_runner(
            ["orca", "orchestration", "worker-list", "--json"]
        )
        if code != 0:
            raise ReapError(
                f"Failed to resolve dispatch via worker-list: {stderr or stdout}",
                code,
            )

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ReapError(f"Could not parse worker-list JSON: {exc}", 4)

        result = payload.get("result") if isinstance(payload, dict) else None
        workers = result.get("workers") if isinstance(result, dict) else None
        if not isinstance(workers, list):
            workers = []

        row = find_worker_row_for_dispatch(workers, dispatch_id)
        if row is None:
            raise ReapError(
                f"Could not resolve dispatch {dispatch_id}: worker-list had no row for it",
                2,
            )
        task_id = row.get("task_id") or row.get("taskId")
        if task_id:
            return str(task_id)
        raise ReapError(
            f"worker-list row for dispatch {dispatch_id} has no task_id",
            2,
        )

    def _close_terminal(self, terminal_id: str) -> None:
        """Close a terminal via orca terminal close."""
        code, stdout, stderr = self.orca_runner(
            ["orca", "terminal", "close", "--terminal", terminal_id]
        )
        if code != 0:
            raise ReapError(f"Failed to close terminal {terminal_id}: {stderr}", code)

    def _close_worktree_terminals(self, selector: str) -> None:
        """Close every pane in one measured worktree through Orca."""
        code, _stdout, stderr = self.orca_runner(
            ["orca", "terminal", "close", "--worktree", selector, "--all", "--json"]
        )
        if code != 0:
            raise ReapError(
                f"Failed to close terminals for worktree {selector}: {stderr}", code
            )

    def _check_worktree_safe_to_remove(self, worktree_path: Path) -> tuple[bool, bool, str]:
        """
        Check if worktree can be safely removed.

        Returns:
            (is_clean, is_merged, reason_if_not)
        """
        self._last_landing_rule = None
        if not worktree_path.exists():
            return False, False, f"Worktree path does not exist"

        # Check git status
        code, stdout, stderr = self.orca_runner(
            ["git", "-C", str(worktree_path), "status", "--porcelain"]
        )
        if code != 0:
            return False, False, f"Not a git repo or git error: {stderr}"

        # __pycache__ litter does not count as dirty: .gitignore already
        # covers it everywhere this runs, but a stray untracked copy (a
        # worktree created before .gitignore existed, or copied by hand)
        # should not by itself block an otherwise-clean removal.
        dirty_lines = [
            line
            for line in stdout.splitlines()
            if line.strip()
            and not (line.startswith("?? ") and "__pycache__/" in line[3:])
        ]
        if dirty_lines:
            return False, False, f"Worktree has uncommitted changes"

        # Get current branch
        code, branch_output, stderr = self.orca_runner(
            ["git", "-C", str(worktree_path), "branch", "--show-current"]
        )
        if code != 0:
            return False, False, f"Could not get current branch: {stderr}"

        current_branch = branch_output.strip()
        if not current_branch:
            return False, False, "Could not get current branch: detached HEAD"

        # Check if branch is topologically merged.
        code, stdout, stderr = self.orca_runner(
            ["git", "-C", str(worktree_path), "branch", "-a", "--merged", "origin/main"]
        )
        if code != 0:
            return False, False, f"Could not check merge status: {stderr}"

        merged_branches = [
            line.strip().lstrip("* ")
            for line in stdout.strip().split("\n")
            if line.strip()
        ]

        if current_branch in merged_branches:
            self._last_landing_rule = "ancestry"
            return True, True, ""

        squash_included, squash_reason = self._branch_changes_included_in_origin_main(
            worktree_path
        )
        if squash_included:
            self._last_landing_rule = "content"
            return True, True, ""

        return False, False, (
            f"Current branch {current_branch} is not merged to origin/main"
            f" ({squash_reason})"
        )

    def _ignored_media(self, worktree_path: Path) -> Optional[list[str]]:
        """Ignored paths under `worktree_path` whose suffix is in
        `IGNORED_MEDIA_SUFFIXES` (case-insensitive), from `git status
        --porcelain --ignored --untracked-files=all -z`'s `!! ` records.
        `--untracked-files=all` makes git list individual files inside an
        ignored directory (e.g. `renders/`) instead of just the directory;
        `-z` delimits each record with NUL instead of a trailing newline and
        never quotes the path, so a path with a space or a non-ASCII name
        comes through intact. `None` on a git failure, never read as "no
        ignored media"."""
        code, stdout, _stderr = self.orca_runner(
            [
                "git",
                "-C",
                str(worktree_path),
                "status",
                "--porcelain",
                "--ignored",
                "--untracked-files=all",
                "-z",
            ]
        )
        if code != 0:
            return None
        return [
            record[3:]
            for record in stdout.split("\0")
            if record.startswith("!! ")
            and Path(record[3:]).suffix.lower() in IGNORED_MEDIA_SUFFIXES
        ]

    def _branch_changes_included_in_origin_main(
        self, worktree_path: Path
    ) -> tuple[bool, str]:
        """
        True when the branch's changed paths have the same content in origin/main.

        Squash merges erase ancestry, so `git branch --merged origin/main` cannot
        prove inclusion. Compare only paths changed from the merge base. This
        avoids treating unrelated changes that landed in origin/main as evidence
        that the worker branch landed.
        """
        code, branch_output, stderr = self.orca_runner(
            ["git", "-C", str(worktree_path), "branch", "--show-current"]
        )
        branch_name = branch_output.strip()
        if code == 0 and branch_name:
            code, merge_base_output, stderr = self.orca_runner(
                ["git", "-C", str(worktree_path), "merge-base", "origin/main", branch_name]
            )
            merge_base = merge_base_output.strip()
            if code == 0 and merge_base:
                code, changed_output, stderr = self.orca_runner(
                    [
                        "git",
                        "--literal-pathspecs",
                        "-C",
                        str(worktree_path),
                        "diff",
                        "--name-only",
                        "-z",
                        "--no-renames",
                        merge_base,
                        branch_name,
                    ]
                )
                if code == 0:
                    changed_paths = [path for path in changed_output.split("\0") if path]
                    if not changed_paths:
                        return True, "branch changes are already included in origin/main"
                    diff_command = [
                        "git",
                        "--literal-pathspecs",
                        "-C",
                        str(worktree_path),
                        "diff",
                        "--quiet",
                        "origin/main",
                        branch_name,
                        "--",
                        *changed_paths,
                    ]
                    diff_code, diff_stdout, diff_stderr = self.orca_runner(diff_command)
                    if diff_code == 0:
                        return True, "branch changes are already included in origin/main"
                    if diff_code == 1:
                        return (
                            False,
                            "branch changes are not included in origin/main "
                            f"(differing paths: {', '.join(changed_paths)})",
                        )
                    return False, f"content comparison failed: {diff_stderr or diff_stdout}"

        # Keep a compatibility fallback for older ledger fixtures that do not
        # expose a branch ref to the runner. Real dispatches take the measured
        # merge-base and path-scoped diff above.
        return self._legacy_branch_changes_included_in_origin_main(worktree_path)

    def _legacy_branch_changes_included_in_origin_main(
        self, worktree_path: Path
    ) -> tuple[bool, str]:
        code, main_tree_stdout, stderr = self.orca_runner(
            ["git", "-C", str(worktree_path), "rev-parse", "origin/main^{tree}"]
        )
        if code != 0:
            return False, f"could not resolve origin/main tree: {stderr}"

        code, merge_tree_stdout, stderr = self.orca_runner(
            [
                "git",
                "-C",
                str(worktree_path),
                "merge-tree",
                "--write-tree",
                "origin/main",
                "HEAD",
            ]
        )
        if code != 0:
            return False, f"virtual merge failed: {stderr or merge_tree_stdout}"

        main_tree = main_tree_stdout.strip()
        merge_tree = merge_tree_stdout.splitlines()[0].strip() if merge_tree_stdout else ""
        if merge_tree == main_tree:
            return True, "branch changes are already included in origin/main"

        return False, "branch changes are not included in origin/main"

    def _remove_worktree(
        self, worktree_path: Path, worktree_selector: Optional[str] = None
    ) -> None:
        """Remove a worktree through Orca when its selector was measured."""
        if worktree_selector:
            code, _stdout, stderr = self.orca_runner(
                [
                    "orca",
                    "worktree",
                    "rm",
                    "--worktree",
                    worktree_selector,
                    "--delete-branch",
                    "--json",
                ]
            )
            if code != 0:
                raise ReapError(
                    f"Failed to remove worktree {worktree_selector}: {stderr}", code
                )
            return

        # Legacy rows without a dispatch-time selector retain the old Git
        # cleanup path. New dispatch rows always use the Orca path above.
        # Resolve the shared git dir, then remove through --git-dir. The remove
        # must not run with the worktree as git's cwd: Windows cannot delete a
        # process's current directory. It also must not depend on the caller's cwd.
        # --path-format=absolute needs Git 2.31+, which this project does not
        # require, so resolve the (possibly relative) default output ourselves
        # against the -C directory the command ran in.
        code, stdout, stderr = self.orca_runner(
            ["git", "-C", str(worktree_path), "rev-parse", "--git-common-dir"]
        )
        raw_common_dir = stdout.rstrip("\r\n")
        if code != 0 or not raw_common_dir:
            raise ReapError(
                f"Failed to resolve git common dir for {worktree_path}: {stderr}", code or 1
            )
        common_dir = os.path.abspath(os.path.join(str(worktree_path), raw_common_dir))
        code, stdout, stderr = self.orca_runner(
            ["git", f"--git-dir={common_dir}", "worktree", "remove", str(worktree_path)]
        )
        if code != 0:
            raise ReapError(f"Failed to remove worktree {worktree_path}: {stderr}", code)

    def _append_reap_record(self, record: ReapRecord) -> None:
        """Append reap record to the ledger."""
        if not self.reap_ledger_path:
            return

        self.reap_ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with self.reap_ledger_path.open("a", encoding="utf-8") as f:
            entry = {
                "event": "reap",
                "ts": record.timestamp,
                **record.to_dict(),
            }
            f.write(json.dumps(entry, sort_keys=True, separators=(",", ":")))
            f.write("\n")

    def _run_subprocess(
        self, command: list[str]
    ) -> tuple[int, str, str]:
        """Run a subprocess and return (code, stdout, stderr)."""
        # Strip inherited git-repository env vars so every git call the reaper
        # makes (safety checks and removal alike) resolves against the -C
        # repository it was told to inspect, not whatever repo the caller's
        # process happens to be sitting in.
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in GIT_REPOSITORY_ENV_VARS
        }
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                env=env,
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return 1, "", f"Command timed out: {' '.join(command)}"
        except Exception as e:
            return 1, "", str(e)
