"""Small helpers for scanning Swift source without a full parser.

They only need to find balanced call arguments and read literals. Anything they can't
read exactly is reported as unreadable, never guessed.
"""

import re

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_STRING = re.compile(r'"((?:[^"\\]|\\.)*)"')


def line_of(text: str, offset: int) -> int:
    """1-based line number of a character offset."""
    return text.count("\n", 0, offset) + 1


def line_text(text: str, line: int) -> str:
    return text.splitlines()[line - 1].strip()


def strip_comment(value: str) -> str:
    """Remove a trailing // comment that isn't inside a string."""
    in_string = False
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and in_string:
            i += 2
            continue
        if ch == '"':
            in_string = not in_string
        elif not in_string and value.startswith("//", i):
            return value[:i].rstrip()
        i += 1
    return value.rstrip()


def balanced_args(text: str, open_paren: int) -> str | None:
    """The text between `(` at open_paren and its matching `)`, skipping strings."""
    depth = 0
    in_string = False
    i = open_paren
    while i < len(text):
        ch = text[i]
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren + 1 : i]
        i += 1
    return None


def string_literal(text: str, quote: int) -> tuple[str, int] | None:
    """The raw contents of the Swift string starting at `"` at index quote, and its end.

    Handles `\\(...)` interpolations, including strings nested inside them.
    """
    if quote >= len(text) or text[quote] != '"':
        return None
    i = quote + 1
    while i < len(text):
        ch = text[i]
        if ch == "\\" and text.startswith("\\(", i):
            close = _interpolation_end(text, i + 1)
            if close is None:
                return None
            i = close + 1
            continue
        if ch == "\\":
            i += 2
            continue
        if ch == '"':
            return text[quote + 1 : i], i + 1
        if ch == "\n":
            return None
        i += 1
    return None


def _interpolation_end(text: str, open_paren: int) -> int | None:
    depth = 0
    i = open_paren
    while i < len(text):
        ch = text[i]
        if ch == '"':
            inner = string_literal(text, i)
            if inner is None:
                return None
            i = inner[1]
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


_LOCALIZED_INTERPOLATION = re.compile(
    r'^String\(\s*localized:\s*"((?:[^"\\]|\\.)*)"'
    r'(?:\s*,\s*comment:\s*"(?:[^"\\]|\\.)*")?\s*\)$'
)


def render_string(raw: str) -> tuple[str, str | None]:
    """Render a Swift string's contents for display.

    `\\(String(localized: "U/hr"))` becomes `U/hr`. Any other interpolation depends on
    values only known at runtime, so the text is returned as written with a reason.
    """
    out: list[str] = []
    problem: str | None = None
    i = 0
    while i < len(raw):
        if raw.startswith("\\(", i):
            close = _interpolation_end(raw, i + 1)
            if close is None:
                return raw, "unbalanced interpolation"
            inner = raw[i + 2 : close].strip()
            m = _LOCALIZED_INTERPOLATION.match(inner)
            if m:
                out.append(m.group(1))
            else:
                out.append(f"\\({inner})")
                problem = problem or f"depends on a runtime value: \\({inner})"
            i = close + 1
            continue
        if raw.startswith("\\", i) and i + 1 < len(raw):
            out.append({"n": "\n", "t": "\t"}.get(raw[i + 1], raw[i + 1]))
            i += 2
            continue
        out.append(raw[i])
        i += 1
    return "".join(out), problem


def literal(value: str) -> str | None:
    """A Swift literal as written: number, true/false, string contents or `.enumCase`.

    Returns None for anything else (calculations, function calls, variables).
    """
    value = strip_comment(value).strip().rstrip(",").strip()
    if _NUMBER.fullmatch(value):
        return value
    if value in ("true", "false"):
        return value
    m = _STRING.fullmatch(value)
    if m:
        return m.group(1)
    if re.fullmatch(r"\.[A-Za-z_]\w*", value):
        return value
    return None


def named_args(args: str) -> dict[str, tuple[str, int]]:
    """Top-level `name: value` arguments of a call, with each value's offset in args."""
    result: dict[str, tuple[str, int]] = {}
    depth = 0
    in_string = False
    start = 0
    parts: list[tuple[str, int]] = []
    i = 0
    while i < len(args):
        ch = args[i]
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append((args[start:i], start))
            start = i + 1
        i += 1
    parts.append((args[start:], start))
    for part, offset in parts:
        m = re.match(r"\s*(\w+)\s*:\s*", part)
        if m:
            result[m.group(1)] = (part[m.end() :].strip(), offset + m.end())
    return result
