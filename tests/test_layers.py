"""Guards the design: layers 1, 3, 5 and 7 must stay plain code with no AI model."""

import importlib

import pytest

DETERMINISTIC = ["input_check", "fact_extraction", "citation_check", "edit_constraints"]
ALL_LAYERS = DETERMINISTIC + ["triage", "drafting", "verifier"]


@pytest.mark.parametrize("name", DETERMINISTIC)
def test_deterministic_layers_use_no_ai(name: str) -> None:
    module = importlib.import_module(f"open_docs_drafter.layers.{name}")
    assert module.AI_INVOLVED is False


def test_layers_are_numbered_1_to_7() -> None:
    numbers = sorted(
        importlib.import_module(f"open_docs_drafter.layers.{n}").LAYER for n in ALL_LAYERS
    )
    assert numbers == list(range(1, 8))
