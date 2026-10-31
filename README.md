# open-docs-drafter

**Status: early development.** Layers 1 (input check), 3 (fact extraction) and 5 (citation and number check), rule-based triage and the planted-error suite are built. Nothing drafts docs yet.

open-docs-drafter watches open-source automated insulin delivery (OS-AID) projects on GitHub and drafts documentation updates from merged code changes. It only opens **draft pull requests for human review**. It never merges anything.

The first target is [Trio](https://github.com/nightscout/Trio) and its docs ([TrioDocs](https://github.com/nightscout/trio-docs), MkDocs Material). AAPS and LoopDocs come later. Each project plugs in through a profile file and adapters.

> [!WARNING]
> This tool does not give therapy or dosing advice and is not a medical device. Every draft it produces must be checked by a human before it reaches users.

## Safety goal

**Zero unsupported claims reach users.** AI models can't be made hallucination-free, so the design makes every claim machine-checkable and keeps a human as the final gate.

## Core rules

These rules live in the core engine. A project profile can add rules but can never switch these off.

1. **Draft only.** It opens draft PRs on a fork. It never merges, never pushes to a protected branch and never writes upstream.
2. **Evidence or silence.** Every factual statement must cite a specific line in the diff or PR. A statement with no citation is removed.
3. **Abstaining is success.** When the evidence is unclear, it outputs "needs human" instead of guessing.
4. **Numbers come from code, not the model.** Setting names, defaults, ranges, units and UI labels are extracted deterministically.
5. **Warnings are protected.** It can never delete or weaken an existing warning or caution box.
6. **Red-tier changes get no AI text.** Algorithm, dosing and settings-reset changes are flagged for a human expert, never drafted.
7. **Inputs are untrusted.** PR text is treated as data and cross-checked against the actual diff.
8. **English source only.** Translations stay with human volunteers.
9. **Everything is traceable.** Each draft records its inputs, model and version, prompts and outputs.

## Protection layers

| # | Layer | AI? |
|---|---|---|
| 1 | Input check: PR text vs. actual diff | No |
| 2 | Triage into green / amber / red (rules can only raise a tier) | Yes |
| 3 | Fact extraction from source files | No |
| 4 | Grounded drafting with a citation for every claim | Yes |
| 5 | Citation and number check | No |
| 6 | Independent verifier model | Yes |
| 7 | Edit constraints (size cap, warning protection) | No |
| 8 | Human review and sign-off | Humans |

## Risk tiers

| Tier | What the tool does | Approvals |
|---|---|---|
| Red | No AI text; opens a flag with an evidence pack | Experienced human writes it |
| Amber | Drafts, then escalates | Code author + docs maintainer |
| Green | Drafts | One human |

## Roadmap

- [x] Trio profile file with tier rules (draft, needs maintainer review)
- [ ] Deterministic layers (1, 3, 5, 7) with their own tests (layers 1, 3 and 5 done)
- [x] Planted-error test suite, built before any drafting code ([tests/planted_errors](tests/planted_errors); 4 checks pending later layers)
- [ ] Backtest on past Trio releases
- [ ] Shadow mode, agreed with Trio maintainers

## Licence

[MIT](LICENSE). Docs edits proposed to other projects are contributed under those projects' own licences.
