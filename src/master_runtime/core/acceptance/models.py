"""Shared value types for the acceptance loop."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional, Sequence, Tuple, Union

from master_runtime.core.acceptance.casebook import VerificationCase
from master_runtime.core.acceptance.proposer import DEFAULT_PROPOSER_TIMEOUT_SECONDS
from master_runtime.core.acceptance.verdict import CaseResult


BASELINE_LABEL = "baseline"
CANDIDATE_LABEL_FORMAT = "iter-{0:03d}"
CANDIDATE_FILENAME = "candidate.json"
TASK_FILENAME = "task.md"
PROPOSAL_FILENAME = "proposal.md"
IN_PLACE_ATTR = "mutates_workspace_in_place"


@dataclass(frozen=True)
class Candidate:
    """One proposed deliverable.

    ``ref`` is an opaque handle the evaluator resolves (a git rev, a worktree path, a
    patch file). The core never interprets it, which keeps this package free of any
    repository-implementation knowledge.
    """

    label: str
    ref: str = ""
    surfaces: Tuple[str, ...] = ()
    summary: str = ""

    @property
    def changed(self) -> bool:
        """Return whether the proposer declared any changed surface."""

        return bool(self.surfaces)

    def to_dict(self) -> Dict[str, object]:
        """Serialize the candidate."""

        return {
            "label": self.label,
            "ref": self.ref,
            "surfaces": list(self.surfaces),
            "summary": self.summary,
        }


@dataclass(frozen=True)
class ProposerContext:
    """Everything a proposer needs for one iteration.

    The visible cases and failures are not repeated here: they are already written
    into ``workspace_dir`` as ``casebook_visible.json`` and ``visible_failures.json``,
    which is what a CLI proposer actually reads. ``current`` stays because a library
    proposer needs the base ref to derive its candidate ref.
    """

    iteration: int
    workspace_dir: Path
    current: Candidate


@dataclass(frozen=True)
class AcceptanceConfig:
    """Configuration for one acceptance run."""

    name: str
    run_dir: Union[str, Path]
    workspace_root: Union[str, Path] = "."
    max_iterations: int = 3
    proposer_runtime: str = ""
    proposer_model: Optional[str] = None
    proposer_timeout_seconds: int = DEFAULT_PROPOSER_TIMEOUT_SECONDS

    def to_dict(self) -> Dict[str, object]:
        """Serialize the config."""

        return {
            "name": self.name,
            "run_dir": str(self.run_dir),
            "workspace_root": str(self.workspace_root),
            "max_iterations": self.max_iterations,
            "proposer_runtime": self.proposer_runtime,
            "proposer_model": self.proposer_model,
            "proposer_timeout_seconds": self.proposer_timeout_seconds,
        }


Evaluator = Callable[[Candidate, Sequence[VerificationCase]], Sequence[CaseResult]]
Proposer = Callable[[ProposerContext], Optional[Candidate]]


def mark_in_place(target):
    """Declare that a proposer or evaluator mutates the target workspace in place.

    A candidate that is a ref (git rev, worktree) leaves the previous state intact, so
    the loop can iterate past a rejection freely. A proposer that edits the workspace
    directly does not: the next iteration would evaluate the rejected tree. Declaring
    the property here lets :func:`run_acceptance_loop` refuse that combination instead
    of leaving the guard in one CLI's argument parser.
    """

    setattr(target, IN_PLACE_ATTR, True)
    return target


def mutates_workspace_in_place(target) -> bool:
    """Return whether a proposer or evaluator declared in-place mutation."""

    return bool(getattr(target, IN_PLACE_ATTR, False))
