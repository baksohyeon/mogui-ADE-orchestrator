#!/usr/bin/env bash
# Cases for scripts/land: (a) gate passes: pushed, remote equals local; (b)
# gate exits nonzero even when its last printed line says "pass": nothing
# pushed, checkout back at the start sha, log kept (the #318 bug: a
# truncated last-line read, or a pipe that drops the gate's own exit code,
# would pass this); (c) a single-commit cherry-pick conflict: aborted,
# nothing pushed; (c2) the same, on the second of two commits, checked for
# leftover sequencer state too; (d) a dirty checkout: refused before any
# change, and the dirty content survives; (g) a checkout on a branch other
# than main; (h) local main diverged from origin/main; (e) no arguments;
# (f) a commit that does not resolve. (e) and (f) are could-not-run
# failures, exit 2, not the exit-1 shape of the others.
#
# (i) a gate that commits an extra change, moving HEAD past the sha the
# cherry-picks produced: nothing pushed; (j) a gate that checks out a
# different, already-pushed branch: nothing pushed, and main on the remote
# is untouched; (i) and (j) are the two ways a gate can move the checkout
# that step 4 must catch before the push, not after it. (k) a gate that
# edits a tracked file without committing, then fails: the edit is not
# reset away, and the exit is 2 (could not safely recover), not 1, because
# a blind `reset --hard` would have destroyed it. (m) a gate that leaves its
# own cherry-pick conflicted, then fails: the conflict is not silently
# aborted before the dirty check ever sees it, same exit-2 shape as (k).
# (l) `--gate` made of only whitespace: exits 2 before any change, same as
# an empty one.
#
# Each fixture is a fresh bare "origin" plus a clone, built from scratch per
# case so a result in one case cannot leak into the next.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAND="${SCRIPT_DIR}/land"

if [ ! -x "${LAND}" ]; then
  echo "FAIL: ${LAND} is missing or not executable"
  exit 1
fi

F=0
ok() { echo "  ok:   $*"; }
fail() { echo "  FAIL: $*"; F=1; }

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "${WORK_DIR}"' EXIT

# Isolate git from the operator's own global config (signing, default
# branch, aliases) so the fixture behaves the same on every machine.
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_SYSTEM=/dev/null

git_id() {
  # $1 repo path
  git -C "$1" config user.email "land-test@example.invalid"
  git -C "$1" config user.name "land test"
  git -C "$1" config commit.gpgsign false
}

# Build a fresh bare origin + clone pair under "$WORK_DIR/$1", seeded with
# one commit on main. Echoes the clone path.
new_fixture() {
  local name="$1" bare clone
  bare="${WORK_DIR}/${name}-origin.git"
  clone="${WORK_DIR}/${name}-clone"
  git init --quiet --bare --initial-branch=main "${bare}"
  git clone --quiet "${bare}" "${clone}" 2>/dev/null
  # An older git's clone default branch can still be "master" regardless of
  # the bare repo's own default; land assumes "main", so the fixture pins it.
  git -C "${clone}" symbolic-ref HEAD refs/heads/main
  git_id "${clone}"
  echo "base" >"${clone}/file.txt"
  git -C "${clone}" add file.txt
  git -C "${clone}" commit --quiet -m "base"
  git -C "${clone}" push --quiet origin main
  echo "${clone}"
}

# A detached worktree used as the "worker" side: branches off the clone's
# current main, commits go here, and land's job is to carry them from here
# onto the clone's main and push.
make_commit() {
  # $1 clone (acts as the worker checkout too, on a side branch) $2 file $3 content $4 message
  local clone="$1" file="$2" content="$3" msg="$4"
  echo "${content}" >"${clone}/${file}"
  git -C "${clone}" add "${file}"
  git -C "${clone}" commit --quiet -m "${msg}"
  git -C "${clone}" rev-parse HEAD
}

remote_sha() {
  # $1 bare origin path -> sha of refs/heads/main there
  git -C "$1" rev-parse refs/heads/main
}

gate_stub() {
  # $1 destination path $2 exit code $3 last line
  cat >"$1" <<EOF
#!/usr/bin/env bash
echo "${3}"
exit ${2}
EOF
  chmod +x "$1"
}

# --- Case (a): gate exits 0 -------------------------------------------------
clone_a="$(new_fixture a)"
bare_a="${WORK_DIR}/a-origin.git"
start_a="$(git -C "${clone_a}" rev-parse HEAD)"
git -C "${clone_a}" checkout --quiet -b work
sha_a="$(make_commit "${clone_a}" change-a.txt one "commit a")"
git -C "${clone_a}" checkout --quiet main
gate_stub "${WORK_DIR}/gate-pass.sh" 0 "pass"

out=$(cd "${clone_a}" && "${LAND}" --repo "${clone_a}" --gate "${WORK_DIR}/gate-pass.sh" "${sha_a}" 2>&1)
rc=$?
head_a="$(git -C "${clone_a}" rev-parse HEAD)"
remote_a="$(remote_sha "${bare_a}")"
content_a="$(cat "${clone_a}/change-a.txt" 2>/dev/null || true)"
# cherry-pick always writes a new commit object (a fresh committer date),
# so the landed sha differs from the work-branch sha even with no
# conflict; what must match is the content and that local equals remote.
if [ "${rc}" -eq 0 ] && [ "${head_a}" = "${remote_a}" ] && [ "${content_a}" = "one" ] && git -C "${clone_a}" merge-base --is-ancestor "${start_a}" HEAD; then
  ok "gate passes: pushed, remote equals local"
else
  fail "gate passes: rc=${rc} head=${head_a} remote=${remote_a} content=${content_a}"
  echo "       output: ${out}"
fi

# --- Case (b): gate exits nonzero while its last line says "pass" ----------
clone_b="$(new_fixture b)"
bare_b="${WORK_DIR}/b-origin.git"
start_b="$(git -C "${clone_b}" rev-parse HEAD)"
git -C "${clone_b}" checkout --quiet -b work
sha_b="$(make_commit "${clone_b}" change-b.txt one "commit b")"
git -C "${clone_b}" checkout --quiet main
gate_stub "${WORK_DIR}/gate-lying.sh" 1 "pass"

out=$(cd "${clone_b}" && "${LAND}" --repo "${clone_b}" --gate "${WORK_DIR}/gate-lying.sh" "${sha_b}" 2>&1)
rc=$?
head_b="$(git -C "${clone_b}" rev-parse HEAD)"
remote_b="$(remote_sha "${bare_b}")"
log_path_b="$(printf '%s\n' "${out}" | grep -o '/[^ ]*land-gate[^ ,;]*' | head -1)"
if [ "${rc}" -eq 1 ] && [ "${head_b}" = "${start_b}" ] && [ "${remote_b}" = "${start_b}" ] \
  && [ -n "${log_path_b}" ] && [ -f "${log_path_b}" ] && grep -q "pass" "${log_path_b}"; then
  ok "gate's exit code is trusted over its last printed line: nothing pushed, checkout reset, log kept"
else
  fail "gate's exit code was not trusted: rc=${rc} head=${head_b} remote=${remote_b} want=${start_b} log=${log_path_b}"
  echo "       output: ${out}"
fi

# --- Case (c): cherry-pick conflict -----------------------------------------
clone_c="$(new_fixture c)"
bare_c="${WORK_DIR}/c-origin.git"
start_c="$(git -C "${clone_c}" rev-parse HEAD)"
# Conflicting edit on main after the branch point, so the worker's commit on
# the same line cannot cherry-pick cleanly.
echo "main-side-edit" >"${clone_c}/file.txt"
git -C "${clone_c}" add file.txt
git -C "${clone_c}" commit --quiet -m "main edits file.txt"
git -C "${clone_c}" push --quiet origin main
start_c="$(git -C "${clone_c}" rev-parse HEAD)"
git -C "${clone_c}" checkout --quiet -b work "${start_c}^"
sha_c="$(make_commit "${clone_c}" file.txt worker-side-edit "commit c, conflicts with main")"
git -C "${clone_c}" checkout --quiet main

out=$(cd "${clone_c}" && "${LAND}" --repo "${clone_c}" --gate "${WORK_DIR}/gate-pass.sh" "${sha_c}" 2>&1)
rc=$?
head_c="$(git -C "${clone_c}" rev-parse HEAD)"
remote_c="$(remote_sha "${bare_c}")"
cherry_in_progress=0
# A single-commit cherry-pick conflict leaves CHERRY_PICK_HEAD, not the
# multi-pick sequencer state, so that is what an unaborted conflict leaves
# behind here.
git -C "${clone_c}" rev-parse --quiet --verify CHERRY_PICK_HEAD >/dev/null 2>&1 && cherry_in_progress=1
porcelain_c="$(git -C "${clone_c}" status --porcelain)"
if [ "${rc}" -eq 1 ] && [ "${head_c}" = "${start_c}" ] && [ "${remote_c}" = "${start_c}" ] \
  && [ "${cherry_in_progress}" -eq 0 ] && [ -z "${porcelain_c}" ]; then
  ok "cherry-pick conflict: aborted cleanly, nothing pushed"
else
  fail "cherry-pick conflict not handled: rc=${rc} head=${head_c} remote=${remote_c} want=${start_c} sequencer=${cherry_in_progress} porcelain=[${porcelain_c}]"
  echo "       output: ${out}"
fi

# --- Case (c2): a multi-commit cherry-pick, conflicting on the second ------
# A multi-commit pick leaves real sequencer state (not just CHERRY_PICK_HEAD)
# if the abort does not clean it up; this is the case that state is checked.
clone_c2="$(new_fixture c2)"
bare_c2="${WORK_DIR}/c2-origin.git"
echo "main-side-edit-2" >"${clone_c2}/file.txt"
git -C "${clone_c2}" add file.txt
git -C "${clone_c2}" commit --quiet -m "main edits file.txt"
git -C "${clone_c2}" push --quiet origin main
start_c2="$(git -C "${clone_c2}" rev-parse HEAD)"
git -C "${clone_c2}" checkout --quiet -b work "${start_c2}^"
sha_c2_1="$(make_commit "${clone_c2}" ok.txt fine "commit c2-1, no conflict")"
sha_c2_2="$(make_commit "${clone_c2}" file.txt worker-side-edit-2 "commit c2-2, conflicts with main")"
git -C "${clone_c2}" checkout --quiet main

out=$(cd "${clone_c2}" && "${LAND}" --repo "${clone_c2}" --gate "${WORK_DIR}/gate-pass.sh" "${sha_c2_1}" "${sha_c2_2}" 2>&1)
rc=$?
head_c2="$(git -C "${clone_c2}" rev-parse HEAD)"
remote_c2="$(remote_sha "${bare_c2}")"
sequencer_in_progress=0
[ -d "${clone_c2}/.git/sequencer" ] && sequencer_in_progress=1
git -C "${clone_c2}" rev-parse --quiet --verify CHERRY_PICK_HEAD >/dev/null 2>&1 && sequencer_in_progress=1
porcelain_c2="$(git -C "${clone_c2}" status --porcelain)"
if [ "${rc}" -eq 1 ] && [ "${head_c2}" = "${start_c2}" ] && [ "${remote_c2}" = "${start_c2}" ] \
  && [ "${sequencer_in_progress}" -eq 0 ] && [ -z "${porcelain_c2}" ]; then
  ok "multi-commit cherry-pick conflict on the second commit: aborted cleanly, no sequencer state, nothing pushed"
else
  fail "multi-commit cherry-pick conflict not handled: rc=${rc} head=${head_c2} remote=${remote_c2} want=${start_c2} sequencer=${sequencer_in_progress} porcelain=[${porcelain_c2}]"
  echo "       output: ${out}"
fi

# --- Case (d): dirty checkout ------------------------------------------------
clone_d="$(new_fixture d)"
bare_d="${WORK_DIR}/d-origin.git"
start_d="$(git -C "${clone_d}" rev-parse HEAD)"
git -C "${clone_d}" checkout --quiet -b work
sha_d="$(make_commit "${clone_d}" change-d.txt one "commit d")"
git -C "${clone_d}" checkout --quiet main
echo "uncommitted" >"${clone_d}/dirty.txt"

out=$(cd "${clone_d}" && "${LAND}" --repo "${clone_d}" --gate "${WORK_DIR}/gate-pass.sh" "${sha_d}" 2>&1)
rc=$?
head_d="$(git -C "${clone_d}" rev-parse HEAD)"
remote_d="$(remote_sha "${bare_d}")"
if [ "${rc}" -eq 1 ] && [ "${head_d}" = "${start_d}" ] && [ "${remote_d}" = "${start_d}" ] && [ -f "${clone_d}/dirty.txt" ] && [ "$(cat "${clone_d}/dirty.txt")" = "uncommitted" ]; then
  ok "dirty checkout: refused before any change, dirty file survives"
else
  fail "dirty checkout not refused cleanly: rc=${rc} head=${head_d} remote=${remote_d}"
  echo "       output: ${out}"
fi

# --- Case (g): checkout on a branch other than main -------------------------
clone_g="$(new_fixture g)"
bare_g="${WORK_DIR}/g-origin.git"
start_g="$(git -C "${clone_g}" rev-parse HEAD)"
git -C "${clone_g}" checkout --quiet -b not-main

out_g=$(cd "${clone_g}" && "${LAND}" --repo "${clone_g}" --gate "${WORK_DIR}/gate-pass.sh" "${start_g}" 2>&1)
rc_g=$?
head_g="$(git -C "${clone_g}" rev-parse HEAD)"
remote_g="$(remote_sha "${bare_g}")"
if [ "${rc_g}" -eq 1 ] && [ "${head_g}" = "${start_g}" ] && [ "${remote_g}" = "${start_g}" ]; then
  ok "checkout on a branch other than main: refused, nothing pushed"
else
  fail "wrong-branch checkout not refused cleanly: rc=${rc_g} head=${head_g} remote=${remote_g}"
  echo "       output: ${out_g}"
fi

# --- Case (h): local main diverged from origin/main -------------------------
clone_h="$(new_fixture h)"
bare_h="${WORK_DIR}/h-origin.git"
echo "local-only" >"${clone_h}/local-only.txt"
git -C "${clone_h}" add local-only.txt
git -C "${clone_h}" commit --quiet -m "local commit, never pushed"
start_h="$(git -C "${clone_h}" rev-parse HEAD)"
remote_before_h="$(remote_sha "${bare_h}")"

out_h=$(cd "${clone_h}" && "${LAND}" --repo "${clone_h}" --gate "${WORK_DIR}/gate-pass.sh" "${start_h}" 2>&1)
rc_h=$?
head_h="$(git -C "${clone_h}" rev-parse HEAD)"
remote_h="$(remote_sha "${bare_h}")"
if [ "${rc_h}" -eq 1 ] && [ "${head_h}" = "${start_h}" ] && [ "${remote_h}" = "${remote_before_h}" ]; then
  ok "local main diverged from origin/main: refused, nothing pushed"
else
  fail "diverged main not refused cleanly: rc=${rc_h} head=${head_h} remote=${remote_h} want_remote=${remote_before_h}"
  echo "       output: ${out_h}"
fi

# --- Case (i): gate commits an extra change, moving HEAD past picked -------
clone_i="$(new_fixture i)"
bare_i="${WORK_DIR}/i-origin.git"
start_i="$(git -C "${clone_i}" rev-parse HEAD)"
git -C "${clone_i}" checkout --quiet -b work
sha_i="$(make_commit "${clone_i}" change-i.txt one "commit i")"
git -C "${clone_i}" checkout --quiet main
cat >"${WORK_DIR}/gate-sneaky-commit.sh" <<'EOF'
#!/usr/bin/env bash
git commit --allow-empty -q -m sneaky
exit 0
EOF
chmod +x "${WORK_DIR}/gate-sneaky-commit.sh"

out_i=$(cd "${clone_i}" && "${LAND}" --repo "${clone_i}" --gate "${WORK_DIR}/gate-sneaky-commit.sh" "${sha_i}" 2>&1)
rc_i=$?
head_i="$(git -C "${clone_i}" rev-parse HEAD)"
remote_i="$(remote_sha "${bare_i}")"
if [ "${rc_i}" -eq 1 ] && [ "${head_i}" = "${start_i}" ] && [ "${remote_i}" = "${start_i}" ]; then
  ok "gate commits an extra change after the cherry-pick: nothing pushed, checkout reset"
else
  fail "gate's extra commit was not caught: rc=${rc_i} head=${head_i} remote=${remote_i} want=${start_i}"
  echo "       output: ${out_i}"
fi

# --- Case (j): gate checks out a different, already-pushed branch ----------
clone_j="$(new_fixture j)"
bare_j="${WORK_DIR}/j-origin.git"
start_j="$(git -C "${clone_j}" rev-parse HEAD)"
git -C "${clone_j}" checkout --quiet -b work
sha_j="$(make_commit "${clone_j}" change-j.txt one "commit j")"
git -C "${clone_j}" checkout --quiet main
git -C "${clone_j}" checkout --quiet -b other "${start_j}"
other_sha_j="$(make_commit "${clone_j}" other.txt other "other branch commit")"
git -C "${clone_j}" push --quiet origin other
git -C "${clone_j}" checkout --quiet main
cat >"${WORK_DIR}/gate-checkout-other.sh" <<EOF
#!/usr/bin/env bash
git -C "${clone_j}" checkout --quiet other
exit 0
EOF
chmod +x "${WORK_DIR}/gate-checkout-other.sh"

out_j=$(cd "${clone_j}" && "${LAND}" --repo "${clone_j}" --gate "${WORK_DIR}/gate-checkout-other.sh" "${sha_j}" 2>&1)
rc_j=$?
remote_main_j="$(remote_sha "${bare_j}")"
head_j="$(git -C "${clone_j}" rev-parse HEAD)"
branch_j="$(git -C "${clone_j}" branch --show-current)"
if [ "${rc_j}" -eq 1 ] && [ "${remote_main_j}" = "${start_j}" ] \
  && [ "${head_j}" = "${start_j}" ] && [ "${branch_j}" = "main" ]; then
  ok "gate checks out a different branch: nothing pushed, main on the remote untouched, local checkout back on main at the start sha"
else
  fail "gate's branch switch was not caught: rc=${rc_j} remote_main=${remote_main_j} head=${head_j} branch=${branch_j} want=${start_j} other_sha=${other_sha_j}"
  echo "       output: ${out_j}"
fi

# --- Case (k): gate edits a tracked file without committing, then fails ----
clone_k="$(new_fixture k)"
bare_k="${WORK_DIR}/k-origin.git"
start_k="$(git -C "${clone_k}" rev-parse HEAD)"
git -C "${clone_k}" checkout --quiet -b work
sha_k="$(make_commit "${clone_k}" change-k.txt one "commit k")"
git -C "${clone_k}" checkout --quiet main
cat >"${WORK_DIR}/gate-dirty-edit.sh" <<'EOF'
#!/usr/bin/env bash
echo "edited-by-gate" > file.txt
exit 1
EOF
chmod +x "${WORK_DIR}/gate-dirty-edit.sh"

out_k=$(cd "${clone_k}" && "${LAND}" --repo "${clone_k}" --gate "${WORK_DIR}/gate-dirty-edit.sh" "${sha_k}" 2>&1)
rc_k=$?
content_k="$(cat "${clone_k}/file.txt" 2>/dev/null)"
remote_k="$(remote_sha "${bare_k}")"
if [ "${rc_k}" -eq 2 ] && [ "${content_k}" = "edited-by-gate" ] && [ "${remote_k}" = "${start_k}" ] \
  && printf '%s' "${out_k}" | grep -q "${start_k}" && printf '%s' "${out_k}" | grep -q "NOT reset"; then
  ok "gate leaves an uncommitted tracked-file edit then fails: exit 2, edit survives, nothing pushed"
else
  fail "gate's uncommitted edit was not protected: rc=${rc_k} content=[${content_k}] remote=${remote_k} want_remote=${start_k}"
  echo "       output: ${out_k}"
fi

# --- Case (m): gate leaves its own cherry-pick conflicted, then fails ------
# Exercises the order inside reset_to_start itself: the dirty check must
# run before any `cherry-pick --abort`, or a conflict the gate leaves
# behind is discarded before land ever notices it was there.
clone_m="$(new_fixture m2)"
bare_m="${WORK_DIR}/m2-origin.git"
start_m="$(git -C "${clone_m}" rev-parse HEAD)"
git -C "${clone_m}" checkout --quiet -b work
sha_m="$(make_commit "${clone_m}" file.txt worker-edit "commit m2, edits file.txt")"
git -C "${clone_m}" checkout --quiet main
# A commit, off the same base, that edits file.txt differently -- cherry-
# picking it onto the worker's edit above is what the gate leaves conflicted.
git -C "${clone_m}" checkout --quiet -b conflict-source "${start_m}"
conflict_sha_m="$(make_commit "${clone_m}" file.txt conflict-source-edit "conflicting edit")"
git -C "${clone_m}" checkout --quiet main
cat >"${WORK_DIR}/gate-leave-conflict.sh" <<EOF
#!/usr/bin/env bash
git -C "${clone_m}" cherry-pick "${conflict_sha_m}" >/dev/null 2>&1
exit 1
EOF
chmod +x "${WORK_DIR}/gate-leave-conflict.sh"

out_m=$(cd "${clone_m}" && "${LAND}" --repo "${clone_m}" --gate "${WORK_DIR}/gate-leave-conflict.sh" "${sha_m}" 2>&1)
rc_m=$?
cherry_in_progress_m=0
git -C "${clone_m}" rev-parse --quiet --verify CHERRY_PICK_HEAD >/dev/null 2>&1 && cherry_in_progress_m=1
remote_m="$(remote_sha "${bare_m}")"
if [ "${rc_m}" -eq 2 ] && [ "${cherry_in_progress_m}" -eq 1 ] && [ "${remote_m}" = "${start_m}" ] \
  && printf '%s' "${out_m}" | grep -q "NOT reset"; then
  ok "gate leaves its own cherry-pick conflicted then fails: not silently aborted, exit 2, nothing pushed"
else
  fail "gate's own conflict was not protected: rc=${rc_m} cherry_in_progress=${cherry_in_progress_m} remote=${remote_m} want_remote=${start_m}"
  echo "       output: ${out_m}"
fi

# --- Case (l): --gate made of only whitespace exits 2 ----------------------
clone_l="$(new_fixture l)"
bare_l="${WORK_DIR}/l-origin.git"
start_l="$(git -C "${clone_l}" rev-parse HEAD)"
git -C "${clone_l}" checkout --quiet -b work
sha_l="$(make_commit "${clone_l}" change-l.txt one "commit l")"
git -C "${clone_l}" checkout --quiet main

out_l=$(cd "${clone_l}" && "${LAND}" --repo "${clone_l}" --gate "   " "${sha_l}" 2>&1)
rc_l=$?
head_l="$(git -C "${clone_l}" rev-parse HEAD)"
remote_l="$(remote_sha "${bare_l}")"
if [ "${rc_l}" -eq 2 ] && [ "${head_l}" = "${start_l}" ] && [ "${remote_l}" = "${start_l}" ]; then
  ok "a whitespace-only --gate is rejected like an empty one: exits 2, nothing pushed"
else
  fail "whitespace-only --gate was accepted: rc=${rc_l} head=${head_l} remote=${remote_l} want=${start_l}"
  echo "       output: ${out_l}"
fi

# --- Case (e): usage error (no arguments) exits 2 --------------------------
out_e=$("${LAND}" 2>&1)
rc_e=$?
if [ "${rc_e}" -eq 2 ]; then
  ok "usage error (no arguments) exits 2"
else
  fail "usage error exited ${rc_e}, want 2"
  echo "       output: ${out_e}"
fi

# --- Case (f): a commit argument that does not resolve exits 2 -------------
clone_f="$(new_fixture f)"
out_f=$(cd "${clone_f}" && "${LAND}" --repo "${clone_f}" --gate "${WORK_DIR}/gate-pass.sh" "deadbeef0000000000000000000000000000dead" 2>&1)
rc_f=$?
if [ "${rc_f}" -eq 2 ]; then
  ok "a commit that does not resolve exits 2, before any change is made"
else
  fail "unresolved commit exited ${rc_f}, want 2"
  echo "       output: ${out_f}"
fi

# --- Failability: ignoring the gate's exit code must make case (b) fail ----
MUT="${WORK_DIR}/land.mutant"
sed 's/gate_rc=\$?/gate_rc=0/' "${LAND}" >"${MUT}"
if [ "$(cat "${MUT}")" = "$(cat "${LAND}")" ]; then
  fail "failability: mutant text 'gate_rc=\$?' not found in ${LAND}"
else
  chmod +x "${MUT}"
  clone_m="$(new_fixture m)"
  bare_m="${WORK_DIR}/m-origin.git"
  start_m="$(git -C "${clone_m}" rev-parse HEAD)"
  git -C "${clone_m}" checkout --quiet -b work
  sha_m="$(make_commit "${clone_m}" change-m.txt one "commit m")"
  git -C "${clone_m}" checkout --quiet main
  out_m=$(cd "${clone_m}" && "${MUT}" --repo "${clone_m}" --gate "${WORK_DIR}/gate-lying.sh" "${sha_m}" 2>&1)
  rc_m=$?
  remote_m="$(remote_sha "${bare_m}")"
  if [ "${rc_m}" -eq 0 ] && [ "${remote_m}" != "${start_m}" ]; then
    ok "failability: a mutant that ignores the gate's exit code pushes on case (b), proving the real script's check matters"
  else
    fail "failability: mutant did not push on case (b) (rc=${rc_m} remote=${remote_m}); the real check may not be what guards this"
  fi
fi

echo "----"
[ "${F}" -eq 0 ] && echo "pass" || echo "fail"
exit "${F}"
