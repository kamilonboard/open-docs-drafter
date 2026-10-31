"""Risk tiers.

Core rule: any signal can raise a tier; only a named human can lower one.
Project profiles may add triggers but cannot change this behaviour.
"""

from enum import IntEnum


class Tier(IntEnum):
    GREEN = 1  # Drafts; one human approves.
    AMBER = 2  # Drafts, then escalates; code author + docs maintainer approve.
    RED = 3  # No AI-written text; evidence pack for an experienced human.


def raise_tier(current: Tier, signal: Tier) -> Tier:
    """Combine a new signal with the current tier. The result is never lower."""
    return max(current, signal)


def human_lower_tier(current: Tier, target: Tier, *, approved_by: str) -> Tier:
    """Lower a tier. Only allowed with a named human approver."""
    if not approved_by.strip():
        raise PermissionError("Lowering a tier requires a named human approver.")
    if target >= current:
        raise ValueError(f"{target.name} is not lower than {current.name}.")
    return target
