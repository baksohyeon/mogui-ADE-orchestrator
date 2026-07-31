"""Deterministic acceptance loop for master-dispatched worker deliverables."""

from master_runtime.core.acceptance.casebook import (
    CaseBook,
    CaseBookError,
    CaseOrigin,
    CaseSplit,
    RegressionLog,
    VerificationCase,
    load_casebook,
    read_casebook,
)
from master_runtime.core.acceptance.config import (
    AcceptanceConfigError,
    LoadedConfig,
    load_acceptance_config,
)
from master_runtime.core.acceptance.evaluators import command_evaluator
from master_runtime.core.acceptance.layout import AcceptanceRunLayout
from master_runtime.core.acceptance.loop import (
    cli_proposer,
    read_candidate,
    run_acceptance_loop,
)
from master_runtime.core.acceptance.models import (
    BASELINE_LABEL,
    AcceptanceConfig,
    Candidate,
    Evaluator,
    Proposer,
    ProposerContext,
    mark_in_place,
)
from master_runtime.core.acceptance.process import ProcessResult, run_process
from master_runtime.core.acceptance.proposer import (
    ProposerError,
    ProposerRequest,
    invoke_cli_proposer,
)
from master_runtime.core.acceptance.report import AcceptanceReport, IterationRecord
from master_runtime.core.acceptance.verdict import (
    AcceptanceReason,
    AcceptanceVerdict,
    CaseResult,
    Scorecard,
    decide,
    score_results,
)

__all__ = [
    "AcceptanceConfig",
    "AcceptanceConfigError",
    "AcceptanceReason",
    "AcceptanceReport",
    "AcceptanceRunLayout",
    "AcceptanceVerdict",
    "BASELINE_LABEL",
    "Candidate",
    "CaseBook",
    "CaseBookError",
    "CaseOrigin",
    "CaseResult",
    "CaseSplit",
    "Evaluator",
    "IterationRecord",
    "LoadedConfig",
    "ProcessResult",
    "Proposer",
    "ProposerContext",
    "ProposerError",
    "ProposerRequest",
    "RegressionLog",
    "Scorecard",
    "VerificationCase",
    "cli_proposer",
    "command_evaluator",
    "decide",
    "invoke_cli_proposer",
    "load_acceptance_config",
    "load_casebook",
    "mark_in_place",
    "read_candidate",
    "read_casebook",
    "run_acceptance_loop",
    "run_process",
    "score_results",
]
