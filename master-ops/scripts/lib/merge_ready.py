#!/usr/bin/env python3
"""Shared parsing for the merge-ready measurement.

This file is invoked directly with ``python3 -I`` by both measurement phases.
Keeping the parsers here prevents the preflight and final verdict from
silently accepting different roster, review, stop-list, or contract shapes.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DECISION_STATES = {"APPROVED", "CHANGES_REQUESTED", "DISMISSED", "PENDING"}


def load_json(path: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"{Path(path).name}: unparseable: {exc}") from exc


def strip_bot_suffix(login: Any) -> str:
    if not isinstance(login, str):
        return ""
    return login[:-5] if login.lower().endswith("[bot]") else login


def matches_stop(path: str, entry: str) -> bool:
    template_layout_prefix = "master-" "ops/"

    def without_template_prefix(value: str) -> str:
        return value[len(template_layout_prefix) :] if value.startswith(template_layout_prefix) else value

    def with_layout_aliases(value: str) -> set[str]:
        root_path = without_template_prefix(value)
        return {root_path, f"{template_layout_prefix}{root_path}"}

    def matches_one(candidate: str, stop_entry: str) -> bool:
        if stop_entry.endswith("/"):
            return candidate == stop_entry.rstrip("/") or candidate.startswith(stop_entry)
        if any(char in stop_entry for char in "*?["):
            return fnmatch.fnmatch(candidate, stop_entry)
        return candidate == stop_entry

    return any(
        matches_one(candidate, stop_candidate)
        for candidate in with_layout_aliases(path)
        for stop_candidate in with_layout_aliases(entry)
    )


def read_stop_entries(path: str) -> list[str]:
    entries = [
        line.strip()
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not entries:
        raise ValueError(f"stop-paths file has no entries: {path}")
    return entries


def changed_paths(files: Any) -> list[str]:
    if not isinstance(files, list):
        raise ValueError("changed files response is not a list")
    paths: set[str] = set()
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("filename"), str):
            raise ValueError("changed files response has a malformed item")
        paths.add(item["filename"])
        previous = item.get("previous_filename")
        if previous is not None:
            if not isinstance(previous, str) or not previous:
                raise ValueError("changed files response has a malformed previous_filename")
            paths.add(previous)
    return sorted(paths)


def contract_writes(path: str) -> list[str] | None:
    text = Path(path).read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?\n)---", text, re.DOTALL)
    front_matter = match.group(1) if match else ""
    for front_matter_line in front_matter.splitlines():
        key, separator, raw_value = front_matter_line.partition(":")
        if separator and key.strip() == "writes":
            raw_value = raw_value.strip()
            if not (raw_value.startswith("[") and raw_value.endswith("]")):
                raise ValueError("contract front matter writes is malformed")
            inner = raw_value[1:-1].strip()
            return [item.strip() for item in inner.split(",") if item.strip()] if inner else []
    return None


def path_verdict(files_path: str, stop_path: str, contract_path: str) -> tuple[int, str]:
    files = load_json(files_path)
    paths = changed_paths(files)
    stop_entries = read_stop_entries(stop_path)
    problems: list[str] = []
    stop_hits = [path for path in paths if any(matches_stop(path, entry) for entry in stop_entries)]
    if stop_hits:
        problems.append(
            f"{len(stop_hits)} stop-list path(s): "
            + ", ".join(f"{path} (stop-list)" for path in stop_hits)
        )
    if contract_path:
        globs = contract_writes(contract_path)
        if globs is None:
            message = "contract front matter has no writes: list; cannot verify scope"
            if problems:
                return 2, "merge-ready: ask · " + "; ".join(problems + [message])
            return 1, message
        outside = [path for path in paths if not any(fnmatch.fnmatch(path, glob) for glob in globs)]
        if outside:
            problems.append("path(s) outside contract writes: " + ", ".join(outside))
    if problems:
        return 2, "merge-ready: ask · " + "; ".join(problems)
    return 0, ""


def parse_bots(path: str) -> dict[str, tuple[str, str] | None]:
    forms: dict[str, tuple[str, str] | None] = {}
    for line_number, raw_line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = [field.strip() for field in line.split("|")]
        if len(fields) != 3 or not all(fields):
            raise ValueError(
                f"bots file has malformed line {line_number}; expected login | rate-limit marker | required line"
            )
        login, marker, required_line = fields
        if login in forms:
            raise ValueError(f"bots file has duplicate login: {login}")
        if (marker == "none") != (required_line == "none"):
            raise ValueError(f"bots file has incomplete rate-limit form for {login}")
        forms[login] = None if marker == "none" else (marker, required_line)
    if not forms:
        raise ValueError(f"bots file has no entries: {path}")
    return forms


def review_is_standalone(review: Any) -> bool:
    if not isinstance(review, dict):
        raise ValueError("graphql response has a malformed review node")
    body = review.get("body")
    if isinstance(body, str) and body.strip():
        return True
    comments = review.get("comments")
    if not isinstance(comments, dict) or not isinstance(comments.get("nodes"), list):
        return False
    has_top_level_comment = False
    for comment in comments["nodes"]:
        if not isinstance(comment, dict) or "replyTo" not in comment:
            raise ValueError("graphql response has malformed review comment replyTo")
        reply_to = comment["replyTo"]
        if reply_to is None:
            has_top_level_comment = True
        elif not isinstance(reply_to, dict):
            raise ValueError("graphql response has malformed review comment replyTo")
    page_info = comments.get("pageInfo")
    if not isinstance(page_info, dict) or not isinstance(page_info.get("hasNextPage"), bool):
        raise ValueError("graphql response has malformed review comments pageInfo")
    if has_top_level_comment:
        return True
    if page_info["hasNextPage"]:
        raise ValueError("graphql response has unpaged review comments without a top-level comment")
    return False


def parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("missing or empty timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid timestamp {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"timestamp has no timezone {value!r}")
    return parsed.astimezone(timezone.utc)


def rate_limit_notice(form: tuple[str, str] | None, body: Any) -> bool:
    if form is None or not isinstance(body, str):
        return False
    marker, required_line = form
    lines = body.splitlines()
    return lines.count(marker) == 1 and required_line in lines


def review_state(reviews_path: str, comments_path: str, bots_path: str, head_sha: str, head_time: str) -> dict[str, Any]:
    reviews = load_json(reviews_path)
    comments = load_json(comments_path)
    if not isinstance(reviews, list):
        raise ValueError("graphql response reviews are not a list")
    if not isinstance(comments, list):
        raise ValueError("PR comments response is not a list")
    forms = parse_bots(bots_path)
    head_reviewers: set[str] = set()
    decision_reviews: dict[str, list[tuple[str, int, str]]] = {}
    for index, review in enumerate(reviews):
        if not isinstance(review, dict):
            raise ValueError("graphql response has a malformed review node")
        author = review.get("author") or {}
        if author.get("__typename") != "Bot":
            continue
        login = strip_bot_suffix(author.get("login"))
        if (review.get("commit") or {}).get("oid") != head_sha:
            continue
        if not review_is_standalone(review):
            continue
        state = review.get("state")
        if not isinstance(state, str) or state.upper() not in DECISION_STATES | {"COMMENTED"}:
            raise ValueError("graphql response has malformed review state")
        state = state.upper()
        if login and state != "DISMISSED":
            head_reviewers.add(login)
        if state in DECISION_STATES:
            decision_reviews.setdefault(login or "unknown", []).append(
                (review.get("submittedAt") or "", index, state)
            )

    latest = {
        login: max(entries, key=lambda item: (item[0], item[1]))[2]
        for login, entries in decision_reviews.items()
    }
    candidate_bots: set[str] = set()
    recent_rate_limited: set[str] = set()
    head_time_value = parse_timestamp(head_time) if head_time else None
    for comment in comments:
        if not isinstance(comment, dict):
            raise ValueError("PR comments response has a malformed comment")
        user = comment.get("user") or {}
        login = strip_bot_suffix(user.get("login"))
        if user.get("type") != "Bot" or login not in forms:
            continue
        form = forms[login]
        if rate_limit_notice(form, comment.get("body") or "") and login not in head_reviewers:
            candidate_bots.add(login)
        if head_time_value:
            try:
                comment_time = parse_timestamp(comment.get("created_at"))
            except ValueError as exc:
                raise ValueError(f"PR comment created_at is malformed: {exc}") from exc
            if comment_time >= head_time_value and rate_limit_notice(form, comment.get("body") or ""):
                recent_rate_limited.add(login)
    return {
        "bot_logins": sorted(forms),
        "head_bot_reviewer_logins": sorted(head_reviewers),
        "candidate_bots": sorted(candidate_bots),
        "recent_rate_limited_bots": sorted(recent_rate_limited),
        "latest_bot_state": latest,
    }


def connection_page(page_path: str, aggregate_path: str, connection: str, page_number: int, page_cap: int) -> dict[str, Any]:
    if page_number > page_cap:
        raise ValueError(f"{connection} pagination exceeded cap of {page_cap} pages")
    payload = load_json(page_path)
    if isinstance(payload, dict) and payload.get("errors"):
        raise ValueError(f"graphql response contains errors for {connection}")
    pull_request = (payload.get("data") or {}).get("repository", {}).get("pullRequest")
    if not isinstance(pull_request, dict):
        raise ValueError("graphql response missing data.repository.pullRequest")
    connection_data = pull_request.get(connection)
    if not isinstance(connection_data, dict) or not isinstance(connection_data.get("nodes"), list):
        raise ValueError(f"graphql response missing {connection}.nodes")
    page_info = connection_data.get("pageInfo")
    if not isinstance(page_info, dict) or not isinstance(page_info.get("hasNextPage"), bool):
        raise ValueError(f"graphql response has malformed {connection}.pageInfo")
    has_next = page_info["hasNextPage"]
    if "endCursor" not in page_info:
        raise ValueError(f"graphql response has malformed {connection}.pageInfo.endCursor")
    end_cursor = page_info["endCursor"]
    if has_next and (not isinstance(end_cursor, str) or not end_cursor):
        raise ValueError(f"graphql response has malformed {connection}.pageInfo.endCursor")
    if end_cursor is not None and not isinstance(end_cursor, str):
        raise ValueError(f"graphql response has malformed {connection}.pageInfo.endCursor")
    aggregate = load_json(aggregate_path) if Path(aggregate_path).exists() else []
    if not isinstance(aggregate, list):
        raise ValueError(f"{connection} aggregate is not a list")
    aggregate.extend(connection_data["nodes"])
    Path(aggregate_path).write_text(json.dumps(aggregate), encoding="utf-8")
    return {"has_next": has_next, "end_cursor": end_cursor}


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="mode", required=True)
    path_parser = subparsers.add_parser("path-verdict")
    path_parser.add_argument("--files", required=True)
    path_parser.add_argument("--stop-paths", required=True)
    path_parser.add_argument("--contract", default="")
    state_parser = subparsers.add_parser("review-state")
    state_parser.add_argument("--reviews", required=True)
    state_parser.add_argument("--comments", required=True)
    state_parser.add_argument("--bots", required=True)
    state_parser.add_argument("--head", required=True)
    state_parser.add_argument("--head-time", default="")
    page_parser = subparsers.add_parser("connection-page")
    page_parser.add_argument("--page", required=True)
    page_parser.add_argument("--aggregate", required=True)
    page_parser.add_argument("--connection", required=True)
    page_parser.add_argument("--page-number", type=int, required=True)
    page_parser.add_argument("--page-cap", type=int, required=True)
    args = parser.parse_args()
    try:
        if args.mode == "path-verdict":
            code, message = path_verdict(args.files, args.stop_paths, args.contract)
            if message:
                print(message)
            return code
        if args.mode == "review-state":
            print(json.dumps(review_state(args.reviews, args.comments, args.bots, args.head, args.head_time)))
            return 0
        print(json.dumps(connection_page(args.page, args.aggregate, args.connection, args.page_number, args.page_cap)))
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
