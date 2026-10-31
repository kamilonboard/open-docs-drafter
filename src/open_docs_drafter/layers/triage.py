"""Layer 2: Triage and tiering.

Classifies a change as green, amber or red. Paths and keywords from the core rules and
the project profile can only raise the tier, never lower it. On failure: default to the
higher tier.

This module holds the rule-based part, which is plain code. A model-based signal will be
added later; it will be combined with `raise_tier`, so it can raise but never lower the
rule-based result.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase

from open_docs_drafter.core_rules import Rule
from open_docs_drafter.keywords import contains_keyword, words
from open_docs_drafter.profile import Profile
from open_docs_drafter.tiers import Tier, raise_tier

LAYER = 2
AI_INVOLVED = True


@dataclass(frozen=True)
class Match:
    rule_id: str
    tier: Tier
    reason: str
    evidence: str  # The file path or keyword that triggered the rule.


@dataclass(frozen=True)
class TriageResult:
    tier: Tier
    matches: tuple[Match, ...]
    unmatched_files: tuple[str, ...]  # Files no path rule covered; they get the default tier.


def rule_based_tier(
    profile: Profile, changed_files: Sequence[str], texts: Iterable[str] = ()
) -> TriageResult:
    """Tier a change from its changed files and its text (diff, PR title and body).

    Each file gets the highest tier of the path rules it matches, or the profile's
    default tier if none match, so a green rule can never hide an unrecognised file.
    Keyword hits anywhere in the text then raise the result further. Pull request text
    is untrusted, but here it can only raise the tier, which is the safe direction.
    """
    rules = profile.all_rules
    tier = Tier.GREEN
    matches: list[Match] = []
    unmatched: list[str] = []

    for path in changed_files:
        file_matches = [
            Match(rule.id, rule.tier, rule.reason, path)
            for rule in rules
            if _path_matches(rule, path)
        ]
        if file_matches:
            matches.extend(file_matches)
            tier = raise_tier(tier, max(m.tier for m in file_matches))
        else:
            unmatched.append(path)
            tier = raise_tier(tier, profile.default_tier)

    text_words = words("\n".join(texts))
    for rule in rules:
        for keyword in rule.keywords:
            if contains_keyword(text_words, keyword):
                matches.append(Match(rule.id, rule.tier, rule.reason, keyword))
                tier = raise_tier(tier, rule.tier)

    if not changed_files and not matches:
        tier = profile.default_tier

    return TriageResult(tier=tier, matches=tuple(matches), unmatched_files=tuple(unmatched))


def _path_matches(rule: Rule, path: str) -> bool:
    return any(fnmatchcase(path, pattern) for pattern in rule.paths)
