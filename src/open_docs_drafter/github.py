"""Minimal read-only GitHub REST client for fetching merged pull requests.

Uses only the standard library. It never writes to GitHub.
"""

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from open_docs_drafter.models import ChangedFile, PullRequest

API = "https://api.github.com"


class GitHubError(RuntimeError):
    pass


def find_token() -> str | None:
    """GITHUB_TOKEN or GH_TOKEN, else the GitHub CLI's stored login, else None."""
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(name):
            return os.environ[name]
    gh = shutil.which("gh") or str(Path.home() / "bin" / "gh")
    if Path(gh).exists():
        try:
            out = subprocess.run(
                [gh, "auth", "token"], capture_output=True, text=True, timeout=10, check=True
            )
            return out.stdout.strip() or None
        except (subprocess.SubprocessError, OSError):
            return None
    return None


class GitHubClient:
    def __init__(self, token: str | None = None) -> None:
        self.token = token

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        url = f"{API}{path}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url)
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("X-GitHub-Api-Version", "2022-11-28")
        request.add_header("User-Agent", "open-docs-drafter")
        if self.token:
            request.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            hint = (
                " (set GITHUB_TOKEN or log in with `gh auth login`)"
                if exc.code in (401, 403)
                else ""
            )
            raise GitHubError(f"GitHub API {exc.code} for {path}{hint}") from exc
        except urllib.error.URLError as exc:
            raise GitHubError(f"Could not reach GitHub: {exc.reason}") from exc

    def merged_pulls(self, repo: str, limit: int, base: str | None = None) -> list[dict[str, Any]]:
        """The most recently merged pull requests, newest merge first (list data only)."""
        merged: list[dict[str, Any]] = []
        params: dict[str, Any] = {"state": "closed", "sort": "updated", "direction": "desc"}
        if base:
            params["base"] = base
        for page in range(1, 11):
            batch = self._get(f"/repos/{repo}/pulls", {**params, "per_page": 100, "page": page})
            merged.extend(p for p in batch if p.get("merged_at"))
            if len(batch) < 100 or len(merged) >= limit * 2:
                break
        merged.sort(key=lambda p: p["merged_at"], reverse=True)
        return merged[:limit]

    def pull_files(self, repo: str, number: int) -> tuple[ChangedFile, ...]:
        files: list[ChangedFile] = []
        for page in range(1, 31):
            batch = self._get(
                f"/repos/{repo}/pulls/{number}/files", {"per_page": 100, "page": page}
            )
            files.extend(ChangedFile(f["filename"], f.get("patch") or "") for f in batch)
            if len(batch) < 100:
                break
        return tuple(files)


class PullRequestCache:
    """One JSON file per pull request, so re-runs are fast, offline and reproducible."""

    def __init__(self, root: Path, repo: str) -> None:
        self.dir = root / repo.replace("/", "__")

    def _path(self, number: int) -> Path:
        return self.dir / f"pr_{number}.json"

    def get(self, number: int) -> PullRequest | None:
        path = self._path(number)
        if not path.exists():
            return None
        return PullRequest.from_json(json.loads(path.read_text(encoding="utf-8")))

    def put(self, pr: PullRequest) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self._path(pr.number).write_text(json.dumps(pr.to_json(), indent=1), encoding="utf-8")

    def all(self) -> list[PullRequest]:
        if not self.dir.exists():
            return []
        prs = [
            PullRequest.from_json(json.loads(p.read_text(encoding="utf-8")))
            for p in self.dir.glob("pr_*.json")
        ]
        return sorted(prs, key=lambda p: p.merged_at, reverse=True)


def fetch_merged(
    client: GitHubClient, cache: PullRequestCache, repo: str, limit: int, base: str | None = None
) -> list[PullRequest]:
    """Fetch the latest merged PRs, using the cache for any already downloaded."""
    result: list[PullRequest] = []
    for item in client.merged_pulls(repo, limit, base):
        pr = cache.get(item["number"])
        if pr is None:
            pr = PullRequest(
                number=item["number"],
                title=item["title"],
                body=item.get("body") or "",
                merged_at=item["merged_at"],
                files=client.pull_files(repo, item["number"]),
            )
            cache.put(pr)
        result.append(pr)
    return result
