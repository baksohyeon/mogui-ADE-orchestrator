Product-path guard quoted newline (2026-10-27):

- Treat only an unquoted, unescaped newline as a command separator in the
  product-path guard. A newline inside single or double quotes stays part of
  its word, so `touch '<LF>' <product path>` is blocked instead of being split
  into two harmless-looking segments; a backslash newline is removed as a line
  continuation, as bash does.
