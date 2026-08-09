"""Fail-close gate wrapper."""

import sys
import inspect

from mogui_errors import EXIT_PASS, EXIT_UNDETERMINED, MoguiError
from mogui_log import emit, human

_EMIT_RESERVED = set(inspect.signature(emit).parameters)


def run_gate(name, body) -> int:
    """Run a measurement and map pass/finding/unknown to 0/1/2."""
    try:
        fields = body() or {}
        line = emit("info", name, "pass", evidence="observed", **fields)
    except MoguiError as error:
        outcome = "finding" if error.exit_code == 1 else "undetermined"
        context = {
            f"context_{key}" if key in _EMIT_RESERVED else key: value
            for key, value in error.context.items()
        }
        line = emit(error.level, error.event, outcome, component=error.component,
                    evidence=error.evidence, reason=error.reason, **context)
        print(human(line), file=sys.stderr)
        return error.exit_code
    except Exception as error:
        line = emit("warn", name, "undetermined", evidence="unknown",
                    reason=f"unexpected:{type(error).__name__}")
        print(human(line), file=sys.stderr)
        return EXIT_UNDETERMINED
    print(human(line))
    return EXIT_PASS


if __name__ == "__main__":
    sys.exit(run_gate("dispatch_gate", lambda: {"reason": "within_budget"}))
