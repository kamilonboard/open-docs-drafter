"""Core tier triggers that apply to every project.

A project profile adds its own rules on top of these. It cannot remove, rename or
lower them: there is no profile key that refers to core rules at all.
"""

from dataclasses import dataclass, field

from open_docs_drafter.tiers import Tier

# A change that no rule recognises is never treated as green.
MIN_DEFAULT_TIER = Tier.AMBER


@dataclass(frozen=True)
class Rule:
    """A tier trigger.

    `paths` are fnmatch patterns matched against each changed file; `*` also matches `/`.
    `keywords` are matched word by word against the diff and pull request text, after
    splitting camelCase and snake_case, so "max iob" matches `maxIOB` but "isf" does not
    match `isFinished`. The last word may be a prefix ("alarm" matches `alarms`).
    """

    id: str
    tier: Tier
    reason: str
    paths: tuple[str, ...] = field(default=())
    keywords: tuple[str, ...] = field(default=())


CORE_RULES: tuple[Rule, ...] = (
    Rule(
        id="core-red-dosing",
        tier=Tier.RED,
        reason="Dosing algorithm or insulin, carb or sensitivity maths",
        keywords=(
            "insulin sensitivity",
            "carb ratio",
            "dosing",
            "max iob",
            "max bolus",
            "max basal",
        ),
    ),
    Rule(
        id="core-red-safety-limits",
        tier=Tier.RED,
        reason="Safety limits",
        keywords=("safety limit", "safety threshold", "low glucose suspend"),
    ),
    Rule(
        id="core-red-settings-reset",
        tier=Tier.RED,
        reason="Settings resets or migrations",
        keywords=(
            "settings reset",
            "reset settings",
            "preferences reset",
            "reset preferences",
            "reset to default",
            "settings migration",
        ),
    ),
    Rule(
        id="core-red-alarms",
        tier=Tier.RED,
        reason="Alarm behaviour",
        keywords=("alarm", "urgent low"),
    ),
    Rule(
        id="core-amber-devices",
        tier=Tier.AMBER,
        reason="Device setup and pairing",
        keywords=("pairing", "unpair"),
    ),
    Rule(
        id="core-amber-sync",
        tier=Tier.AMBER,
        reason="Data sync and remote monitoring",
        keywords=("nightscout", "remote control", "remote bolus"),
    ),
)
