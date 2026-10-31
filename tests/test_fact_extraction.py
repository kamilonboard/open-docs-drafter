from pathlib import Path

import pytest

from open_docs_drafter.extractors import json_defaults, swift, trio
from open_docs_drafter.extractors.swift_scan import literal, render_string, string_literal
from open_docs_drafter.facts import Fact, FactSet, Kind, diff, inconsistencies
from open_docs_drafter.layers.fact_extraction import extract_facts, fact_changes, fact_paths
from open_docs_drafter.profile import ProfileError, load_profile, parse_profile

FIXTURES = Path(__file__).parent / "fixtures" / "trio"
TRIO = load_profile(Path(__file__).parent.parent / "profiles" / "trio" / "profile.yaml")

# Fixture files under the paths they have in the Trio repository.
LAYOUT = {
    "Trio/Sources/Models/Preferences.swift": "Preferences.swift",
    "Trio/Resources/json/defaults/preferences.json": "preferences.json",
    "Trio/Resources/json/defaults/settings/settings.json": "settings.json",
    "Trio/Sources/Models/DecimalPickerSettings.swift": "DecimalPickerSettings.swift",
    "Trio/Sources/Modules/SMBSettings/View/SMBSettingsRootView.swift": (
        "Modules/SMBSettings/View/SMBSettingsRootView.swift"
    ),
    "Trio/Sources/Modules/GeneralSettings/View/UnitsLimitsSettingsRootView.swift": (
        "Modules/GeneralSettings/View/UnitsLimitsSettingsRootView.swift"
    ),
}


def files() -> dict[str, str]:
    return {repo: (FIXTURES / local).read_text() for repo, local in LAYOUT.items()}


@pytest.fixture(scope="module")
def facts() -> FactSet:
    return extract_facts(TRIO, files())


def values(fs: FactSet, setting: str, kind: Kind) -> list[str | None]:
    return [f.value for f in fs.get(setting, kind)]


# ------------------------------------------------------------------ swift scanning


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("30", "30"),
        ("0.05,", "0.05"),
        ("-1", "-1"),
        ("true", "true"),
        ('"rapid-acting"', "rapid-acting"),
        (".rapidActing", ".rapidActing"),
        ("30 // minutes", "30"),
        ("maxIOB * 2", None),
        ("Preferences()", None),
        ("someValue", None),
    ],
)
def test_literal(raw: str, expected: str | None) -> None:
    assert literal(raw) == expected


def test_render_localized_interpolation() -> None:
    line = 'Text("Default: 2 \\(String(localized: "U/hr", comment: "abbr"))")'
    raw, _ = string_literal(line, line.index('"'))  # type: ignore[misc]
    assert render_string(raw) == ("Default: 2 U/hr", None)


def test_render_runtime_interpolation_needs_human() -> None:
    raw = 'Default: \\(units == .mgdL ? "160" : x) \\(units.rawValue)'
    shown, problem = render_string(raw)
    assert problem is not None and "runtime value" in problem
    assert shown == raw


# ------------------------------------------------------------------ extractors


def test_struct_defaults_are_exact_and_cited() -> None:
    text = (FIXTURES / "Preferences.swift").read_text()
    by_name = {f.setting: f for f in swift.struct_defaults("P.swift", text)}
    assert by_name["maxSMBBasalMinutes"].value == "30"
    assert by_name["maxSMBBasalMinutes"].line == 5
    assert by_name["maxSMBBasalMinutes"].source == (
        "var maxSMBBasalMinutes: Decimal = 30 // minutes of basal"
    )
    assert by_name["curve"].value == ".rapidActing"
    assert "timestamp" not in by_name  # no default, so no fact


def test_non_literal_default_needs_human() -> None:
    text = (FIXTURES / "Preferences.swift").read_text()
    fact = next(f for f in swift.struct_defaults("P.swift", text) if f.setting == "computedLimit")
    assert fact.value is None
    assert fact.needs_human is not None and "maxIOB * 2" in fact.needs_human


def test_coding_keys() -> None:
    text = (FIXTURES / "Preferences.swift").read_text()
    keys = {f.setting: f.value for f in swift.coding_keys("P.swift", text)}
    assert keys["maxIOB"] == "max_iob"
    assert keys["maxSMBBasalMinutes"] == "maxSMBBasalMinutes"  # bare case
    assert keys["smbInterval"] == "SMBInterval"
    assert keys["computedLimit"] == "computedLimit" and keys["timestamp"] == "timestamp"


def test_json_defaults_keep_numbers_as_written() -> None:
    text = '{\n  "a" : 1.0,\n  "b" : true,\n  "c" : "x"\n}'
    facts = {f.setting: f for f in json_defaults.extract("d.json", text)}
    assert facts["a"].value == "1.0" and facts["a"].line == 2
    assert facts["b"].value == "true"
    assert facts["c"].value == "x"


def test_broken_json_needs_human() -> None:
    [fact] = json_defaults.extract("d.json", "{ broken")
    assert fact.value is None and fact.needs_human


def test_picker_settings_single_and_multi_line() -> None:
    text = (FIXTURES / "DecimalPickerSettings.swift").read_text()
    facts = trio.picker_settings("D.swift", text)
    smb = {f.kind: f for f in facts if f.setting == "maxSMBBasalMinutes"}
    assert (smb[Kind.MIN].value, smb[Kind.MAX].value, smb[Kind.STEP].value) == ("15", "180", "5")
    assert smb[Kind.UNIT].value == "min"
    basal = {f.kind: f for f in facts if f.setting == "maxBasal"}
    assert basal[Kind.PICKER_DEFAULT].value == "10" and basal[Kind.PICKER_DEFAULT].line == 8
    assert basal[Kind.MAX].line == 11
    assert basal[Kind.UNIT].value == "U/h"
    safety = {f.kind: f for f in facts if f.setting == "maxDailySafetyMultiplier"}
    assert safety[Kind.MAX].value == "5"  # trailing comment ignored


def test_setting_views_labels_and_hints() -> None:
    path = "Modules/SMBSettings/View/SMBSettingsRootView.swift"
    facts = trio.setting_views(path, (FIXTURES / path).read_text())
    got = {(f.setting, f.kind): f.value for f in facts}
    assert got[("enableSMBAlways", Kind.LABEL)] == "Enable SMB Always"  # from booleanValue
    assert got[("enableSMBAlways", Kind.HINT_DEFAULT)] == "Default: OFF"
    assert got[("maxSMBBasalMinutes", Kind.LABEL)] == "Max SMB Basal Minutes"
    assert got[("maxSMBBasalMinutes", Kind.HINT_DEFAULT)] == "Default: 30 minutes"


def test_hint_line_is_the_string_line() -> None:
    path = "Modules/GeneralSettings/View/UnitsLimitsSettingsRootView.swift"
    text = (FIXTURES / path).read_text()
    hint = next(
        f
        for f in trio.setting_views(path, text)
        if f.setting == "halfBasalExerciseTarget" and f.kind is Kind.HINT_DEFAULT
    )
    assert text.splitlines()[hint.line - 1].strip().startswith('"Default:')
    assert hint.value is None and hint.needs_human


# ------------------------------------------------------------------ the layer on Trio's layout


def test_fact_paths_match_trio_layout() -> None:
    all_paths = [*LAYOUT, "Trio/Sources/Models/Other.swift", "README.md"]
    assert fact_paths(TRIO, all_paths) == sorted(LAYOUT)


def test_json_defaults_are_filed_under_swift_names(facts: FactSet) -> None:
    assert values(facts, "maxIOB", Kind.JSON_DEFAULT) == ["0"]
    assert values(facts, "smbInterval", Kind.JSON_DEFAULT) == ["3"]


def test_full_setting_record(facts: FactSet) -> None:
    s = "maxSMBBasalMinutes"
    assert values(facts, s, Kind.DEFAULT) == ["30"]
    assert values(facts, s, Kind.JSON_DEFAULT) == ["30"]
    assert values(facts, s, Kind.PICKER_DEFAULT) == ["30"]
    assert values(facts, s, Kind.UNIT) == ["min"]
    assert values(facts, s, Kind.LABEL) == ["Max SMB Basal Minutes"]
    for f in facts.facts:
        assert f.path in LAYOUT and f.line >= 1  # every fact is cited


def test_needing_human(facts: FactSet) -> None:
    assert {f.setting for f in facts.needing_human} == {"computedLimit", "halfBasalExerciseTarget"}


def test_inconsistencies(facts: FactSet) -> None:
    found = {i.setting: i.message for i in inconsistencies(facts)}
    # Real Trio case: settings.json says 2, the picker says 10.
    assert "maxBasal" in found and "json_default 2" in found["maxBasal"]
    # Planted: help text says 5 min, code default is 3.
    assert "smbInterval" in found and "Default: 5 min" in found["smbInterval"]
    # 300% matches a factor of 3; 30 minutes matches 30. Not flagged.
    assert "maxDailySafetyMultiplier" not in found
    assert "maxSMBBasalMinutes" not in found
    assert set(found) == {"maxBasal", "smbInterval"}


def test_fact_changes_between_snapshots() -> None:
    base = files()
    head = dict(base)
    key = "Trio/Sources/Models/DecimalPickerSettings.swift"
    head[key] = head[key].replace("min: 15, max: 180", "min: 15, max: 240")
    changes = fact_changes(TRIO, base, head)
    assert [(c.setting, c.kind, c.old.value, c.new.value) for c in changes] == [  # type: ignore[union-attr]
        ("maxSMBBasalMinutes", Kind.MAX, "180", "240")
    ]
    assert changes[0].new is not None and changes[0].new.citation.endswith(":5")


def test_no_changes_when_identical() -> None:
    assert fact_changes(TRIO, files(), files()) == []


def test_added_and_removed_facts() -> None:
    a = Fact("x", Kind.DEFAULT, "1", "p", 1, "var x = 1")
    b = Fact("y", Kind.DEFAULT, "2", "p", 2, "var y = 2")
    changes = diff(FactSet([a]), FactSet([b]))
    assert [(c.setting, c.old is None, c.new is None) for c in changes] == [
        ("x", False, True),
        ("y", True, False),
    ]


# ------------------------------------------------------------------ profile


def test_profile_rejects_unknown_extractor() -> None:
    data = {
        "profile_version": 1,
        "project": {
            "name": "X",
            "code_repo": "a/b",
            "docs_repo": "a/c",
            "docs_branch": "main",
            "docs_format": "mkdocs",
        },
        "facts": [{"extractor": "guess_with_ai", "paths": ["*.swift"]}],
    }
    with pytest.raises(ProfileError, match="extractor"):
        parse_profile(data)


def test_trio_profile_has_facts() -> None:
    assert {s.extractor for s in TRIO.facts} == {
        "swift_struct_defaults",
        "swift_coding_keys",
        "json_defaults",
        "trio_picker_settings",
        "trio_setting_views",
    }
