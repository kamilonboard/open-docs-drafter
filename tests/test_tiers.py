import pytest

from open_docs_drafter.tiers import Tier, human_lower_tier, raise_tier


@pytest.mark.parametrize("current", list(Tier))
@pytest.mark.parametrize("signal", list(Tier))
def test_raise_never_lowers(current: Tier, signal: Tier) -> None:
    result = raise_tier(current, signal)
    assert result >= current
    assert result >= signal


def test_lowering_needs_named_human() -> None:
    with pytest.raises(PermissionError):
        human_lower_tier(Tier.RED, Tier.AMBER, approved_by="  ")


def test_lowering_must_go_down() -> None:
    with pytest.raises(ValueError):
        human_lower_tier(Tier.AMBER, Tier.RED, approved_by="maintainer")


def test_human_can_lower() -> None:
    assert human_lower_tier(Tier.AMBER, Tier.GREEN, approved_by="maintainer") is Tier.GREEN
