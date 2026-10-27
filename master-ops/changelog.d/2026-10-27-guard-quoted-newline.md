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
  command lines as a body; and an unquoted-delimiter heredoc body containing
  `$(`, a backtick, or `${` is denied as unparseable, because bash expands it.
