# Master Operations Card ({{WORKSPACE_NAME}})

- This repository is the workspace/orchestrator operations layer for `{{WORKSPACE_NAME}}`. Do not load repository-level coding rules globally here; each product repo owns its own code rules.
- Workspace root: `{{WORKSPACE_ROOT}}`
- Operations repository: `{{OPS_REPO}}`
- Workspace repositories: `{{REPO_LIST}}`
- Master operations SSOT: `docs/MASTER-OPERATIONS.md`
- Role state SSOT: `docs/runbooks/role-state.md`
- Execution state belongs in the issue tracker. Plans, designs, closed decisions, and durable runbooks belong in Git.
- After compaction, clear, or session recovery, first reload issue-tracker context and re-check active tracks before continuing.
- Sensitive lanes such as auth, permission, credentials, production data, and secrets should be delegated to a dedicated security or operations session. The master coordinates and verifies; it does not improvise sensitive implementation.
- Default master model identifier to measure at boot: `{{MODEL_ID}}`
- Context-quality monitor namespace: `{{MONITOR_NS}}`
