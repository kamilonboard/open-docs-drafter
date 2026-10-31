import copy
from typing import Any

import pytest

from open_docs_drafter.core_rules import CORE_RULES
from open_docs_drafter.profile import ProfileError, parse_profile
from open_docs_drafter.tiers import Tier

BASE: dict[str, Any] = {
    "profile_version": 1,
    "project": {
        "name": "Example",
        "code_repo": "org/app",
        "docs_repo": "org/docs",
        "docs_branch": "main",
        "docs_format": "mkdocs",
    },
    "rules": [{"id": "ex-green-ui", "tier": "green", "reason": "UI", "paths": ["ui/*"]}],
}


def make(**changes: Any) -> dict[str, Any]:
    data = copy.deepcopy(BASE)
    data.update(changes)
    return data


def test_valid_profile_loads() -> None:
    profile = parse_profile(make())
    assert profile.project.name == "Example"
    assert profile.default_tier is Tier.AMBER
    assert profile.status == "draft"


def test_core_rules_always_included() -> None:
    profile = parse_profile(make(rules=[]))
    assert profile.all_rules[: len(CORE_RULES)] == CORE_RULES


@pytest.mark.parametrize(
    "extra",
    [
        {"core_rules": {"draft_only": False}},
        {"disable_core_rules": True},
        {"allow_red_drafting": True},
    ],
)
def test_no_key_can_switch_off_core_rules(extra: dict[str, Any]) -> None:
    with pytest.raises(ProfileError, match="unknown keys"):
        parse_profile(make(**extra))


def test_default_tier_cannot_be_green() -> None:
    with pytest.raises(ProfileError, match="never green"):
        parse_profile(make(default_tier="green"))


def test_default_tier_can_be_red() -> None:
    assert parse_profile(make(default_tier="red")).default_tier is Tier.RED


def test_rule_cannot_reuse_core_id() -> None:
    rule = {"id": CORE_RULES[0].id, "tier": "green", "reason": "x", "keywords": ["x"]}
    with pytest.raises(ProfileError, match="core id"):
        parse_profile(make(rules=[rule]))


def test_duplicate_rule_ids_rejected() -> None:
    rule = BASE["rules"][0]
    with pytest.raises(ProfileError, match="duplicated"):
        parse_profile(make(rules=[rule, rule]))


@pytest.mark.parametrize(
    ("rule", "message"),
    [
        ({"id": "r", "tier": "purple", "reason": "x", "paths": ["a"]}, "tier"),
        ({"id": "r", "tier": "red", "reason": "x"}, "at least one path or keyword"),
        ({"id": "r", "tier": "red", "reason": "", "paths": ["a"]}, "reason"),
        ({"id": "r", "tier": "red", "reason": "x", "paths": "a/*"}, "must be a list"),
        ({"id": "r", "tier": "red", "reason": "x", "paths": ["a"], "lower_to": "green"}, "unknown"),
    ],
)
def test_bad_rules_rejected(rule: dict[str, Any], message: str) -> None:
    with pytest.raises(ProfileError, match=message):
        parse_profile(make(rules=[rule]))


def test_unknown_docs_format_rejected() -> None:
    data = make()
    data["project"]["docs_format"] = "sphinx"
    with pytest.raises(ProfileError, match="docs_format"):
        parse_profile(data)


def test_unsupported_version_rejected() -> None:
    with pytest.raises(ProfileError, match="profile_version"):
        parse_profile(make(profile_version=2))
