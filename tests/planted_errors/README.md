# Planted-error suite

Fake pull requests that the tool must catch, every one, on every CI run. A single miss blocks a
release of the tool. Planned cases: false numbers, unit swaps (mg/dL vs mmol/L), hidden
instructions in PR text, silent settings resets, and algorithm changes disguised as UI fixes.

This suite is built before any drafting code.
