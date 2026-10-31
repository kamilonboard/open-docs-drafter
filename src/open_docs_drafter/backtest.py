"""Backtest: run rule-based triage over real merged pull requests.

Used to check a profile before and after every rule change. With a baseline profile it
reports which pull requests changed tier, so a change that lowers a tier is never silent.
"""

import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from open_docs_drafter.github import PullRequest
from open_docs_drafter.layers.triage import TriageResult, rule_based_tier
from open_docs_drafter.profile import Profile
from open_docs_drafter.tiers import Tier


@dataclass(frozen=True)
class PRResult:
    pr: PullRequest
    triage: TriageResult

    def reasons(self, limit: int = 3) -> list[str]:
        """The evidence behind the final tier, most specific first."""
        top = [m for m in self.triage.matches if m.tier == self.triage.tier]
        seen: list[str] = []
        for m in top:
            item = f"{m.rule_id}: {m.evidence}"
            if item not in seen:
                seen.append(item)
        if not seen:
            seen = [f"no rule (default tier): {p}" for p in self.triage.unmatched_files]
        return seen[:limit]


@dataclass(frozen=True)
class TierChange:
    number: int
    title: str
    before: Tier
    after: Tier

    @property
    def lowered(self) -> bool:
        return self.after < self.before


def changed_lines(patch: str) -> list[str]:
    """Added and removed lines from unified diff hunks, without the +/- marker."""
    return [
        line[1:]
        for line in patch.splitlines()
        if line[:1] in ("+", "-") and not line.startswith(("+++", "---"))
    ]


def triage_pr(profile: Profile, pr: PullRequest) -> PRResult:
    texts = [pr.title, pr.body]
    for f in pr.files:
        texts.extend(changed_lines(f.patch))
    return PRResult(pr, rule_based_tier(profile, [f.path for f in pr.files], texts))


def run(profile: Profile, prs: Sequence[PullRequest]) -> list[PRResult]:
    return [triage_pr(profile, pr) for pr in prs]


def tier_counts(results: Sequence[PRResult]) -> dict[str, int]:
    counts = Counter(r.triage.tier for r in results)
    return {t.name: counts.get(t, 0) for t in sorted(Tier, reverse=True)}


def compare(baseline: Sequence[PRResult], current: Sequence[PRResult]) -> list[TierChange]:
    before = {r.pr.number: r.triage.tier for r in baseline}
    return [
        TierChange(r.pr.number, r.pr.title, before[r.pr.number], r.triage.tier)
        for r in current
        if r.pr.number in before and before[r.pr.number] != r.triage.tier
    ]


# ------------------------------------------------------------------ output


def format_text(results: Sequence[PRResult], changes: Sequence[TierChange] | None) -> str:
    lines = []
    for r in results:
        title = r.pr.title if len(r.pr.title) <= 60 else r.pr.title[:57] + "..."
        lines.append(f"#{r.pr.number:<6} {r.triage.tier.name:<5}  {title}")
        for reason in r.reasons():
            lines.append(f"{'':16}{reason}")
    lines.append("")
    lines.append(_summary(results))
    lines.extend(_change_lines(changes))
    return "\n".join(lines)


def format_markdown(results: Sequence[PRResult], changes: Sequence[TierChange] | None) -> str:
    lines = ["| PR | Tier | Title | Why |", "|---|---|---|---|"]
    for r in results:
        title = r.pr.title.replace("|", "\\|")
        why = "<br>".join(f"`{x}`" for x in r.reasons()).replace("|", "\\|")
        lines.append(f"| #{r.pr.number} | {r.triage.tier.name.title()} | {title} | {why} |")
    lines.append("")
    lines.append(_summary(results))
    lines.extend(_change_lines(changes))
    return "\n".join(lines)


def format_json(results: Sequence[PRResult], changes: Sequence[TierChange] | None) -> str:
    data: dict[str, object] = {
        "counts": tier_counts(results),
        "pulls": [
            {
                "number": r.pr.number,
                "title": r.pr.title,
                "merged_at": r.pr.merged_at,
                "tier": r.triage.tier.name,
                "matches": [
                    {"rule": m.rule_id, "tier": m.tier.name, "evidence": m.evidence}
                    for m in r.triage.matches
                ],
                "unmatched_files": list(r.triage.unmatched_files),
            }
            for r in results
        ],
    }
    if changes is not None:
        data["changes"] = [
            {"number": c.number, "before": c.before.name, "after": c.after.name} for c in changes
        ]
    return json.dumps(data, indent=2)


def _summary(results: Sequence[PRResult]) -> str:
    counts = tier_counts(results)
    return f"{len(results)} PRs: " + ", ".join(f"{n.lower()} {c}" for n, c in counts.items())


def _change_lines(changes: Sequence[TierChange] | None) -> list[str]:
    if changes is None:
        return []
    if not changes:
        return ["No tier changes against the baseline."]
    lowered = sum(c.lowered for c in changes)
    out = [f"{len(changes)} tier changes against the baseline ({lowered} lowered):"]
    for c in changes:
        mark = "  LOWERED, check by hand" if c.lowered else ""
        out.append(f"  #{c.number:<6} {c.before.name} -> {c.after.name}  {c.title[:50]}{mark}")
    return out
