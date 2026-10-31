"""Find warning boxes (MkDocs Material admonitions) in Markdown.

    !!! danger "Important Safety Note"
        Remote bolus is a powerful feature that delivers real insulin.

A box is its opening line plus every following line that is blank or indented further
than the opening line. Boxes can be nested inside lists, tabs or other boxes.
"""

import re
from dataclasses import dataclass

# Types that carry safety information. "important" is an alias of "tip" in MkDocs Material,
# but TrioDocs authors use it for things users must not miss, so it is protected too.
PROTECTED_TYPES = frozenset(
    {"warning", "caution", "attention", "danger", "error", "important", "failure", "bug"}
)

_OPENER = re.compile(r"^([ \t]*)(?:!!!|\?\?\?\+?)[ \t]+([A-Za-z][\w-]*)")


@dataclass(frozen=True)
class Admonition:
    kind: str  # Lower-case type, e.g. "danger"
    start_line: int  # 1-based
    text: str  # The opening line and body, trailing blank lines removed

    @property
    def protected(self) -> bool:
        return self.kind in PROTECTED_TYPES

    @property
    def title(self) -> str:
        return self.text.splitlines()[0].strip()


def find_admonitions(markdown: str) -> list[Admonition]:
    lines = markdown.splitlines()
    found: list[Admonition] = []
    for i, line in enumerate(lines):
        m = _OPENER.match(line)
        if not m:
            continue
        indent = _width(m.group(1))
        end = i + 1
        while end < len(lines) and (not lines[end].strip() or _indent(lines[end]) > indent):
            end += 1
        while end > i + 1 and not lines[end - 1].strip():
            end -= 1
        found.append(Admonition(m.group(2).lower(), i + 1, "\n".join(lines[i:end])))
    return found


def protected_admonitions(markdown: str) -> list[Admonition]:
    return [a for a in find_admonitions(markdown) if a.protected]


def _indent(line: str) -> int:
    return _width(line[: len(line) - len(line.lstrip())])


def _width(whitespace: str) -> int:
    return sum(4 if ch == "\t" else 1 for ch in whitespace)
