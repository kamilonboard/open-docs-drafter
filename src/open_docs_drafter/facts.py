"""Facts: exact values extracted from source code, each with its file, line and source text.

A fact is never inferred. If an extractor can't read a value exactly (for example, the
default is a calculation rather than a literal), the fact's value is None and it carries
the reason, which later layers treat as "needs human".
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum


class Kind(StrEnum):
    DEFAULT = "default"  # Default in the settings model (e.g. Preferences.swift)
    JSON_KEY = "json_key"  # Key used in stored and exported JSON
    JSON_DEFAULT = "json_default"  # Default in a bundled JSON defaults file
    PICKER_DEFAULT = "picker_default"  # Default in the settings picker definition
    MIN = "min"
    MAX = "max"
    STEP = "step"
    UNIT = "unit"
    LABEL = "label"  # On-screen label
    HINT_DEFAULT = "hint_default"  # "Default: ..." text shown in the app's help


@dataclass(frozen=True)
class Fact:
    setting: str
    kind: Kind
    value: str | None  # Exactly as written in the source; None means "needs human".
    path: str
    line: int
    source: str  # The source line, stripped.
    unit: str | None = None
    needs_human: str | None = None  # Why the value couldn't be read exactly.

    @property
    def citation(self) -> str:
        return f"{self.path}:{self.line}"

    @property
    def number(self) -> Decimal | None:
        return as_number(self.value)


def as_number(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


@dataclass(frozen=True)
class FactChange:
    setting: str
    kind: Kind
    old: Fact | None  # None: the fact is new.
    new: Fact | None  # None: the fact was removed.

    @property
    def summary(self) -> str:
        old = "absent" if self.old is None else (self.old.value or "unreadable")
        new = "absent" if self.new is None else (self.new.value or "unreadable")
        return f"{self.setting} {self.kind}: {old} -> {new}"


@dataclass(frozen=True)
class Inconsistency:
    setting: str
    message: str
    facts: tuple[Fact, ...]


class FactSet:
    """All facts for a codebase snapshot, indexed by setting and kind.

    JSON defaults are filed under the Swift setting name when a JSON_KEY fact links them.
    """

    def __init__(self, facts: Iterable[Fact]) -> None:
        facts = list(facts)
        aliases = {f.value: f.setting for f in facts if f.kind is Kind.JSON_KEY and f.value}
        self.facts: list[Fact] = []
        for f in facts:
            if f.kind is Kind.JSON_DEFAULT and f.setting in aliases:
                f = Fact(**{**f.__dict__, "setting": aliases[f.setting]})
            self.facts.append(f)
        self._index: dict[tuple[str, Kind], list[Fact]] = {}
        for f in self.facts:
            self._index.setdefault((f.setting, f.kind), []).append(f)

    def get(self, setting: str, kind: Kind) -> list[Fact]:
        return self._index.get((setting, kind), [])

    def one(self, setting: str, kind: Kind) -> Fact | None:
        found = self.get(setting, kind)
        return found[0] if len(found) == 1 else None

    @property
    def settings(self) -> list[str]:
        return sorted({f.setting for f in self.facts})

    @property
    def needing_human(self) -> list[Fact]:
        return [f for f in self.facts if f.value is None]

    def __len__(self) -> int:
        return len(self.facts)


def diff(base: FactSet, head: FactSet) -> list[FactChange]:
    """Facts that were added, removed or changed value between two snapshots."""
    changes: list[FactChange] = []
    keys = sorted(set(base._index) | set(head._index))
    for setting, kind in keys:
        old = base.get(setting, kind)
        new = head.get(setting, kind)
        old_values = sorted(f.value or "" for f in old)
        new_values = sorted(f.value or "" for f in new)
        if old_values == new_values and len(old) == len(new):
            continue
        changes.append(FactChange(setting, kind, old[0] if old else None, new[0] if new else None))
    return changes


def inconsistencies(facts: FactSet) -> list[Inconsistency]:
    """Places where the code disagrees with itself about a setting.

    Compares the model default, the JSON default and the picker default, and checks the
    "Default: ..." hint against them. Factors shown as a percentage (3 -> 300%) count as
    equal. Any disagreement means the docs can't simply copy one of them.
    """
    found: list[Inconsistency] = []
    for setting in facts.settings:
        defaults = [
            f
            for kind in (Kind.DEFAULT, Kind.JSON_DEFAULT, Kind.PICKER_DEFAULT)
            for f in facts.get(setting, kind)
            if f.number is not None
        ]
        if len({f.number for f in defaults}) > 1:
            values = ", ".join(f"{f.kind} {f.value} ({f.citation})" for f in defaults)
            found.append(Inconsistency(setting, f"defaults disagree: {values}", tuple(defaults)))
        reference = next((f for f in defaults), None)
        for hint in facts.get(setting, Kind.HINT_DEFAULT):
            if reference is None or reference.number is None:
                continue
            shown = _hint_number(hint.value)
            if shown is None:
                continue
            if shown not in {reference.number, reference.number * 100}:
                found.append(
                    Inconsistency(
                        setting,
                        f"help text says {hint.value!r} ({hint.citation}) but the "
                        f"{reference.kind} is {reference.value} ({reference.citation})",
                        (hint, reference),
                    )
                )
    return found


def _hint_number(text: str | None) -> Decimal | None:
    if not text:
        return None
    digits = ""
    for ch in text:
        if ch.isdigit() or (ch in ".," and digits):
            digits += "." if ch == "," else ch
        elif digits:
            break
    return as_number(digits.rstrip(".")) if digits else None
