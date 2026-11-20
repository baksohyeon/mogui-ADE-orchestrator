- Runbook structure (#356) now gives every runbook front matter, a generated
  index, and a bounded `Brief`. Dispatch contracts can name `runbooks` and
  `runbooks_waived`; the gate records trigger, existence, injection, and Brief
  outcomes, while the wrapper injects each named Brief before the worker starts.
