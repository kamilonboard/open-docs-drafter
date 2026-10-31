"""The structured draft format that the drafting layer (4) must produce.

Everything a draft would add to the docs is a claim. Each claim cites its evidence:
lines in the pull request's diff, or facts extracted from the code (layer 3). Numbers,
units and setting names enter a claim only through placeholders that point at facts:

    "{{fact:maxSMBBasalMinutes.label}} now goes up to {{fact:maxSMBBasalMinutes.max}}."

Placeholders are filled from the facts by code, never by the model.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Side(StrEnum):
    NEW = "new"  # A line in the changed file after the PR (added or unchanged context).
    OLD = "old"  # A line before the PR (removed or unchanged context).


@dataclass(frozen=True)
class DiffCitation:
    path: str
    line: int
    side: Side
    quote: str  # Text that must appear on that line.


@dataclass(frozen=True)
class FactCitation:
    setting: str
    kind: str


Citation = DiffCitation | FactCitation


@dataclass(frozen=True)
class Claim:
    text: str
    citations: tuple[Citation, ...] = field(default=())


@dataclass(frozen=True)
class DocEdit:
    doc_path: str  # File in the docs repository.
    claims: tuple[Claim, ...]


@dataclass(frozen=True)
class Draft:
    edits: tuple[DocEdit, ...]

    @property
    def claims(self) -> list[Claim]:
        return [c for e in self.edits for c in e.claims]


class DraftFormatError(ValueError):
    pass


def parse_draft(data: Any) -> Draft:
    """Parse a draft from JSON/YAML data. Strict: unknown keys are errors."""
    top = _mapping(data, {"edits"}, "draft")
    edits = []
    for i, e in enumerate(_list(top.get("edits"), "draft.edits")):
        where = f"edits[{i}]"
        raw = _mapping(e, {"doc_path", "claims"}, where)
        claims = []
        for j, c in enumerate(_list(raw.get("claims"), f"{where}.claims")):
            cw = f"{where}.claims[{j}]"
            rc = _mapping(c, {"text", "citations"}, cw)
            citations = tuple(
                _citation(x, f"{cw}.citations[{k}]")
                for k, x in enumerate(_list(rc.get("citations", []), f"{cw}.citations"))
            )
            claims.append(Claim(_str(rc.get("text"), f"{cw}.text"), citations))
        edits.append(DocEdit(_str(raw.get("doc_path"), f"{where}.doc_path"), tuple(claims)))
    return Draft(tuple(edits))


def _citation(data: Any, where: str) -> Citation:
    if isinstance(data, dict) and "fact" in data:
        raw = _mapping(data, {"fact"}, where)
        setting, _, kind = _str(raw["fact"], f"{where}.fact").partition(".")
        if not setting or not kind:
            raise DraftFormatError(f"{where}.fact must be setting.kind")
        return FactCitation(setting, kind)
    raw = _mapping(data, {"path", "line", "side", "quote"}, where)
    line = raw.get("line")
    if not isinstance(line, int) or isinstance(line, bool) or line < 1:
        raise DraftFormatError(f"{where}.line must be a positive integer")
    side = raw.get("side", "new")
    if side not in {s.value for s in Side}:
        raise DraftFormatError(f"{where}.side must be 'new' or 'old'")
    return DiffCitation(
        _str(raw.get("path"), f"{where}.path"), line, Side(side), _str(raw.get("quote"), where)
    )


def _mapping(data: Any, allowed: set[str], where: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise DraftFormatError(f"{where} must be a mapping")
    unknown = set(data) - allowed
    if unknown:
        raise DraftFormatError(f"{where}: unknown keys {sorted(unknown)}")
    return data


def _list(data: Any, where: str) -> list[Any]:
    if not isinstance(data, list):
        raise DraftFormatError(f"{where} must be a list")
    return data


def _str(data: Any, where: str) -> str:
    if not isinstance(data, str) or not data.strip():
        raise DraftFormatError(f"{where} must be a non-empty string")
    return data
