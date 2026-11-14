# docs: check web pages headless or in Orca's browser first

Workers now use Orca's embedded browser first, then headless capture or `curl`,
with Computer Use requiring a coordinator ask when a visible GUI is necessary.
Issue #281.
