"""Generic Swift extractors: struct property defaults and Codable key names."""

import re

from open_docs_drafter.extractors.swift_scan import line_of, line_text, literal, strip_comment
from open_docs_drafter.facts import Fact, Kind

_PROPERTY = re.compile(
    r"^[ \t]*(?:@\w+(?:\([^)]*\))?\s+)*(?:public\s+|private\s+|internal\s+)?var\s+(\w+)"
    r"\s*(?::\s*[\w.?<>\[\], ]+?)?\s*=\s*(.+)$",
    re.MULTILINE,
)
_CODING_KEYS = re.compile(r"enum\s+CodingKeys\s*:\s*String[^{]*\{")
_CASE = re.compile(r"^\s*case\s+(.+)$", re.MULTILINE)


def struct_defaults(path: str, text: str) -> list[Fact]:
    """`var name: Type = value` inside top-level struct/class bodies."""
    facts = []
    for m in _PROPERTY.finditer(text):
        name, raw = m.group(1), strip_comment(m.group(2))
        line = line_of(text, m.start(1))
        value = literal(raw)
        facts.append(
            Fact(
                setting=name,
                kind=Kind.DEFAULT,
                value=value,
                path=path,
                line=line,
                source=line_text(text, line),
                needs_human=None if value is not None else f"default is not a literal: {raw}",
            )
        )
    return facts


def coding_keys(path: str, text: str) -> list[Fact]:
    """`case swiftName = "json_name"` (and bare `case name`) in CodingKeys enums."""
    facts = []
    for block in _CODING_KEYS.finditer(text):
        end = text.find("}", block.end())
        body_start = block.end()
        body = text[body_start:end]
        for m in _CASE.finditer(body):
            for entry in m.group(1).split(","):
                entry = strip_comment(entry).strip()
                if not entry:
                    continue
                name, _, raw = (part.strip() for part in entry.partition("="))
                json_key = literal(raw) if raw else name
                line = line_of(text, body_start + m.start())
                facts.append(
                    Fact(
                        setting=name,
                        kind=Kind.JSON_KEY,
                        value=json_key,
                        path=path,
                        line=line,
                        source=line_text(text, line),
                    )
                )
    return facts
