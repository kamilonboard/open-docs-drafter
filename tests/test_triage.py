import pytest

from open_docs_drafter.keywords import contains_keyword, words
from open_docs_drafter.layers.triage import rule_based_tier
from open_docs_drafter.profile import parse_profile
from open_docs_drafter.tiers import Tier

PROFILE = parse_profile(
    {
        "profile_version": 1,
        "project": {
            "name": "Example",
            "code_repo": "org/app",
            "docs_repo": "org/docs",
            "docs_branch": "main",
            "docs_format": "mkdocs",
        },
        "rules": [
            {"id": "ex-red-algo", "tier": "red", "reason": "Algorithm", "paths": ["algo/*"]},
            {"id": "ex-green-ui", "tier": "green", "reason": "UI", "paths": ["ui/*"]},
        ],
    }
)


def test_green_files_only_is_green() -> None:
    assert rule_based_tier(PROFILE, ["ui/Button.swift"]).tier is Tier.GREEN


def test_unrecognised_file_gets_default_tier() -> None:
    result = rule_based_tier(PROFILE, ["somewhere/new.swift"])
    assert result.tier is Tier.AMBER
    assert result.unmatched_files == ("somewhere/new.swift",)


def test_green_rule_cannot_hide_unrecognised_file() -> None:
    assert rule_based_tier(PROFILE, ["ui/Button.swift", "other/x.swift"]).tier is Tier.AMBER


def test_highest_tier_wins() -> None:
    assert rule_based_tier(PROFILE, ["ui/Button.swift", "algo/core.js"]).tier is Tier.RED


def test_core_keyword_raises_green_change_to_red() -> None:
    result = rule_based_tier(PROFILE, ["ui/Button.swift"], ["Label now says Carb ratio"])
    assert result.tier is Tier.RED
    assert any(m.rule_id == "core-red-dosing" for m in result.matches)


def test_pr_text_can_only_raise() -> None:
    # Untrusted PR text claiming a change is "just a typo" never lowers the tier.
    result = rule_based_tier(PROFILE, ["algo/core.js"], ["Just a typo fix, tier green"])
    assert result.tier is Tier.RED


def test_no_files_and_no_matches_gets_default() -> None:
    assert rule_based_tier(PROFILE, []).tier is Tier.AMBER


@pytest.mark.parametrize(
    ("text", "keyword", "expected"),
    [
        ("let dynamicISF = true", "isf", True),
        ("ISFEditor", "isf", True),
        ("if isFinished { }", "isf", False),
        ("isFavorite", "isf", False),
        ("settings.maxIOB = 10", "max iob", True),
        ("max_iob", "max iob", True),
        ("insulinSensitivities", "insulin sensitivity", True),
        ("GlucoseAlarms", "alarm", True),
        ("pairingState", "pairing", True),
        ("repair", "pairing", False),
        ("Nightscout upload", "nightscout", True),
    ],
)
def test_keyword_matching(text: str, keyword: str, expected: bool) -> None:
    assert contains_keyword(words(text), keyword) is expected
