"""Project profiles: per-project settings and extra tier rules, loaded from YAML.

Validation is strict. Unknown keys are rejected, so a profile cannot carry a switch
that the core would quietly ignore, and there is no key for turning core rules off.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from open_docs_drafter.core_rules import CORE_RULES, MIN_DEFAULT_TIER, Rule
from open_docs_drafter.tiers import Tier

SUPPORTED_PROFILE_VERSIONS = {1}
DOCS_FORMATS = {"mkdocs"}

_TOP_KEYS = {"profile_version", "project", "status", "default_tier", "rules"}
_PROJECT_KEYS = {"name", "code_repo", "docs_repo", "docs_branch", "docs_format"}
_RULE_KEYS = {"id", "tier", "reason", "paths", "keywords"}
_STATUSES = {"draft", "confirmed"}


class ProfileError(ValueError):
    """The profile file is invalid. The message says where and why."""


@dataclass(frozen=True)
class Project:
    name: str
    code_repo: str
    docs_repo: str
    docs_branch: str
    docs_format: str


@dataclass(frozen=True)
class Profile:
    project: Project
    status: str
    default_tier: Tier
    rules: tuple[Rule, ...]

    @property
    def all_rules(self) -> tuple[Rule, ...]:
        """Core rules first, then the profile's own. Core rules always apply."""
        return CORE_RULES + self.rules


def load_profile(path: str | Path) -> Profile:
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ProfileError(f"{path}: not valid YAML: {exc}") from exc
    return parse_profile(data, source=str(path))


def parse_profile(data: Any, *, source: str = "profile") -> Profile:
    top = _mapping(data, source, _TOP_KEYS)

    version = top.get("profile_version")
    if version not in SUPPORTED_PROFILE_VERSIONS:
        raise ProfileError(
            f"{source}: profile_version must be one of {sorted(SUPPORTED_PROFILE_VERSIONS)}"
        )

    project = _parse_project(top.get("project"), f"{source}: project")

    status = top.get("status", "draft")
    if status not in _STATUSES:
        raise ProfileError(f"{source}: status must be one of {sorted(_STATUSES)}")

    default_tier = _parse_tier(
        top.get("default_tier", MIN_DEFAULT_TIER.name), f"{source}: default_tier"
    )
    if default_tier < MIN_DEFAULT_TIER:
        raise ProfileError(
            f"{source}: default_tier cannot be below {MIN_DEFAULT_TIER.name.lower()}; "
            "an unrecognised change is never green"
        )

    raw_rules = top.get("rules", [])
    if not isinstance(raw_rules, list):
        raise ProfileError(f"{source}: rules must be a list")
    rules = tuple(_parse_rule(r, f"{source}: rules[{i}]") for i, r in enumerate(raw_rules))

    seen = {r.id for r in CORE_RULES}
    for rule in rules:
        if rule.id in seen:
            raise ProfileError(f"{source}: rule id {rule.id!r} is duplicated or reuses a core id")
        seen.add(rule.id)

    return Profile(project=project, status=status, default_tier=default_tier, rules=rules)


def _parse_project(data: Any, where: str) -> Project:
    raw = _mapping(data, where, _PROJECT_KEYS)
    values = {key: _string(raw.get(key), f"{where}.{key}") for key in _PROJECT_KEYS}
    if values["docs_format"] not in DOCS_FORMATS:
        raise ProfileError(f"{where}.docs_format must be one of {sorted(DOCS_FORMATS)}")
    return Project(**values)


def _parse_rule(data: Any, where: str) -> Rule:
    raw = _mapping(data, where, _RULE_KEYS)
    paths = _string_list(raw.get("paths", []), f"{where}.paths")
    keywords = _string_list(raw.get("keywords", []), f"{where}.keywords")
    if not paths and not keywords:
        raise ProfileError(f"{where}: a rule needs at least one path or keyword")
    return Rule(
        id=_string(raw.get("id"), f"{where}.id"),
        tier=_parse_tier(raw.get("tier"), f"{where}.tier"),
        reason=_string(raw.get("reason"), f"{where}.reason"),
        paths=paths,
        keywords=tuple(k.lower() for k in keywords),
    )


def _parse_tier(value: Any, where: str) -> Tier:
    names = [t.name.lower() for t in Tier]
    if not isinstance(value, str) or value.lower() not in names:
        raise ProfileError(f"{where} must be one of {names}")
    return Tier[value.upper()]


def _mapping(value: Any, where: str, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProfileError(f"{where} must be a mapping")
    unknown = set(value) - allowed
    if unknown:
        raise ProfileError(f"{where}: unknown keys {sorted(map(str, unknown))}")
    return value


def _string(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileError(f"{where} must be a non-empty string")
    return value.strip()


def _string_list(value: Any, where: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ProfileError(f"{where} must be a list")
    return tuple(_string(v, f"{where}[{i}]") for i, v in enumerate(value))
