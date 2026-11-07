"""Release digest: every merged change between two releases, drafted or not.

This is the control for hazards H3 (settings reset not documented) and H7 (change missed
entirely). Drafting works one pull request at a time, so a PR that was never drafted
leaves no trace there. The digest starts from the release range instead, so such a PR
still shows up. It is plain code and uses no model.

Titles and commit subjects are untrusted (core rule 7), so they appear as plain text only.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from open_docs_drafter import backtest
from open_docs_drafter.layers.triage import TriageResult
from open_docs_drafter.models import DirectCommit, PullRequest
from open_docs_drafter.profile import Profile
from open_docs_drafter.tiers import Tier

__all__ = [
    "NOT_DRAFTED",
    "Digest",
    "DigestEntry",
    "DirectCommit",
    "build",
    "format_markdown",
    "outcomes_from_audit",
    "plain_text",
]

NOT_DRAFTED = "not drafted"


@dataclass(frozen=True)
class DigestEntry:
    pr: PullRequest
    triage: TriageResult
    status: str  # The pipeline outcome from the audit log, or NOT_DRAFTED.

    @property
    def settings_reset(self) -> bool:
        # Core and profile rules both say "reset" in their reason, so a profile's own
        # migration rule counts too.
        return any("reset" in m.reason.lower() for m in self.triage.matches)

    @property
    def needs_attention(self) -> bool:
        return self.triage.tier is Tier.RED or self.settings_reset


@dataclass(frozen=True)
class Digest:
    project: str
    base: str
    head: str
    entries: tuple[DigestEntry, ...]  # Highest tier first.
    direct_commits: tuple[DirectCommit, ...]


def build(
    profile: Profile,
    base: str,
    head: str,
    prs: Sequence[PullRequest],
    direct_commits: Sequence[DirectCommit],
    outcomes: Mapping[int, str],
) -> Digest:
    entries = [
        DigestEntry(
            pr, backtest.triage_pr(profile, pr).triage, outcomes.get(pr.number, NOT_DRAFTED)
        )
        for pr in prs
    ]
    entries.sort(key=lambda e: (-e.triage.tier, e.pr.number))
    return Digest(profile.project.name, base, head, tuple(entries), tuple(direct_commits))


def outcomes_from_audit(runs: Path) -> dict[int, str]:
    """The newest pipeline outcome per pull request, from the audit records."""
    newest: dict[int, tuple[str, str]] = {}
    if not runs.exists():
        return {}
    for path in runs.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            number = record["pull_request"]["number"]
            found = (record["created_at"], record["outcome"])
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ValueError(f"unreadable audit record {path}: {exc}") from exc
        if number not in newest or found > newest[number]:
            newest[number] = found
    return {number: outcome for number, (_, outcome) in newest.items()}


def plain_text(text: str) -> str:
    """Untrusted text as inert Markdown: no links, HTML, table breaks or @mentions."""
    text = " ".join(text.split()).replace("&", "&amp;").replace("<", "&lt;")
    for char in "\\`*_[]|":
        text = text.replace(char, "\\" + char)
    return text.replace("@", "@​")  # A zero-width space stops the mention.


def _line(entry: DigestEntry) -> str:
    return f"- #{entry.pr.number} {plain_text(entry.pr.title)} ({entry.status})"


def _why(entry: DigestEntry) -> str:
    top = [m for m in entry.triage.matches if m.tier == entry.triage.tier]
    seen = list(dict.fromkeys(f"{m.rule_id}: {m.evidence}" for m in top))[:2]
    return "; ".join(plain_text(x) for x in seen) or "no rule, default tier"


def format_markdown(digest: Digest) -> str:
    entries = digest.entries
    counts = _tier_counts(entries)
    resets = [e for e in entries if e.settings_reset]
    red = [e for e in entries if e.needs_attention and not e.settings_reset]
    lines = [
        f"# {plain_text(digest.project)} release digest: "
        f"{plain_text(digest.base)} to {plain_text(digest.head)}",
        "",
        f"{len(entries)} merged pull requests: {counts}. "
        f"{len(digest.direct_commits)} commits with no pull request.",
        "",
        "## Settings resets",
        "",
        "Check that the release notes warn about each of these. The rules can miss a reset, "
        "so an empty list proves nothing.",
        "",
    ]
    lines += [_line(e) for e in resets] or ["None found by the rules."]
    lines += ["", "## Other red changes", "", "A human writes these docs by hand.", ""]
    lines += [_line(e) for e in red] or ["None."]
    if digest.direct_commits:
        lines += [
            "",
            "## Commits with no pull request",
            "",
            "Nothing else in this digest covers these. Read them by hand.",
            "",
        ]
        lines += [f"- `{c.sha[:7]}` {plain_text(c.subject)}" for c in digest.direct_commits]
    lines += [
        "",
        "## All merged pull requests",
        "",
        "| PR | Tier | Status | Title | Why |",
        "|---|---|---|---|---|",
    ]
    lines += [
        f"| #{e.pr.number} | {e.triage.tier.name.title()} | {e.status} "
        f"| {plain_text(e.pr.title)} | {_why(e)} |"
        for e in entries
    ]
    return "\n".join(lines) + "\n"


def _tier_counts(entries: Sequence[DigestEntry]) -> str:
    return ", ".join(
        f"{tier.name.lower()} {sum(e.triage.tier is tier for e in entries)}"
        for tier in sorted(Tier, reverse=True)
    )
