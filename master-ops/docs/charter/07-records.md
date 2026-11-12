# §7. Records

Governs document ownership and record separation. See the index: [`../MASTER-OPERATIONS.md`](../MASTER-OPERATIONS.md).

Separate record ownership:

- Execution state: issue tracker
- Long-term planning, design, runbooks, decisions, and lineage: Git

Do not narrate the same fact in both systems. Put intermediate progress notes in the issue tracker. Put accepted decisions and durable procedures in Git.

Explanations written in chat to resolve owner confusion are documentation candidates by default. Decide in the same work cycle whether the explanation belongs in public template docs or an operations guide, and land it there when it would prevent recurrence. Chat is not a documentation surface.

Every time in a record, report, or owner-facing message is an exact minute anchored to one named event, the start or the completion of the work, read from an instrument (a commit time such as `git log --format=%ci`, a transcript record's timestamp, `date` at the event, a tool's completion line). Masked or rounded forms ("13:3x", "about 16:30", "around 4 pm") are not written. When the anchor is not obvious, name it once. A masked time widens the error the owner must accept from about 1 minute to up to 10.

Do not store credentials, secrets, raw environment values, or secret-dependent implementation detail in operations documents.
