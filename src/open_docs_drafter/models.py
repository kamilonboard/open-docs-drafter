"""Pull request data shared by the layers, the backtest and the GitHub client."""

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
        )


def changed_lines(patch: str) -> list[str]:
    """Added and removed lines from unified diff hunks, without the +/- marker.

    Unchanged context lines are left out, so they can't raise a tier or support a claim.
    """
    return [
        line[1:]
        for line in patch.splitlines()
        if line[:1] in ("+", "-") and not line.startswith(("+++", "---"))
    ]
