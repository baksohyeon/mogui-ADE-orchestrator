# Role State

Current Role: (not booted; declare on first master start)
Role Lock: ENABLED
Frozen: all other roles
Unlock: explicit user instruction only

- Generation: 0 (set to 1 on first boot)
- Last transition: none
- Update rule: update only on role switch immediately after Proposal -> Approval, or during succession boot. Git history is the transition audit trail.

Allowed roles:

- Architecture
- Research
- Reference Implementation
- Feature Implementation
- Release / Operations
- Incident Response
- Maintenance
