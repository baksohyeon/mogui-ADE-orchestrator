Upgrade installs now record a `git describe --tags --match` suffix using the
release tag named in `TEMPLATE-VERSION` when the template source is ahead of
that tag. Template stamps use the form `vX.Y.Z` or `vX.Y.Z-N-g<sha>`;
`template-check` now answers `cannot measure` with exit 2 for an installed
stamp in any other form. The resolver validates and compares the same
measurable stamp grammar and treats equal-distance stamps with different
commit IDs as unmeasurable. Registered intentional removals are now
recognized by both `template-check` and `template-apply`, including the write
pass, while malformed retirement records refuse writes. Existing operations
repositories must run Upgrade mode to pick up these changes, and template test
comments remain readable after placeholder substitution.
