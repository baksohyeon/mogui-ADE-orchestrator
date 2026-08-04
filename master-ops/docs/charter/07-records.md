# §7. Records

Governs document ownership and record separation. See the index: [`../MASTER-OPERATIONS.md`](../MASTER-OPERATIONS.md).

Separate record ownership:

- Execution state: issue tracker
- Long-term planning, design, runbooks, decisions, and lineage: Git

Do not narrate the same fact in both systems. Put intermediate progress notes in the issue tracker. Put accepted decisions and durable procedures in Git.

Explanations written in chat to resolve owner confusion are documentation candidates by default. Decide in the same work cycle whether the explanation belongs in public template docs or an operations guide, and land it there when it would prevent recurrence. Chat is not a documentation surface.

Do not store credentials, secrets, raw environment values, or secret-dependent implementation detail in operations documents.
