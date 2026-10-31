"""Pull request data shared by the layers, the backtest and the GitHub client."""

import re
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ChangedFile:
    path: str
    patch: str  # Unified diff hunks; empty for binary or very large files.


@dataclass(frozen=True)
class PullRequest:
    number: int
    title: str
    body: str
    merged_at: str
    files: tuple[ChangedFile, ...]
    merge_commit_sha: str = ""  # The commit that merged it; empty if unknown

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "PullRequest":
        return cls(
            number=int(data["number"]),
            title=data["title"],
            body=data.get("body") or "",
            merged_at=data["merged_at"],
            files=tuple(ChangedFile(f["path"], f.get("patch") or "") for f in data["files"]),
            merge_commit_sha=data.get("merge_commit_sha") or "",
        )


@dataclass(frozen=True)
class PatchLine:
    marker: str  # "+" added, "-" removed, " " unchanged context
    old_line: int | None  # Line number before the change (None for added lines)
    new_line: int | None  # Line number after the change (None for removed lines)
    text: str


_HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def patch_lines(patch: str) -> list[PatchLine]:
    """Every line in a patch's hunks, with its old and new line numbers.

    Lines under a hunk header that can't be read get no numbers, so they can't be cited.
    """
    result: list[PatchLine] = []
    old: int | None = None
    new: int | None = None
    for raw in patch.splitlines():
        header = _HUNK.match(raw)
        if header:
            old, new = int(header.group(1)), int(header.group(2))
            continue
        if raw.startswith("@@"):
            old = new = None
            continue
        if raw.startswith("\\"):  # "\ No newline at end of file"
            continue
        marker, text = (raw[:1] or " "), raw[1:]
        if marker not in "+- ":
            continue
        if old is None or new is None:
            continue
        if marker == "+":
            result.append(PatchLine("+", None, new, text))
            new += 1
        elif marker == "-":
            result.append(PatchLine("-", old, None, text))
            old += 1
        else:
            result.append(PatchLine(" ", old, new, text))
            old += 1
            new += 1
    return result


def changed_lines(patch: str) -> list[str]:
    """Added and removed lines from unified diff hunks, without the +/- marker.

    Unchanged context lines are left out, so they can't raise a tier or support a claim.
    """
    return [
        line[1:]
        for line in patch.splitlines()
        if line[:1] in ("+", "-") and not line.startswith(("+++", "---"))
    ]
