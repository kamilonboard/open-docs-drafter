"""Planted-error suite.

Fake pull requests that the tool must catch, every one, on every CI run. A single miss
fails CI and blocks a release of the tool.

Each case in cases/*.yaml names a hazard from hazards.yaml and says what the built layers
must do with it. Checks for layers not built yet are listed under `pending` and show up
as skipped tests with the reason, so gaps stay visible. When a layer is built, add its
check here and move the case's pending entry into `expect`.

Case files are validated strictly: a misspelt expectation is an error, never a silent pass.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

from open_docs_drafter.layers.input_check import check_input
from open_docs_drafter.layers.triage import rule_based_tier
from open_docs_drafter.models import ChangedFile, PullRequest, changed_lines
from open_docs_drafter.profile import Profile, load_profile
from open_docs_drafter.tiers import Tier

HERE = Path(__file__).parent
PROFILES = {"trio": HERE.parent.parent / "profiles" / "trio" / "profile.yaml"}

_CASE_KEYS = {"id", "hazard", "summary", "profile", "pr", "expect"}
_PR_KEYS = {"title", "body", "files"}
_FILE_KEYS = {"path", "patch"}
_EXPECT_KEYS = {"triage", "input_check", "pending"}
_TRIAGE_KEYS = {"min_tier"}
_INPUT_KEYS = {"discarded", "findings_include", "text_excludes", "diff_tier_min"}
_PENDING_KEYS = {"component", "check"}


@dataclass(frozen=True)
class Case:
    id: str
    hazard: str
    summary: str
    profile: str
    pr: PullRequest
    expect: dict[str, Any]
    source: str


def _keys(
    data: Any, allowed: set[str], where: str, required: frozenset[str] | set[str] = frozenset()
) -> None:
    if not isinstance(data, dict):
        raise ValueError(f"{where}: must be a mapping")
    unknown = set(data) - allowed
    missing = set(required) - set(data)
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}")
    if missing:
        raise ValueError(f"{where}: missing keys {sorted(missing)}")


def _tier(value: Any, where: str) -> Tier:
    if not isinstance(value, str) or value.upper() not in Tier.__members__:
        raise ValueError(f"{where}: unknown tier {value!r}")
    return Tier[value.upper()]


def load_hazards() -> dict[str, dict[str, str]]:
    data = yaml.safe_load((HERE / "hazards.yaml").read_text(encoding="utf-8"))
    for hid, h in data.items():
        _keys(h, {"name", "manual"}, f"hazards.yaml {hid}", {"name"})
    return data  # type: ignore[no-any-return]


def load_cases() -> list[Case]:
    hazards = load_hazards()
    cases: list[Case] = []
    seen: set[str] = set()
    for path in sorted((HERE / "cases").glob("*.yaml")):
        for i, raw in enumerate(yaml.safe_load(path.read_text(encoding="utf-8"))):
            where = f"{path.name}[{i}]"
            _keys(raw, _CASE_KEYS, where, {"id", "hazard", "summary", "pr", "expect"})
            where = f"{path.name} {raw['id']}"
            if raw["id"] in seen:
                raise ValueError(f"{where}: duplicate case id")
            seen.add(raw["id"])
            if raw["hazard"] not in hazards:
                raise ValueError(f"{where}: unknown hazard {raw['hazard']!r}")

            pr = raw["pr"]
            _keys(pr, _PR_KEYS, f"{where} pr", _PR_KEYS)
            files = []
            for f in pr["files"]:
                _keys(f, _FILE_KEYS, f"{where} file", _FILE_KEYS)
                files.append(ChangedFile(f["path"], f["patch"]))

            expect = raw["expect"]
            _keys(expect, _EXPECT_KEYS, f"{where} expect")
            if not expect:
                raise ValueError(f"{where}: expect is empty; a case must check something")
            if "triage" in expect:
                _keys(expect["triage"], _TRIAGE_KEYS, f"{where} triage", _TRIAGE_KEYS)
                _tier(expect["triage"]["min_tier"], f"{where} triage")
            if "input_check" in expect:
                ic = expect["input_check"]
                _keys(ic, _INPUT_KEYS, f"{where} input_check")
                if not ic:
                    raise ValueError(f"{where}: input_check is empty")
                if "diff_tier_min" in ic:
                    _tier(ic["diff_tier_min"], f"{where} input_check")
            for p in expect.get("pending", []):
                _keys(p, _PENDING_KEYS, f"{where} pending", _PENDING_KEYS)

            cases.append(
                Case(
                    id=raw["id"],
                    hazard=raw["hazard"],
                    summary=raw["summary"],
                    profile=raw.get("profile", "trio"),
                    pr=PullRequest(0, pr["title"], pr["body"], "", tuple(files)),
                    expect=expect,
                    source=path.name,
                )
            )
    return cases


CASES = load_cases()
_PROFILE_CACHE: dict[str, Profile] = {}


def profile_for(case: Case) -> Profile:
    if case.profile not in _PROFILE_CACHE:
        _PROFILE_CACHE[case.profile] = load_profile(PROFILES[case.profile])
    return _PROFILE_CACHE[case.profile]


def _ids(kind: str) -> list[Any]:
    return [pytest.param(c, id=c.id) for c in CASES if kind in c.expect]


# ------------------------------------------------------------------ built layers


@pytest.mark.parametrize("case", _ids("triage"))
def test_triage(case: Case) -> None:
    pr = case.pr
    texts = [pr.title, pr.body, *(line for f in pr.files for line in changed_lines(f.patch))]
    result = rule_based_tier(profile_for(case), [f.path for f in pr.files], texts)
    want = _tier(case.expect["triage"]["min_tier"], case.id)
    assert result.tier >= want, (
        f"{case.id}: tier {result.tier.name}, needs at least {want.name}. {case.summary}"
    )


@pytest.mark.parametrize("case", _ids("input_check"))
def test_input_check(case: Case) -> None:
    want = case.expect["input_check"]
    result = check_input(profile_for(case), case.pr)
    found = {f.code for f in result.findings}

    if "discarded" in want:
        assert result.discarded is want["discarded"], f"{case.id}: findings {sorted(found)}"
    for code in want.get("findings_include", []):
        assert code in found, f"{case.id}: expected finding {code!r}, got {sorted(found)}"
    for text in want.get("text_excludes", []):
        kept = f"{result.title or ''}\n{result.description or ''}"
        assert text not in kept, f"{case.id}: {text!r} reached later layers"
    if "diff_tier_min" in want:
        assert result.diff_tier >= _tier(want["diff_tier_min"], case.id)


# ------------------------------------------------------------------ layers not built yet


def _pending() -> list[Any]:
    return [
        pytest.param(c, p, id=f"{c.id}::{p['component'].replace(' ', '-')}")
        for c in CASES
        for p in c.expect.get("pending", [])
    ]


@pytest.mark.parametrize(("case", "pending"), _pending())
def test_pending(case: Case, pending: dict[str, str]) -> None:
    pytest.skip(f"PENDING {pending['component']}: {pending['check']}")


# ------------------------------------------------------------------ coverage


def test_every_hazard_is_covered() -> None:
    covered = {c.hazard for c in CASES}
    for hid, hazard in load_hazards().items():
        assert hid in covered or "manual" in hazard, (
            f"{hid} ({hazard['name']}) has no planted-error case and no manual reason"
        )


def test_cases_cover_the_design_doc_list() -> None:
    # The design doc names five kinds of planted error. Keep at least one of each.
    hazards = {c.hazard for c in CASES}
    ids = " ".join(c.id for c in CASES)
    assert "H1" in hazards  # false numbers
    assert "unit-swap" in ids  # unit swaps
    assert "H6" in hazards  # hidden instructions
    assert "H3" in hazards  # silent settings resets
    assert "as-ui-fix" in ids  # algorithm changes disguised as UI fixes
