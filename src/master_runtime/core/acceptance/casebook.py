"""Verification case book with a visible/private split and regression accumulation."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union


class CaseSplit(str, Enum):
    """Evaluation splits ordered by who is allowed to see them."""

    TRAIN = "train"
    HOLDOUT = "holdout"
    SCORECARD = "scorecard"


class CaseOrigin(str, Enum):
    """Where a verification case entered the book from."""

    SEED = "seed"
    REGRESSION = "regression"


VISIBLE_SPLITS = frozenset({CaseSplit.TRAIN})
PRIVATE_SPLITS = frozenset({CaseSplit.HOLDOUT, CaseSplit.SCORECARD})
GATED_SPLITS = (CaseSplit.TRAIN, CaseSplit.HOLDOUT)
SPLIT_ALIASES = {
    "visible": CaseSplit.TRAIN.value,
    "private": CaseSplit.HOLDOUT.value,
    "acceptance": CaseSplit.SCORECARD.value,
    "final_eval": CaseSplit.SCORECARD.value,
}
REGRESSION_READMIT_SPLIT = CaseSplit.HOLDOUT


class CaseBookError(ValueError):
    """Raised when a case book is structurally invalid."""


def normalize_split(value: Union[CaseSplit, str]) -> CaseSplit:
    """Normalize one split name and apply the documented aliases."""

    if isinstance(value, CaseSplit):
        return value
    text = str(value).strip().lower()
    text = SPLIT_ALIASES.get(text, text)
    try:
        return CaseSplit(text)
    except ValueError as exc:
        raise CaseBookError("unknown split: {0}".format(value)) from exc


@dataclass(frozen=True)
class VerificationCase:
    """One deterministic verification case owned by the master."""

    case_id: str
    split: CaseSplit
    stratum: str
    command: Tuple[str, ...] = ()
    origin: CaseOrigin = CaseOrigin.SEED

    @property
    def is_visible(self) -> bool:
        """Return whether a candidate proposer may see this case."""

        return self.split in VISIBLE_SPLITS

    def to_dict(self) -> Dict[str, object]:
        """Serialize the case."""

        return {
            "case_id": self.case_id,
            "split": self.split.value,
            "stratum": self.stratum,
            "command": list(self.command),
            "origin": self.origin.value,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "VerificationCase":
        """Build one case from a mapping, failing closed on bad input."""

        case_id = _string_or_none(payload.get("case_id"))
        if not case_id:
            raise CaseBookError("case_id is required")
        stratum = _string_or_none(payload.get("stratum"))
        if not stratum:
            raise CaseBookError("case {0}: stratum is required".format(case_id))
        split_value = payload.get("split")
        if split_value is None:
            raise CaseBookError("case {0}: split is required".format(case_id))
        origin_value = _string_or_none(payload.get("origin")) or CaseOrigin.SEED.value
        try:
            origin = CaseOrigin(origin_value)
        except ValueError as exc:
            raise CaseBookError(
                "case {0}: unknown origin {1}".format(case_id, origin_value)
            ) from exc
        return cls(
            case_id=case_id,
            split=normalize_split(split_value),
            stratum=stratum,
            command=tuple(_string_items(payload.get("command"))),
            origin=origin,
        )


@dataclass(frozen=True)
class CaseBook:
    """Immutable, deduplicated set of verification cases."""

    cases: Tuple[VerificationCase, ...] = ()

    def cases_for_split(self, split: Union[CaseSplit, str]) -> Tuple[VerificationCase, ...]:
        """Return cases belonging to one split in book order."""

        wanted = normalize_split(split)
        return tuple(case for case in self.cases if case.split == wanted)

    def gated_cases(self) -> Tuple[VerificationCase, ...]:
        """Return the cases that participate in the acceptance comparison."""

        return tuple(case for case in self.cases if case.split in GATED_SPLITS)

    def visible_cases(self) -> Tuple[VerificationCase, ...]:
        """Return the cases a candidate proposer is allowed to see."""

        return tuple(case for case in self.cases if case.is_visible)

    def private_cases(self) -> Tuple[VerificationCase, ...]:
        """Return the cases withheld from the candidate proposer."""

        return tuple(case for case in self.cases if not case.is_visible)

    def case_ids(self) -> Tuple[str, ...]:
        """Return every case id in book order."""

        return tuple(case.case_id for case in self.cases)

    def has_split(self, split: Union[CaseSplit, str]) -> bool:
        """Return whether the book defines any case for one split."""

        return bool(self.cases_for_split(split))

    def strata_for_split(
        self,
        split: Union[CaseSplit, str],
        origin: Optional[CaseOrigin] = CaseOrigin.SEED,
    ) -> frozenset:
        """Return the stratum set for one split, optionally filtered by origin."""

        return frozenset(
            case.stratum
            for case in self.cases_for_split(split)
            if origin is None or case.origin == origin
        )

    def with_cases(self, extra: Iterable[VerificationCase]) -> "CaseBook":
        """Return a new book with `extra` appended, keeping the first id wins rule."""

        known = {case.case_id for case in self.cases}
        merged: List[VerificationCase] = list(self.cases)
        for case in extra:
            if case.case_id in known:
                continue
            known.add(case.case_id)
            merged.append(case)
        return CaseBook(cases=tuple(merged))

    def validate(self) -> None:
        """Fail closed on a book that cannot support a private-holdout comparison."""

        if not self.cases:
            raise CaseBookError("case book must define at least one case")

        seen: set = set()
        for case in self.cases:
            if case.case_id in seen:
                raise CaseBookError("duplicate case_id: {0}".format(case.case_id))
            seen.add(case.case_id)

        for split in GATED_SPLITS:
            if not self.cases_for_split(split):
                raise CaseBookError(
                    "split {0} must include at least one case".format(split.value)
                )

        train_strata = self.strata_for_split(CaseSplit.TRAIN)
        holdout_strata = self.strata_for_split(CaseSplit.HOLDOUT)
        if train_strata != holdout_strata:
            raise CaseBookError(
                "train and holdout must cover the same seed strata; "
                "got train={0} holdout={1}".format(
                    sorted(train_strata), sorted(holdout_strata)
                )
            )

    def manifest(self) -> Dict[str, List[Dict[str, object]]]:
        """Return the full master-side split manifest."""

        payload: Dict[str, List[Dict[str, object]]] = {}
        for split in CaseSplit:
            cases = self.cases_for_split(split)
            if cases:
                payload[split.value] = [case.to_dict() for case in cases]
        return payload

    def visible_manifest(self) -> Dict[str, List[Dict[str, object]]]:
        """Return the manifest a candidate proposer may read."""

        return {
            CaseSplit.TRAIN.value: [case.to_dict() for case in self.visible_cases()],
        }


def load_casebook(payload: Union[Sequence[Mapping[str, object]], Mapping[str, object]]) -> CaseBook:
    """Build one case book from a decoded JSON payload."""

    if isinstance(payload, Mapping):
        raw_cases = payload.get("cases", ())
    else:
        raw_cases = payload
    if not isinstance(raw_cases, (list, tuple)):
        raise CaseBookError("cases must be a list")
    return CaseBook(
        cases=tuple(
            VerificationCase.from_mapping(_mapping_or_fail(item)) for item in raw_cases
        )
    )


def read_casebook(path: Union[str, Path]) -> CaseBook:
    """Read one case book from a JSON file."""

    case_path = Path(path)
    try:
        payload = json.loads(case_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CaseBookError("cannot read case book: {0}".format(case_path)) from exc
    except ValueError as exc:
        raise CaseBookError("invalid case book JSON: {0}".format(case_path)) from exc
    return load_casebook(payload)


class RegressionLog:
    """Append-only JSONL store that pins every observed failure into future rounds.

    A case that has ever failed must never silently leave the evaluation set. If the
    configured book still contains the case, its original split is preserved. If it was
    dropped from the config, it is re-admitted as a private holdout case so that a
    proposer cannot benefit from having pushed it out.
    """

    def __init__(
        self,
        path: Union[str, Path],
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.path = Path(path)
        self._clock = clock or time.time

    def promote(
        self,
        failures: Iterable[VerificationCase],
        iteration: int = 0,
    ) -> Tuple[VerificationCase, ...]:
        """Record newly observed failures and return the ones that were not yet pinned."""

        known = {case.case_id for case in self.cases()}
        promoted: List[VerificationCase] = []
        entries: List[Mapping[str, object]] = []
        for case in failures:
            if case.case_id in known:
                continue
            known.add(case.case_id)
            pinned = replace(case, origin=CaseOrigin.REGRESSION)
            promoted.append(pinned)
            entry = dict(pinned.to_dict())
            entry["ts"] = float(self._clock())
            entry["iteration"] = int(iteration)
            entry["observed_split"] = case.split.value
            entries.append(entry)
        if entries:
            self._append(entries)
        return tuple(promoted)

    def cases(self) -> Tuple[VerificationCase, ...]:
        """Return every pinned regression case in append order."""

        pinned: List[VerificationCase] = []
        seen: set = set()
        for entry in self._read():
            try:
                case = VerificationCase.from_mapping(entry)
            except CaseBookError:
                continue
            if case.case_id in seen:
                continue
            seen.add(case.case_id)
            pinned.append(replace(case, origin=CaseOrigin.REGRESSION))
        return tuple(pinned)

    def apply(self, casebook: CaseBook) -> CaseBook:
        """Merge pinned regressions into one book, re-admitting dropped cases privately."""

        configured = {case.case_id for case in casebook.cases}
        readmitted = tuple(
            replace(case, split=REGRESSION_READMIT_SPLIT)
            for case in self.cases()
            if case.case_id not in configured
        )
        return casebook.with_cases(readmitted)

    def _append(self, entries: Sequence[Mapping[str, object]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as log:
            for entry in entries:
                log.write(json.dumps(entry, sort_keys=True, separators=(",", ":")))
                log.write("\n")

    def _read(self) -> Iterable[Mapping[str, object]]:
        if not self.path.exists():
            return ()

        entries: List[Mapping[str, object]] = []
        with self.path.open("r", encoding="utf-8") as log:
            for raw_line in log:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if isinstance(entry, dict):
                    entries.append(entry)
        return entries


def render_split_markdown(casebook: CaseBook) -> str:
    """Render the master-side split manifest as Markdown."""

    lines = ["# Verification Split Manifest", ""]
    for split in CaseSplit:
        cases = casebook.cases_for_split(split)
        if not cases:
            continue
        visibility = "visible" if split in VISIBLE_SPLITS else "private"
        lines.extend(["## {0} ({1})".format(split.value, visibility), ""])
        lines.extend(
            "- `{0}` [{1}] origin=`{2}`".format(case.stratum, case.case_id, case.origin.value)
            for case in cases
        )
        lines.append("")
    return "\n".join(lines)


def _mapping_or_fail(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CaseBookError("case entry must be an object")
    return value


def _string_or_none(value: object) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _string_items(value: object) -> Tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, str))
