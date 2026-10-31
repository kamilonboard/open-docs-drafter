# Trio profile

Tier rules for [Trio](https://github.com/nightscout/Trio) and
[TrioDocs](https://github.com/nightscout/trio-docs), in [`profile.yaml`](profile.yaml).

**Status: draft.** These rules are a first proposal and still need agreement from Trio's
maintainers. The profile can add rules but never switch off a core rule.

## Try it

```sh
uv run open-docs-drafter check-profile profiles/trio/profile.yaml
uv run open-docs-drafter triage --profile profiles/trio/profile.yaml \
    --file Trio/Sources/Modules/ISFEditor/View/ISFEditorRootView.swift \
    --text "Rename the save button"
```

## First check against real pull requests (2026-10-31)

Rule-based triage only, run over Trio's 40 most recently merged pull requests (#1619–#1711),
using changed files, title, body and added/removed diff lines.

| Tier  | PRs |
|-------|----:|
| Red   | 23  |
| Amber | 17  |
| Green | 0   |

Every algorithm, dosing and alarm change came out red (for example #1651, #1679, #1645,
#1696). The rules over-flag in the safe direction. Examples: UI-only padding changes in the
Adjustments screens (#1684, #1685), dead-code removals that mention `basal` (#1711, #1693),
and a sound-licence note that mentions `alarm` (#1658). No PR reached green, mostly because
almost every PR touches at least one file no rule covers, which defaults to amber.

## Questions for Trio maintainers

- Should UI-only changes to therapy and adjustment screens stay red, or become amber?
- Should the bolus and carb entry screens (Treatments, AddCarbs) be red or amber?
- Which other paths are safe to mark green, so that fewer files fall back to amber?
- Should keywords on removed lines (dead-code clean-ups) still raise the tier?
