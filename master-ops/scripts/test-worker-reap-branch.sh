#!/usr/bin/env bash
# The branch cleanup proof uses a real temporary git repository and a stubbed
# gh command. The rendered template has no orchestrator source tree, so it
# reports a skip there while the authoring checkout runs the full proof.
set -u

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MODULE="$ROOT/src/master_runtime/core/worker_reap.py"
if [ ! -f "$MODULE" ]; then
  echo "SKIP: worker-reap source is not present in this rendered template"
  exit 0
fi

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT

cat >"$T/gh" <<'EOF'
#!/usr/bin/env bash
case "${GH_STUB_CASE:-}" in
  merged) printf '{"state":"MERGED","headRefOid":"%s"}\n' "$GH_STUB_HEAD" ;;
  open) printf '{"state":"OPEN","headRefOid":"%s"}\n' "$GH_STUB_HEAD" ;;
  no-pr) echo "no pull request found" >&2; exit 1 ;;
  unavailable) echo "gh unavailable" >&2; exit 1 ;;
  *) echo "unknown gh fixture" >&2; exit 1 ;;
esac
EOF
chmod +x "$T/gh"

cat >"$T/branch_probe.py" <<'PY'
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("worker_reap_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def setup_repo(root: Path) -> tuple[Path, str, str]:
    repo = root / "repo"
    repo.mkdir()
    run_git(repo, "init", "--initial-branch", "main")
    run_git(repo, "config", "user.email", "worker-reap@example.invalid")
    run_git(repo, "config", "user.name", "worker-reap test")
    (repo / "README").write_text("base\n", encoding="utf-8")
    run_git(repo, "add", "README")
    run_git(repo, "commit", "-m", "base")
    run_git(repo, "branch", "feature/test")
    tip = run_git(repo, "rev-parse", "refs/heads/feature/test").strip()
    return repo, tip, str((repo / ".git").resolve())


def run_case(module, gh_dir: Path, case: str, label: str, expected: str, *, pr_tip: str | None = None) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo, tip, common_dir = setup_repo(Path(tmp))
        # The helper receives the actual shared git directory so a successful
        # branch deletion exercises the same command used by the reaper.
        old_path = os.environ.get("PATH", "")
        old_case = os.environ.get("GH_STUB_CASE")
        old_head = os.environ.get("GH_STUB_HEAD")
        os.environ["PATH"] = f"{gh_dir}{os.pathsep}{old_path}"
        os.environ["GH_STUB_CASE"] = case
        os.environ["GH_STUB_HEAD"] = pr_tip or tip
        try:
            action = module.WorkerReaper()._plan_branch_deletion(
                "feature/test",
                tip,
                common_dir,
                "example/worker-reap",
                execute=True,
                reason="",
            )
        finally:
            os.environ["PATH"] = old_path
            for key, value in (("GH_STUB_CASE", old_case), ("GH_STUB_HEAD", old_head)):
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        if expected not in action:
            raise AssertionError(f"{label}: expected {expected!r}, got {action!r}")
        branch = run_git(repo, "branch", "--list", "feature/test")
        if case == "merged" and pr_tip is None:
            assert branch == "", (label, branch)
        else:
            assert branch != "", (label, branch)
        print(f"  ok:   {label}")


def main(module_path: Path, gh_dir: Path) -> int:
    module = load_module(module_path)
    run_case(module, gh_dir, "merged", "merged + equal tip deletes", "branch_deleted")
    run_case(
        module,
        gh_dir,
        "merged",
        "merged + different tip keeps",
        "tip differs",
        pr_tip="0" * 40,
    )
    run_case(module, gh_dir, "open", "open PR keeps", "not merged")
    run_case(module, gh_dir, "no-pr", "no PR keeps", "no PR")
    run_case(module, gh_dir, "unavailable", "gh unavailable keeps", "gh unavailable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
PY

if ! PYTHONPATH="$ROOT/src" python3 "$T/branch_probe.py" "$MODULE" "$T"; then
  echo "  FAIL: branch cleanup probe failed"
  exit 1
fi

# Mutant proof: remove the tip-equality check and the different-tip case must
# fail. The probe exits nonzero when the mutant deletes that branch.
if ! python3 - "$MODULE" "$T/worker_reap_mutant.py" <<'PY'
import sys

source = open(sys.argv[1], encoding="utf-8").read()
mutant = source.replace(
    "if branch_tip != merged_head_oid:",
    "if False:",
    1,
)
if mutant == source:
    raise SystemExit("mutant text not found")
open(sys.argv[2], "w", encoding="utf-8").write(mutant)
PY
then
  echo "  FAIL: could not generate failability mutant"
  exit 1
fi
if [ ! -s "$T/worker_reap_mutant.py" ]; then
  echo "  FAIL: failability mutant file was not created"
  exit 1
fi

if PYTHONPATH="$ROOT/src" python3 "$T/branch_probe.py" "$T/worker_reap_mutant.py" "$T" >"$T/mutant-probe.log" 2>&1; then
  echo "  FAIL: failability mutant deleted the different-tip branch"
  exit 1
fi
if ! grep -q "merged + different tip keeps" "$T/mutant-probe.log" \
  || ! grep -q "expected 'tip differs'" "$T/mutant-probe.log" \
  || ! grep -q "got 'branch_deleted" "$T/mutant-probe.log"; then
  echo "  FAIL: failability mutant did not fail for the different-tip case"
  cat "$T/mutant-probe.log"
  exit 1
fi
echo "  ok:   failability mutant cannot delete a different-tip branch"

echo "worker-reap branch cleanup: all checks passed"
