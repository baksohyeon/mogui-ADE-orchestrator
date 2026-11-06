# orca-json

`scripts/lib/orca_json.py` is the one place that reads JSON out of `orca
orchestration` and `orca terminal` commands. From orca 1.4.246 (2026-11-02)
those commands answer with different keys, with no deprecation notice; every
reader that used a one-off key path or a hand-rolled `jqf` expression failed
silent (an empty string or `None`, never an error) the moment the shape
changed under it. The rule going forward: **every reader of a field this
module normalizes goes through it; a new key goes into the module and its
test, nowhere else.**

Not yet migrated, so still exposed to the next shape change: `scripts/spawn-test`'s
coordinator-run detection (greps for the old `"run": {` shape directly) and
`scripts/dispatch-smoke`'s two `dispatch-show` reads (`d["result"]["dispatch"]["status"]`,
old path only). `worker-wait`'s `_terminal_list` (`terminal list --json`'s
`terminals[].handle`) and its `_last_non_keepalive` envelope parser (which
filters `check --wait`'s interleaved keepalive documents, a different job
from `parse_envelope`'s shape handling) are also outside the module.

## Measured shapes

Measured by the maintainer on orca 1.4.249 (2026-11-07), against the old
shape every script here previously assumed:

| command | old path | 1.4.246+ path |
|---|---|---|
| `task-create --json` | `result.task.id` | `result.taskId` (`result.status` beside it) |
| `run-current --json` | `result.run.id` | `result.runId`, confirmed live: `{"ok":true,"result":{"runId":null}}` for a session with no bound Run |
| `worker-list --json` | `workers[].dispatchStatus`, `workers[].agentTerminalHandle`, `result.page.nextCursor`/`result.page.hasMore` | `workers[].outcome` (`succeeded`/`failed`/`in_progress`), `workers[].terminal`, `result.nextCursor` (empty string means last page); confirmed live |
| `check --json` | `result.deliveryId` (then `--ack`) | no delivery id at all; a consuming `check` marks the batch handled server-side; `--ack` is a no-op |
| `send` | no `--subject` | `--subject` is required, else `invalid_argument` |
| `task-update` | `--task <id>` | `--id <id>`; statuses `pending, ready, dispatched, completed, failed, blocked` |
| `terminal create --json` | `result.terminal.handle` | `result.terminalHandle` or `result.handle` (peer-seat report, not independently re-measured here, see below) |
| `dispatch --inject --json` / `dispatch-show --json` | `result.dispatch.id`, `result.dispatch.status` | `result.dispatchId`, `result.status` (peer-seat report, not independently re-measured here) |

`task-create`, `task-update`, `terminal create`, and `dispatch --inject` are
coordinator-level mutations. A dispatched worker cannot run them against its
own Run (`run_required` with no `--run`, `worker_cannot_coordinate_own_run`
with it), confirmed live while writing this module. The `terminal create` /
`dispatch` rows above therefore carry a peer seat's reported key names, not
an independent live measurement; re-measure them from a coordinator session
before depending on a specific precedence between `terminalHandle` and
`handle` if both ever land in the same response.

## The module

`scripts/lib/orca_json.py`, stdlib only:

- `task_id(result)`, `run_id(result)`, `terminal_handle(result)`,
  `dispatch_id(result)`, `dispatch_status(result)`: each reads the old path
  first, the new path second, and returns `None` when neither exists.
- `delivery_id(result)`: `None` on both an old-shape unacked batch and the
  whole of 1.4.246+, which dropped the field.
- `messages(result)`: `result.get("messages") or []`.
- `workers(result)`: normalized `{dispatch_id, task_id, status, terminal}`
  rows from a `worker-list` result, either shape. A row's "still active"
  status is always reported as `in_progress` (old `dispatchStatus:
  dispatched` and new `outcome: in_progress` both normalize to it); any other
  status value passes through unchanged.
- `next_cursor(result)`: `None` at the last page for both shapes.
- `parse_envelope(text)`: decodes the **last** JSON document in `text` and
  returns `(ok, result, error)`. orca sometimes prints a human-readable line
  after the JSON on failure (`error: run_required: ...`); this ignores that
  trailing text instead of failing the whole parse the way `json.loads` on
  the raw string would.

Importable two ways, both used in this tree:

```python
# from a Python script beside it: load the file directly, not via
# `from lib import orca_json`. `lib/` has no `__init__.py`, so it resolves
# as a PEP 420 namespace package, and an unrelated `lib` package elsewhere
# on sys.path can shadow or merge with it. This is how worker-wait does it.
import importlib.util
path = scripts_dir / "lib" / "orca_json.py"
spec = importlib.util.spec_from_file_location("orca_json", path)
orca_json = importlib.util.module_from_spec(spec)
spec.loader.exec_module(orca_json)
```

```sh
# from a one-liner (dispatch's orca_json_read helper): pass the path
# through argv, not by interpolating it into the Python source. A checkout
# path can contain a quote character, which would break the string literal.
python3 -c "
import sys
sys.path.insert(0, sys.argv[1])
from lib import orca_json
print(orca_json.task_id({'taskId': 'task_x'}))
" "<scripts-dir>"
```

## Callers

- `scripts/dispatch`'s `orca_json_read <func>` helper feeds raw `--json`
  stdout through `parse_envelope` and the named reader on stdin, printing the
  value or an empty line. All four readers (`task-create`, `terminal
  create`, `dispatch --inject`, `dispatch-show`) now call it; an empty read
  prints the first 200 characters of the raw response to stderr before the
  existing failure line.
- `scripts/worker-wait`'s `_resolve_bound_run`, `_worker_list`, and the
  `check`/ack handling in `_wait_for_message` / `_flush_ack` all route
  through the module. `_worker_list`'s "still dispatched" filter checks
  `status == "in_progress"` (the module's normalized value), not the old
  shape's literal `"dispatched"`. `_terminal_list` (`terminal list --json`)
  does not; see "Not yet migrated" above.

## Tests

- `scripts/test-orca-json.sh`: one fixture per shape per function, plus
  `parse_envelope`'s trailing-human-line and two-JSON-document cases. Builds
  an old-path-only mutant copy of the module (never the committed file) and
  confirms every new-shape case fails against it.
- `scripts/test-worker-wait.sh`: the pre-existing old-shape fixtures stay;
  adds one new-shape `worker-list` fixture (DEAD verdict via
  `outcome`/`terminal`/`nextCursor`) and one `check`-without-`deliveryId`
  case, each with its own old-path-only mutant. Because `worker-wait` now
  hard-depends on its `lib/orca_json.py` sibling (and, as before,
  `mogui_log.py`), every sed-mutated copy of the script in this file stages
  both alongside itself before running. A bare `cp`/`sed` of just the
  script, the way the pre-existing DEAD and lock-held cases used to work on
  their own, now fails on `ModuleNotFoundError: No module named 'lib'`.

## The rule

A new orca version changing one of these keys again means: add the new path
to the relevant function in `scripts/lib/orca_json.py`, add its fixture to
`scripts/test-orca-json.sh`, and update the measured-shapes table above. For
a field this module already normalizes, nothing outside it should read
`result["..."]` directly; migrating the "Not yet migrated" callers above
onto the module is separate, tracked work.
