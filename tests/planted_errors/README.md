# Planted-error suite

Fake pull requests that the tool must catch, every one, on every CI run. **A single miss
fails CI and blocks a release of the tool.**

- [`hazards.yaml`](hazards.yaml): the hazard log from the safety design (H1–H10).
- [`cases/`](cases/): the fake pull requests, grouped by hazard.
- [`test_planted_errors.py`](test_planted_errors.py): the runner.

```sh
uv run pytest tests/planted_errors -rs
```

`-rs` lists the pending checks, so you can see what isn't covered yet.

## A case

```yaml
- id: pe-h2-algorithm-change-as-ui-fix
  hazard: H2
  summary: A change to the oref dosing code is described as a UI-only tweak.
  pr:
    title: Tidy up the status label
    body: UI only, no functional change.
    files:
      - path: trio-oref/lib/determine-basal/determine-basal.js
        patch: |
          @@ -812 +812 @@
          -    var maxDeltaPercent = 0.2;
          +    var maxDeltaPercent = 0.3;
  expect:
    triage: {min_tier: red}
    input_check:
      discarded: true
      findings_include: [scope-claim-contradicts-diff]
    pending:
      - component: layer 5
        check: What the layer must do once it exists.
```

| Key | Checks |
|---|---|
| `triage.min_tier` | Rule-based tier is at least this |
| `input_check.discarded` | Layer 1 discards (or keeps) the PR text |
| `input_check.findings_include` | Layer 1 reports these finding codes |
| `input_check.text_excludes` | These strings never reach later layers |
| `input_check.diff_tier_min` | The diff's own tier, ignoring PR text, is at least this |
| `facts.inconsistent` / `facts.consistent` | Layer 3 flags (or doesn't flag) these settings as disagreeing with themselves |
| `facts.needs_human` | Layer 3 can't read these settings exactly and says why |
| `facts.values` | `setting.kind: value` pairs Layer 3 must extract exactly |
| `facts.changes` | Exact before-and-after facts between `base_snapshot` and `snapshot` |
| `pending` | A check for a layer not built yet; shown as a skipped test |

Fact cases use `snapshot` (whole files, path to text) instead of `pr`.

Case files are validated strictly. A misspelt key is an error, never a silent pass.

## Rules

- Every hazard in `hazards.yaml` needs at least one case, or a `manual` reason.
- When a layer is built, add its check to the runner and move each case's `pending` entry
  into `expect`.
- Never delete or loosen a case to make CI pass. Fix the tool, or discuss it in an issue.

## Proof that the suite catches regressions (2026-10-31)

Each safeguard was broken in turn in a copy of the code. The suite failed every time:

| Safeguard removed | Cases failed |
|---|---:|
| Instruction detection | 6 |
| Keyword matching in triage | 5 |
| Scope-claim check | 4 |
| Number redaction | 2 |
| Hidden-Unicode check | 2 |
| `trio-oref/*` red rule | 2 |
| NFKC folding | 1 |
| Zero-width character removal | 1 |
| Amber default for unknown files | 1 |
| Misspelt expectation key | collection error |

Layer 3 (fact extraction), checked the same way:

| Safeguard removed | Cases failed |
|---|---:|
| Unit facts | 2 |
| Detecting changed values | 2 |
| Defaults-disagree check | 1 |
| Help-text check | 1 |
| Percent equivalence for factors | 1 |
| Treating calculations as unreadable | 1 |
| Flagging runtime-dependent help text | 1 |
| Linking JSON keys to Swift names | 1 |
