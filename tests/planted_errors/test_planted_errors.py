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

from open_docs_drafter.facts import Kind, inconsistencies
from open_docs_drafter.layers.fact_extraction import extract_facts, fact_changes
from open_docs_drafter.layers.input_check import check_input
from open_docs_drafter.layers.triage import rule_based_tier
from open_docs_drafter.models import ChangedFile, PullRequest, changed_lines
from open_docs_drafter.profile import Profile, load_profile
from open_docs_drafter.tiers import Tier

HERE = Path(__file__).parent
PROFILES = {"trio": HERE.parent.parent / "profiles" / "trio" / "profile.yaml"}

_CASE_KEYS = {"id", "hazard", "summary", "profile", "pr", "snapshot", "base_snapshot", "expect"}
_PR_KEYS = {"title", "body", "files"}
_FILE_KEYS = {"path", "patch"}
_EXPECT_KEYS = {"triage", "input_check", "facts", "pending"}
_FACTS_KEYS = {"inconsistent", "consistent", "needs_human", "values", "changes"}
_CHANGE_KEYS = {"setting", "kind", "old", "new"}
_TRIAGE_KEYS = {"min_tier"}
_INPUT_KEYS = {"discarded", "findings_include", "text_excludes", "diff_tier_min"}
_PENDING_KEYS = {"component", "check"}


@dataclass(frozen=True)
class Case:
    id: str
    hazard: str
    summary: str
    profile: str
    pr: PullRequest | None
    snapshot: dict[str, str] | None  # Whole files (path -> text) for fact extraction.
    base_snapshot: dict[str, str] | None  # The same files before the change.
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
            _keys(raw, _CASE_KEYS, where, {"id", "hazard", "summary", "expect"})
            where = f"{path.name} {raw['id']}"
            if raw["id"] in seen:
                raise ValueError(f"{where}: duplicate case id")
            seen.add(raw["id"])
            if raw["hazard"] not in hazards:
                raise ValueError(f"{where}: unknown hazard {raw['hazard']!r}")

            pr = None
            if "pr" in raw:
                _keys(raw["pr"], _PR_KEYS, f"{where} pr", _PR_KEYS)
                files = []
                for f in raw["pr"]["files"]:
                    _keys(f, _FILE_KEYS, f"{where} file", _FILE_KEYS)
                    files.append(ChangedFile(f["path"], f["patch"]))
                pr = PullRequest(0, raw["pr"]["title"], raw["pr"]["body"], "", tuple(files))
            for snap in ("snapshot", "base_snapshot"):
                if snap in raw and not (
                    isinstance(raw[snap], dict)
                    and all(isinstance(v, str) for v in raw[snap].values())
                ):
                    raise ValueError(f"{where}: {snap} must map paths to file text")

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
            if ("triage" in expect or "input_check" in expect) and pr is None:
                raise ValueError(f"{where}: triage and input_check checks need a `pr`")
            if "facts" in expect:
                fx = expect["facts"]
                _keys(fx, _FACTS_KEYS, f"{where} facts")
                if not fx:
                    raise ValueError(f"{where}: facts is empty")
                if "snapshot" not in raw:
                    raise ValueError(f"{where}: facts checks need a `snapshot`")
                if "changes" in fx and "base_snapshot" not in raw:
                    raise ValueError(f"{where}: facts.changes needs a `base_snapshot`")
                for c in fx.get("changes", []):
                    _keys(c, _CHANGE_KEYS, f"{where} facts.changes", _CHANGE_KEYS)
                for key in fx.get("values", {}):
                    setting, _, kind = key.partition(".")
                    if not setting or kind not in {k.value for k in Kind}:
                        raise ValueError(f"{where}: facts.values key {key!r} is not setting.kind")
            for p in expect.get("pending", []):
                _keys(p, _PENDING_KEYS, f"{where} pending", _PENDING_KEYS)

            cases.append(
                Case(
                    id=raw["id"],
                    hazard=raw["hazard"],
                    summary=raw["summary"],
                    profile=raw.get("profile", "trio"),
                    pr=pr,
                    snapshot=raw.get("snapshot"),
                    base_snapshot=raw.get("base_snapshot"),
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
    assert pr is not None
    texts = [pr.title, pr.body, *(line for f in pr.files for line in changed_lines(f.patch))]
    result = rule_based_tier(profile_for(case), [f.path for f in pr.files], texts)
    want = _tier(case.expect["triage"]["min_tier"], case.id)
    assert result.tier >= want, (
        f"{case.id}: tier {result.tier.name}, needs at least {want.name}. {case.summary}"
    )


@pytest.mark.parametrize("case", _ids("input_check"))
def test_input_check(case: Case) -> None:
    want = case.expect["input_check"]
    assert case.pr is not None
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


@pytest.mark.parametrize("case", _ids("facts"))
def test_facts(case: Case) -> None:
    assert case.snapshot is not None
    want = case.expect["facts"]
    profile = profile_for(case)
    facts = extract_facts(profile, case.snapshot)
    flagged = {i.setting for i in inconsistencies(facts)}
    unreadable = {f.setting for f in facts.needing_human}

    for setting in want.get("inconsistent", []):
        assert setting in flagged, f"{case.id}: {setting} not flagged; flagged {sorted(flagged)}"
    for setting in want.get("consistent", []):
        assert setting not in flagged, f"{case.id}: {setting} wrongly flagged"
    for setting in want.get("needs_human", []):
        assert setting in unreadable, f"{case.id}: {setting} should need a human"
        for f in facts.facts:
            if f.setting == setting and f.value is None:
                assert f.needs_human, f"{case.id}: unreadable fact without a reason"
    for key, expected in want.get("values", {}).items():
        setting, _, kind = key.partition(".")
        got = [f.value for f in facts.get(setting, Kind(kind))]
        assert got == [str(expected)], f"{case.id}: {key} is {got}, expected {expected!r}"
    if "changes" in want:
        assert case.base_snapshot is not None
        got_changes = [
            {
                "setting": c.setting,
                "kind": c.kind.value,
                "old": c.old.value if c.old else None,
                "new": c.new.value if c.new else None,
            }
            for c in fact_changes(profile, case.base_snapshot, case.snapshot)
        ]
        expected_changes = [
            {k: (str(v) if v is not None else None) for k, v in c.items()} for c in want["changes"]
        ]
        assert got_changes == expected_changes, f"{case.id}: changes {got_changes}"


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
