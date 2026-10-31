"""The Trio profile loads and puts real Trio paths in the expected tiers."""

from pathlib import Path

import pytest

from open_docs_drafter.layers.triage import rule_based_tier
from open_docs_drafter.profile import load_profile
from open_docs_drafter.tiers import Tier

TRIO = load_profile(Path(__file__).parent.parent / "profiles" / "trio" / "profile.yaml")


def test_trio_profile_is_still_a_draft() -> None:
    # Flip to "confirmed" only after Trio's maintainers agree the rules.
    assert TRIO.status == "draft"
    assert TRIO.project.docs_repo == "nightscout/trio-docs"


@pytest.mark.parametrize(
    ("path", "tier"),
    [
        # Red: algorithm, dosing, therapy settings, defaults, migrations, alarms
        ("trio-oref/lib/determine-basal/determine-basal.js", Tier.RED),
        ("Trio/Sources/APS/OpenAPSSwift/DetermineBasal/DosingEngine.swift", Tier.RED),
        ("Trio/Sources/Services/BolusCalculator/BolusCalculator.swift", Tier.RED),
        ("Trio/Sources/Modules/ISFEditor/View/ISFEditorRootView.swift", Tier.RED),
        ("Trio/Sources/Modules/Treatments/View/TreatmentsRootView.swift", Tier.RED),
        ("Trio/Resources/json/defaults/preferences.json", Tier.RED),
        ("Trio/Sources/Modules/Main/View/MainMigrationErrorView.swift", Tier.RED),
        ("Trio/Sources/Services/Alerts/GlucoseAlerts.swift", Tier.RED),
        ("LoopAlgorithm", Tier.RED),
        # Amber: devices, sync, watch, build
        ("Trio/Sources/Modules/PumpConfig/View/PumpConfigRootView.swift", Tier.AMBER),
        ("OmnipodKit", Tier.AMBER),
        ("Trio/Sources/Services/Network/NightscoutAPI.swift", Tier.AMBER),
        ("Trio Watch App Extension/Views/BolusView.swift", Tier.AMBER),
        (".github/workflows/build_trio.yml", Tier.AMBER),
        ("Config.xcconfig", Tier.AMBER),
        # Green: UI, strings, docs, tests
        ("Trio/Sources/Modules/UserInterfaceSettings/View/UIView.swift", Tier.GREEN),
        ("Trio/Sources/Localizations/Main/Localizable.xcstrings", Tier.GREEN),
        ("README.md", Tier.GREEN),
        ("TrioTests/CoreDataTests/GlucoseStorageTests.swift", Tier.GREEN),
    ],
)
def test_trio_paths(path: str, tier: Tier) -> None:
    assert rule_based_tier(TRIO, [path]).tier is tier


def test_unlisted_trio_path_is_amber() -> None:
    assert rule_based_tier(TRIO, ["Trio/Sources/Modules/Stat/StatView.swift"]).tier is Tier.AMBER


def test_migration_test_counts_as_red() -> None:
    # Test-only changes are green, but a migration test hints at a settings change.
    assert rule_based_tier(TRIO, ["TrioTests/DosingModeMigrationTests.swift"]).tier is Tier.RED


def test_ui_change_mentioning_smb_is_red() -> None:
    result = rule_based_tier(
        TRIO, ["Trio/Sources/Views/Toggle.swift"], ['+ Text("Enable SMB always")']
    )
    assert result.tier is Tier.RED


def test_core_data_schema_is_red_but_helpers_are_not() -> None:
    schema = (
        "Model/TrioCoreDataPersistentContainer.xcdatamodeld/"
        "TrioCoreDataPersistentContainer.xcdatamodel/contents"
    )
    assert rule_based_tier(TRIO, [schema]).tier is Tier.RED
    assert rule_based_tier(TRIO, ["Model/Helper/NSPredicates.swift"]).tier is Tier.AMBER
