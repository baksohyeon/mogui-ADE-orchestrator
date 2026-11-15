Codex dispatch briefs now include the measured branch, origin URL, and owner/repo
for authorized push and pull-request commands. An unmeasured destination is called
out explicitly and leaves push unauthorized. Product-repository discovery accepts
credential-bearing HTTPS and user/port SSH remotes while briefs display sanitized
GitHub URLs without remote userinfo. Repository components such as `.github` remain
valid, and branch names with Markdown delimiters receive safe code spans with
boundary padding when needed. Reused-terminal alignment no longer blocks dispatch.
When alignment is unavailable or mismatched, Codex receives an unmeasured no-push
paragraph and dispatch prints one warning, while other runtimes proceed without an
egress warning.
The authorized GraphQL scope is stated as read-only queries, with mutations and
other network writes explicitly unauthorized.
