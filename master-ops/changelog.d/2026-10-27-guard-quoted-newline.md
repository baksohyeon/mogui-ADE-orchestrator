Product-path guard quoted newline (2026-10-27):

- Treat only an unquoted, unescaped newline as a command separator in the
  product-path guard. A newline inside single or double quotes stays part of
  its word, so `touch '<LF>' <product path>` is blocked instead of being split
  into two harmless-looking segments; a backslash newline is removed as a line
  continuation, as bash does.
- Deny a Bash command that contains an ANSI-C quote opener (`$'`, an
  unescaped `$` right before `'`, outside single quotes, double quotes, and
  comments) as unparseable in both modes, because bash reads `\'` inside it as
  an escaped quote and the guard's lexers do not, so `echo $'\''<LF>touch
  <product path><LF>#'` was allowed while bash ran the touch.
- Close three more lexer divergences in the product-path guard: a line
  continuation between `$` and its quote no longer hides the ANSI-C opener;
  an escaped heredoc operator (`ls \<<EOF`) no longer strips the following
  command lines as a body; and an unquoted-delimiter heredoc body is denied
  as unparseable when it contains `$(` or a backtick, because bash expands
  them into code. A bare `${...}` parameter expansion runs no code and is
  no longer denied on its own. A line continuation inside the body is
  removed before this check, matching bash's own line-continuation removal.
  Under `FAIL_CLOSED=1` a `$(` or backtick opener is always blocked; otherwise
  the body gets the same product-root, `cd`, and redirection scrutiny
  already applied to an interpreter-fed heredoc body, so a benign opener
  such as `$(date)` is admitted. Upgrade cost: a legacy-mode body that hides
  a product-root write behind obfuscation the shared scrutiny does not yet
  model can still pass; tightening that later means extending the shared
  scrutiny function, not this check.
