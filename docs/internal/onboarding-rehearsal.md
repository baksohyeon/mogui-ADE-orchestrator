# Onboarding rehearsal and postconditions

`master-ops/scripts/onboarding-rehearsal` is the read-only acceptance check for a
founded workspace. It measures the artifacts that the onboarding steps promise,
prints a postcondition table, and keeps a separate gap list for facts that are
not observable from the supplied files or host.

Run it from any directory after substituting the actual workspace and ops paths.
The installed ops repository contains the script; invoke it with the platform's
Python command:

```console
$ python3 ~/workspace-ops/scripts/onboarding-rehearsal \
    --workspace-root ~/workspace \
    --ops-repo ~/workspace-ops
```

Add `--live` only when the Orca CLI is available. This measures the recorded
seat with `orca terminal list`; it does not spawn, close, or repair a terminal:

```console
$ python3 ~/workspace-ops/scripts/onboarding-rehearsal \
    --workspace-root ~/workspace \
    --ops-repo ~/workspace-ops \
    --live --json > onboarding-rehearsal.json
```

On Windows, use `python` in place of `python3`.

## Postcondition table

| ID | Postcondition | Evidence | Pass condition |
|---|---|---|---|
| P01 | Router inventory is complete | `ONBOARDING.md` index and `onboarding/*.md` | The sets are equal |
| P02 | Installation has no unresolved tokens | installation text files, excluding `.git/` and `.beads/` | No unresolved allowed token remains; the literal `{{...}}` shape mention is not a token |
| P03 | Ops host instructions agree | `CLAUDE.md` and `AGENTS.md` | Byte-identical |
| P04 | Live workspace card equals canonical card | root `CLAUDE.md` and `workspace-card/CLAUDE.md` | Byte-identical |
| P05 | Workspace descriptor satisfies loader rules | `config/workspace-descriptor.json` | JSON has the requested root, `workspace_root_is_plain_folder: true`, a nonempty `master_seat`, and a nonempty repository list |
| P06 | Host runtime is durable | `config/instance-runtime.json` | JSON exists and has `master_host_runtime` |
| P07 | Role state is present | `docs/runbooks/role-state.md` | File exists |
| P08 | Lineage is present | `docs/lineage/MASTER-LINEAGE.md` | File exists |
| L01 | A live terminal occupies the recorded seat | `orca terminal list --worktree ... --json` | Exactly one terminal; unavailable measurement is GAP |
| L02 | The terminal is actually the master | role state/lineage plus host identity | This script does not claim terminal presence proves role identity; it reports GAP |

`P04` is the equality check against the live workspace surface the host reads.
`L01` measures liveness separately. A terminal list cannot establish that the
terminal's process is the master, so `L02` remains an explicit honest gap until
the host exposes independently verifiable role identity.

Exit status is zero only when every row is PASS. A GAP is not a warning-shaped
pass: it means the check was not performed or the available evidence cannot
prove the postcondition. Use `--json` for CI or a later report generator; the
`gaps` array is intentionally preserved in that output.
