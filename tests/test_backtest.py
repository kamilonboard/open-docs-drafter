import copy
import json
from pathlib import Path
from typing import Any

import pytest

from open_docs_drafter import backtest, cli
from open_docs_drafter.github import ChangedFile, PullRequest, PullRequestCache, fetch_merged
from open_docs_drafter.profile import parse_profile
from open_docs_drafter.tiers import Tier

PROFILE_DATA: dict[str, Any] = {
    "profile_version": 1,
    "project": {
        "name": "Example",
        "code_repo": "org/app",
        "docs_repo": "org/docs",
        "docs_branch": "main",
        "docs_format": "mkdocs",
    },
    "rules": [
        {"id": "ex-red-algo", "tier": "red", "reason": "Algorithm", "paths": ["algo/*"]},
        {"id": "ex-green-ui", "tier": "green", "reason": "UI", "paths": ["ui/*"]},
    ],
}
PROFILE = parse_profile(PROFILE_DATA)


def pr(number: int, *paths: str, patch: str = "", title: str = "Change") -> PullRequest:
    return PullRequest(
        number=number,
        title=title,
        body="",
        merged_at=f"2026-10-{number:02d}T00:00:00Z",
        files=tuple(ChangedFile(p, patch) for p in paths),
    )


PRS = [pr(3, "ui/a.swift"), pr(2, "algo/x.js"), pr(1, "lib/new.swift")]


def test_changed_lines_skips_context_and_headers() -> None:
    patch = "--- a/f\n+++ b/f\n@@ -1,3 +1,3 @@\n context\n-old line\n+new line"
    assert backtest.changed_lines(patch) == ["old line", "new line"]


def test_context_lines_do_not_raise_tier() -> None:
    # "carb ratio" only in an unchanged context line must not trigger the core red rule.
    patch = "@@ -1,2 +1,2 @@\n let carb ratio = 1\n-a\n+b"
    result = backtest.triage_pr(PROFILE, pr(1, "ui/a.swift", patch=patch))
    assert result.triage.tier is Tier.GREEN


def test_added_line_keyword_raises_tier() -> None:
    patch = '@@ -1 +1 @@\n-a\n+Text("Carb ratio")'
    assert backtest.triage_pr(PROFILE, pr(1, "ui/a.swift", patch=patch)).triage.tier is Tier.RED


def test_counts() -> None:
    assert backtest.tier_counts(backtest.run(PROFILE, PRS)) == {"RED": 1, "AMBER": 1, "GREEN": 1}


def test_compare_flags_lowered_tiers() -> None:
    looser = copy.deepcopy(PROFILE_DATA)
    looser["rules"][0]["tier"] = "amber"
    changes = backtest.compare(backtest.run(PROFILE, PRS), backtest.run(parse_profile(looser), PRS))
    assert [(c.number, c.before, c.after, c.lowered) for c in changes] == [
        (2, Tier.RED, Tier.AMBER, True)
    ]
    assert "LOWERED" in backtest.format_text(backtest.run(PROFILE, PRS), changes)


def test_formats_render() -> None:
    results = backtest.run(PROFILE, PRS)
    assert "3 PRs: red 1, amber 1, green 1" in backtest.format_text(results, None)
    assert backtest.format_markdown(results, None).startswith("| PR | Tier |")
    assert json.loads(backtest.format_json(results, []))["counts"]["RED"] == 1


def test_cache_round_trip(tmp_path: Path) -> None:
    cache = PullRequestCache(tmp_path, "org/app")
    for p in PRS:
        cache.put(p)
    assert cache.get(2) == PRS[1]
    assert [p.number for p in cache.all()] == [3, 2, 1]


class FakeClient:
    def __init__(self) -> None:
        self.file_calls: list[int] = []

    def merged_pulls(self, repo: str, limit: int, base: str | None = None) -> list[dict[str, Any]]:
        return [
            {"number": p.number, "title": p.title, "body": None, "merged_at": p.merged_at}
            for p in PRS[:limit]
        ]

    def pull_files(self, repo: str, number: int) -> tuple[ChangedFile, ...]:
        self.file_calls.append(number)
        return next(p.files for p in PRS if p.number == number)


def test_fetch_uses_cache(tmp_path: Path) -> None:
    cache = PullRequestCache(tmp_path, "org/app")
    client = FakeClient()
    first = fetch_merged(client, cache, "org/app", 3)  # type: ignore[arg-type]
    second = fetch_merged(client, cache, "org/app", 3)  # type: ignore[arg-type]
    assert first == second == PRS
    assert client.file_calls == [3, 2, 1]  # Only fetched once.


def test_cli_offline(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    profile_path = tmp_path / "p.yaml"
    profile_path.write_text(json.dumps(PROFILE_DATA))  # JSON is valid YAML.
    cache = PullRequestCache(tmp_path / "cache", "org/app")
    for p in PRS:
        cache.put(p)
    argv = ["backtest", "--profile", str(profile_path), "--offline"]
    code = cli.main([*argv, "--cache-dir", str(tmp_path / "cache")])
    assert code == 0
    assert "3 PRs: red 1, amber 1, green 1" in capsys.readouterr().out


def test_cli_offline_without_cache_fails(tmp_path: Path) -> None:
    profile_path = tmp_path / "p.yaml"
    profile_path.write_text(json.dumps(PROFILE_DATA))
    argv = ["backtest", "--profile", str(profile_path), "--offline"]
    assert cli.main([*argv, "--cache-dir", str(tmp_path / "none")]) == 1
