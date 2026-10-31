"""Top-level keys of a JSON defaults file, with the line each appears on."""

import json
import re

from open_docs_drafter.facts import Fact, Kind


def extract(path: str, text: str) -> list[Fact]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [Fact("(file)", Kind.JSON_DEFAULT, None, path, exc.lineno, "", needs_human=str(exc))]
    if not isinstance(data, dict):
        return []
    lines = text.splitlines()
    facts = []
    for key, value in data.items():
        line = _find_line(lines, key)
        if isinstance(value, bool):
            written: str | None = "true" if value else "false"
        elif isinstance(value, int | float):
            written = _number_as_written(lines[line - 1]) if line else str(value)
        elif isinstance(value, str):
            written = value
        else:
            written = None
        facts.append(
            Fact(
                setting=key,
                kind=Kind.JSON_DEFAULT,
                value=written,
                path=path,
                line=line or 1,
                source=lines[line - 1].strip() if line else "",
                needs_human=None if written is not None else "value is not a plain literal",
            )
        )
    return facts


def _find_line(lines: list[str], key: str) -> int:
    pattern = re.compile(r'^\s*"' + re.escape(key) + r'"\s*:')
    for i, line in enumerate(lines, start=1):
        if pattern.match(line):
            return i
    return 0


def _number_as_written(line: str) -> str | None:
    m = re.search(r":\s*(-?\d+(?:\.\d+)?)", line)
    return m.group(1) if m else None
