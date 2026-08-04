"""Worker reap lifecycle: close settled dispatch terminals and clean up worktrees."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ReapRecord:
    """One dispatch reap event in the ledger."""

    task_id: str
    dispatch_id: str
    terminal_id: str
    worktree_path: Optional[str]
    actions_taken: str
    timestamp: float

    def to_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "dispatch_id": self.dispatch_id,
            "terminal_id": self.terminal_id,
            "worktree_path": self.worktree_path,
            "actions_taken": self.actions_taken,
            "timestamp": self.timestamp,
        }


class ReapError(Exception):
    """Reap operation failed."""

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class DispatchState:
    """Parsed dispatch state from orca orchestration dispatch-show."""

    def __init__(self, dispatch_json: dict) -> None:
        self.raw = dispatch_json
        self.dispatch_id = str(dispatch_json.get("dispatch_id", ""))
        self.task_id = str(dispatch_json.get("task_id", ""))
        self.terminal_id = str(dispatch_json.get("terminal_id", ""))
        self.status = str(dispatch_json.get("status", "")).upper()
        self.worktree_path = dispatch_json.get("worktree_path")
        if self.worktree_path:
            self.worktree_path = str(self.worktree_path)

    def is_settled(self) -> bool:
        """True if dispatch is in a terminal state (completed/accepted)."""
        return self.status in ("COMPLETED", "ACCEPTED", "FAILED", "ABANDONED")

    def is_success(self) -> bool:
        """True if dispatch completed or was accepted."""
        return self.status in ("COMPLETED", "ACCEPTED")


class WorkerReaper:
    """Closes settled worker terminals and cleans up worktrees."""

    def __init__(
        self,
        orca_runner: Optional[callable] = None,
        reap_ledger_path: Optional[Path] = None,
    ) -> None:
        self.orca_runner = orca_runner or self._run_subprocess
        self.reap_ledger_path = reap_ledger_path

    def reap(
        self,
        task_id: Optional[str] = None,
        dispatch_id: Optional[str] = None,
        execute: bool = True,
    ) -> ReapRecord:
        """
        Reap a settled dispatch.

        Args:
            task_id: Task ID to look up (or dispatch_id must be provided)
            dispatch_id: Dispatch ID directly (or task_id must be provided)
            execute: If False, dry-run only

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

        # Plan reap actions
        actions = []
        warnings = []

        # Close terminal
        if dispatch_state.terminal_id:
            if execute:
                self._close_terminal(dispatch_state.terminal_id)
            actions.append(f"terminal_closed:{dispatch_state.terminal_id}")

        # Check and possibly remove worktree
        if dispatch_state.worktree_path:
            worktree_path = Path(dispatch_state.worktree_path)
            try:
                wt_clean, wt_merged, reason = self._check_worktree_safe_to_remove(
                    worktree_path
                )
                if wt_clean and wt_merged:
                    if execute:
                        self._remove_worktree(worktree_path)
                    actions.append(f"worktree_removed:{worktree_path}")
                else:
                    actions.append(f"worktree_left:{worktree_path}")
                    warnings.append(reason)
            except Exception as e:
                warnings.append(f"Could not check worktree: {e}")
                actions.append(f"worktree_left:{worktree_path}")

        # Build record
        record = ReapRecord(
            task_id=dispatch_state.task_id,
            dispatch_id=dispatch_state.dispatch_id,
            terminal_id=dispatch_state.terminal_id,
            worktree_path=dispatch_state.worktree_path,
            actions_taken=";".join(actions),
            timestamp=time.time(),
        )

        # Append to ledger
        if execute and self.reap_ledger_path:
            self._append_reap_record(record)

        return record

    def _fetch_dispatch(
        self, task_id: Optional[str], dispatch_id: Optional[str]
    ) -> DispatchState:
        """Fetch dispatch state via orca orchestration dispatch-show."""
        cmd = ["orca", "orchestration", "dispatch-show", "--json"]
        if task_id:
            cmd.extend(["--task", task_id])
        elif dispatch_id:
            cmd.extend(["--dispatch", dispatch_id])

        code, stdout, stderr = self.orca_runner(cmd)
        if code != 0:
            raise ReapError(
                f"Failed to fetch dispatch: {stderr or stdout}",
                code,
            )

        try:
            payload = json.loads(stdout)
            return DispatchState(payload)
        except (json.JSONDecodeError, ValueError) as e:
            raise ReapError(f"Could not parse dispatch JSON: {e}", 4)

    def _close_terminal(self, terminal_id: str) -> None:
        """Close a terminal via orca terminal close."""
        code, stdout, stderr = self.orca_runner(
            ["orca", "terminal", "close", terminal_id]
        )
        if code != 0:
            raise ReapError(f"Failed to close terminal {terminal_id}: {stderr}", code)

    def _check_worktree_safe_to_remove(self, worktree_path: Path) -> tuple[bool, bool, str]:
        """
        Check if worktree can be safely removed.

        Returns:
            (is_clean, is_merged, reason_if_not)
        """
        if not worktree_path.exists():
            return True, True, ""

        # Check git status
        code, stdout, stderr = self.orca_runner(
            ["git", "-C", str(worktree_path), "status", "--porcelain"]
        )
        if code != 0:
            return False, False, f"Not a git repo or git error: {stderr}"

        if stdout.strip():
            return False, False, f"Worktree has uncommitted changes"

        # Check if branch is merged
        code, stdout, stderr = self.orca_runner(
            ["git", "-C", str(worktree_path), "branch", "-a", "--merged", "origin/main"]
        )
        if code != 0:
            return False, False, f"Could not check merge status: {stderr}"

        # Get current branch
        code, branch_output, stderr = self.orca_runner(
            ["git", "-C", str(worktree_path), "branch", "--show-current"]
        )
        if code != 0:
            return False, False, f"Could not get current branch: {stderr}"

        current_branch = branch_output.strip()
        merged_branches = [line.strip() for line in stdout.strip().split("\n") if line.strip()]

        if current_branch not in merged_branches:
            return False, False, f"Current branch {current_branch} is not merged to origin/main"

        return True, True, ""

    def _remove_worktree(self, worktree_path: Path) -> None:
        """Remove a worktree safely."""
        # Use git worktree remove if it's a linked worktree
        code, stdout, stderr = self.orca_runner(
            ["git", "worktree", "remove", str(worktree_path)]
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
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return 1, "", f"Command timed out: {' '.join(command)}"
        except Exception as e:
            return 1, "", str(e)
