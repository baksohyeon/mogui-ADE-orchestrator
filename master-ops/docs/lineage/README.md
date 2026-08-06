# Lineage format and boot procedure

Lineage is append-only observability metadata. It is not a bootstrap source, priority
source, or model-evaluation source. The succession boot card requires the successor to
walk [the boot comparison set](../runbooks/boot-comparison-set.md) and record measured
values before appending an entry.

## Entry format

Every entry records:

- generation and succession reason;
- parent and successor references, with instance identifiers kept private;
- inherited role, open tracks, and verification result;
- measured boot-comparison values and the instrument used for each value;
- repeated-question, reopened-decision, and context-loss metrics when available;
- unknown or unmeasured facts explicitly marked `unconfigured` or `미확인`.

An entry without measured values is incomplete. Narrative claims do not replace the
instrument output. When a handoff conflicts with a fresh measurement, retain the conflict
and report the fresh measurement with its scope.

## Public boundary

Private operations records may retain session ids, process ids, terminal handles, and
workspace ids as instance history. This template carries the procedure and format only;
those identifiers are not transferable knowledge and must not be copied into public files.
