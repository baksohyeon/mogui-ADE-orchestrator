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
  under `FAIL_CLOSED=1` when it contains `$(`, a backtick, or a `${...@P}`
  prompt-expansion transformation, because bash expands them into code. The
  deny reason recorded is `heredoc body expansion`, filed in the event log
  under the same `unresolved_target` bucket an unparseable command lands in.
  A bare `${...}` parameter expansion without `@P` runs no code and is not
  denied on its own. A line continuation inside the body is removed before
  this check, matching bash's own line-continuation removal. In legacy mode
  (the default) that body is instead admitted only when it names no product
  root and the shell's own working directory is not already inside one; the
  same `cd`, redirection-into-root, and product-root scrutiny already
  applied to an interpreter-fed heredoc body decides it, so a benign opener
  such as `$(date)` still passes outside a product root.
  Upgrade cost: a legacy-mode body that hides a product-root write behind
  obfuscation the shared scrutiny does not yet model can still pass;
  tightening that later means extending the shared scrutiny function, not
  this check.
- The legacy-mode product-root scrutiny above tested the body text for the
  configured root's exact realpath string, so a symlinked spelling, `~/...`,
  a `./`- or `../`-relative spelling, or a bare relative spelling with a
  slash all resolved into the root without that string ever appearing and
  were admitted. It now resolves each such body token against the shell's
  working directory and checks the result, the way the redirection-into-root
  check already does for a redirect target, so every one of those spellings
  denies. A bare directory name with no slash at all (`rm -rf product` with
  the working directory beside the root) is a known gap left for a later
  round.
