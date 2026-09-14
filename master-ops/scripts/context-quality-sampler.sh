#!/usr/bin/env bash
# PRINTS ONLY: this script never writes a ledger or any file. Output goes to stdout.
# (Contrast: context-quality-log.sh is the ledger writer; compaction-probe.sh only instructs.)
#
# Print non-blocking source-of-truth samples for E12 recall comparison.
#
# Anchors, all overridable so the script carries no seat-specific assumption:
#   CONTEXT_QUALITY_ANCHOR  git/bd 를 읽을 디렉터리 (기본: 이 스크립트의 부모)
#   CONTEXT_QUALITY_LABEL   출력 헤더에 쓸 이름   (기본: 앵커 디렉터리의 basename)
set +e

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd -P)"
ADMIN_PLANNING_DIR="${CONTEXT_QUALITY_ANCHOR:-$(CDPATH= cd -- "$SCRIPT_DIR/.." 2>/dev/null && pwd -P)}"
REPO_ROOT="$(CDPATH= cd -- "$ADMIN_PLANNING_DIR/.." 2>/dev/null && pwd -P)"

if [ -z "$ADMIN_PLANNING_DIR" ]; then
  ADMIN_PLANNING_DIR="$(pwd)"
fi
ANCHOR_LABEL="${CONTEXT_QUALITY_LABEL:-$(basename "$ADMIN_PLANNING_DIR")}"
if [ -z "$REPO_ROOT" ]; then
  REPO_ROOT="$ADMIN_PLANNING_DIR"
fi

if ! command -v python3 >/dev/null 2>&1; then
  printf '# Context Quality Sampler\n'
  printf 'generated_at: unavailable\n\n'
  printf '## bd active tracks (in_progress)\nunavailable\n\n'
  printf '## bd ready (backlog, 참고용)\nunavailable\n\n'
  printf '## bd closed in last 24h\nunavailable\n\n'
  printf '## %s git log --oneline -5\nunavailable\n' "$ANCHOR_LABEL"
  exit 0
fi

ADMIN_PLANNING_DIR="$ADMIN_PLANNING_DIR" REPO_ROOT="$REPO_ROOT" ANCHOR_LABEL="$ANCHOR_LABEL" python3 <<'PY'
import datetime as dt
import json
import os
import shutil
import subprocess

admin_dir = os.environ.get("ADMIN_PLANNING_DIR") or os.getcwd()
repo_root = os.environ.get("REPO_ROOT") or admin_dir
anchor_label = os.environ.get("ANCHOR_LABEL") or os.path.basename(admin_dir)
bd_available = shutil.which("bd") is not None
now = dt.datetime.now(dt.timezone.utc)


def run(command, cwd):
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except Exception:
        return None


def parse_json_list(raw):
    data = json.loads(raw)
    if isinstance(data, list):
        return data
    return []


def priority_text(item):
    priority = item.get("priority")
    if priority is None:
        return "P?"
    return f"P{priority}"


def print_issue_lines(items, limit=10):
    for item in items[:limit]:
        issue_id = item.get("id", "?")
        title = str(item.get("title", "")).replace("\n", " ")
        print(f"- {issue_id} {priority_text(item)} {title}")
    if len(items) > limit:
        print(f"- ... {len(items) - limit} more")


def parse_time(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


print("# Context Quality Sampler")
print(f"generated_at: {now.isoformat()}")
if not bd_available:
    print("notice: bd unavailable; beads sections skipped")
print()

print("## bd active tracks (in_progress)")
if not bd_available:
    print("unavailable")
else:
    result = run(["bd", "list", "--status=in_progress", "--json"], repo_root)
    if result is None or result.returncode != 0:
        print("unavailable")
    else:
        try:
            active = parse_json_list(result.stdout)
        except Exception:
            print("unavailable")
        else:
            print(f"count: {len(active)}")
            print_issue_lines(active)
print()

print("## bd ready (backlog, 참고용)")
if not bd_available:
    print("unavailable")
else:
    result = run(["bd", "ready", "--json"], repo_root)
    if result is None or result.returncode != 0:
        print("unavailable")
    else:
        try:
            ready = parse_json_list(result.stdout)
        except Exception:
            print("unavailable")
        else:
            print(f"count: {len(ready)}")
            print_issue_lines(ready)
print()

print("## bd closed in last 24h")
if not bd_available:
    print("unavailable")
else:
    result = run(["bd", "list", "--status=closed", "--json"], repo_root)
    if result is None or result.returncode != 0:
        print("unavailable")
    else:
        try:
            closed = parse_json_list(result.stdout)
            cutoff = now - dt.timedelta(hours=24)
            recent = []
            for item in closed:
                closed_at = parse_time(item.get("closed_at"))
                if closed_at is not None and closed_at >= cutoff:
                    recent.append(item)
            recent.sort(key=lambda item: item.get("closed_at") or "", reverse=True)
        except Exception:
            print("unavailable")
        else:
            print(f"count: {len(recent)}")
            print_issue_lines(recent)
print()

print(f"## {anchor_label} git log --oneline -5")
if shutil.which("git") is None:
    print("unavailable")
else:
    result = run(["git", "-C", admin_dir, "log", "--oneline", "-5"], admin_dir)
    if result is None or result.returncode != 0 or not result.stdout.strip():
        print("unavailable")
    else:
        print(result.stdout.rstrip())
PY

exit 0
