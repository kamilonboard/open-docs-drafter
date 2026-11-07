import json
from pathlib import Path
from typing import Any

import pytest

from open_docs_drafter import cli, digest
from open_docs_drafter.github import GitHubError, PullRequestCache, fetch_range
from open_docs_drafter.models import ChangedFile, PullRequest
from open_docs_drafter.profile import load_profile, parse_profile
from open_docs_drafter.tiers import Tier

PROFILE = parse_profile(
    {
        "profile_version": 1,
        "project": {
            "name": "Example",
            "code_repo": "org/app",
            "docs_repo": "org/docs",
            "docs_branch": "main",
            "docs_format": "mkdocs",
        },
        "rules": [{"id": "ex-green-ui", "tier": "green", "reason": "UI", "paths": ["ui/*"]}],
    }
)
RED_PATCH = "@@ -0,0 +1 @@\n+// Settings are reset to defaults."


def pr(
    number: int, path: str = "ui/a.swift", patch: str = "", title: str = "Change"
) -> PullRequest:
    return PullRequest(number, title, "", "2026-10-01T00:00:00Z", (ChangedFile(path, patch),))


def build(*prs: PullRequest, **kw: Any) -> digest.Digest:
    return digest.build(PROFILE, "v1", "v2", prs, kw.get("direct", ()), kw.get("outcomes", {}))


def test_every_pr_is_listed_whatever_its_outcome() -> None:
    result = build(pr(1), pr(2), pr(3), outcomes={2: "ready_for_review"})
    assert [(e.pr.number, e.status) for e in result.entries] == [
        (1, digest.NOT_DRAFTED),
        (2, "ready_for_review"),
        (3, digest.NOT_DRAFTED),
    ]


def test_highest_tier_is_listed_first() -> None:
    result = build(pr(1), pr(2, patch=RED_PATCH))
    assert [e.pr.number for e in result.entries] == [2, 1]


def test_settings_reset_needs_attention_and_is_named_at_the_top() -> None:
    text = digest.format_markdown(build(pr(1), pr(2, patch=RED_PATCH)))
    assert text.index("Settings resets") < text.index("All merged pull requests")
    attention = text[: text.index("All merged pull requests")]
    assert "#2" in attention
    assert "#1" not in attention


def test_any_red_change_without_a_finished_review_needs_attention() -> None:
    entry = build(pr(1, patch="@@ -1 +1 @@\n+// dosing")).entries[0]
    assert entry.triage.tier is Tier.RED
    assert entry.needs_attention


def test_green_change_does_not_need_attention() -> None:
    assert not build(pr(1)).entries[0].needs_attention


def test_direct_commits_are_reported_as_a_coverage_gap() -> None:
    text = digest.format_markdown(
        build(pr(1), direct=(digest.DirectCommit("abcdef1234567", "Hotfix | @someone"),))
    )
    assert "abcdef1" in text
    assert "no pull request" in text
    assert " @someone" not in text


def test_counts_cover_every_entry() -> None:
    result = build(pr(1), pr(2, patch=RED_PATCH), pr(3, path="other/x.swift"))
    assert "3 merged pull requests: red 1, amber 1, green 1" in digest.format_markdown(result)


def test_plain_text_keeps_a_title_readable() -> None:
    assert digest.plain_text("Fix `a` | b @team [x](http://y) <b>\nnext") == (
        "Fix \\`a\\` \\| b @​team \\[x\\](http://y) &lt;b> next"
    )


def test_outcomes_keep_the_newest_audit_record_per_pr(tmp_path: Path) -> None:
    def write(name: str, number: int, created: str, outcome: str) -> None:
        record = {"pull_request": {"number": number}, "created_at": created, "outcome": outcome}
        (tmp_path / name).write_text(json.dumps(record))

    write("b.json", 7, "2026-10-02T00:00:00+00:00", "ready_for_review")
    write("a.json", 7, "2026-10-01T00:00:00+00:00", "rejected")
    write("c.json", 8, "2026-10-01T00:00:00+00:00", "escalated")
    (tmp_path / "ignored.txt").write_text("x")
    assert digest.outcomes_from_audit(tmp_path) == {7: "ready_for_review", 8: "escalated"}


def test_outcomes_from_a_missing_folder_are_empty(tmp_path: Path) -> None:
    assert digest.outcomes_from_audit(tmp_path / "none") == {}


def test_unreadable_audit_record_stops_the_digest(tmp_path: Path) -> None:
    # Skipping it could show a reviewed PR's status wrongly; failing is the safe side.
    (tmp_path / "bad.json").write_text("{")
    with pytest.raises(ValueError, match=r"bad\.json"):
        digest.outcomes_from_audit(tmp_path)


# ------------------------------------------------------------------ range walk


class FakeClient:
    def __init__(self, commits: list[dict[str, Any]], total: int, pulls: dict[str, Any]) -> None:
        self.commits, self.total, self.pulls = commits, total, pulls

    def compare(self, repo: str, base: str, head: str) -> list[dict[str, Any]]:
        if len(self.commits) != self.total:
            raise GitHubError("incomplete")
        return self.commits

    def commit_pulls(self, repo: str, sha: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = self.pulls.get(sha, [])
        return result

    def pull(self, repo: str, number: int) -> dict[str, Any]:
        return {
            "title": f"PR {number}",
            "body": "",
            "merged_at": "2026-10-01T00:00:00Z",
            "merge_commit_sha": f"m{number}",
        }

    def pull_files(self, repo: str, number: int) -> tuple[ChangedFile, ...]:
        return (ChangedFile("ui/a.swift", ""),)


def commit(sha: str, message: str = "msg\n\nbody") -> dict[str, Any]:
    return {"sha": sha, "commit": {"message": message}}


def merged(number: int) -> dict[str, Any]:
    return {"number": number, "merged_at": "2026-10-01T00:00:00Z"}


def test_range_finds_each_pr_once_and_keeps_direct_commits(tmp_path: Path) -> None:
    client = FakeClient(
        [commit("a"), commit("b"), commit("c", "Hotfix\n\ndetails")],
        3,
        {"a": [merged(5)], "b": [merged(5), merged(6)]},
    )
    cache = PullRequestCache(tmp_path, "org/app")
    prs, direct = fetch_range(client, cache, "org/app", "v1", "v2")  # type: ignore[arg-type]
    assert [p.number for p in prs] == [5, 6]
    assert direct == (digest.DirectCommit("c", "Hotfix"),)


def test_commit_on_an_unmerged_pr_counts_as_direct(tmp_path: Path) -> None:
    client = FakeClient([commit("a")], 1, {"a": [{"number": 9, "merged_at": None}]})
    cache = PullRequestCache(tmp_path, "org/app")
    prs, direct = fetch_range(client, cache, "org/app", "v1", "v2")  # type: ignore[arg-type]
    assert prs == ()
    assert [d.sha for d in direct] == ["a"]


def test_compare_refuses_a_partial_commit_list(monkeypatch: pytest.MonkeyPatch) -> None:
    from open_docs_drafter.github import GitHubClient

    client = GitHubClient()
    pages = [{"total_commits": 3, "commits": [commit("a"), commit("b")]}, {"commits": []}]
    monkeypatch.setattr(client, "_get", lambda path, params: pages[params["page"] - 1])
    with pytest.raises(GitHubError, match="2 of 3"):
        client.compare("org/app", "v1", "v2")


def test_compare_collects_every_page(monkeypatch: pytest.MonkeyPatch) -> None:
    from open_docs_drafter.github import GitHubClient

    client = GitHubClient()
    first = [commit(str(i)) for i in range(100)]
    pages = [
        {"total_commits": 101, "commits": first},
        {"total_commits": 101, "commits": [commit("last")]},
    ]
    monkeypatch.setattr(client, "_get", lambda path, params: pages[params["page"] - 1])
    assert len(client.compare("org/app", "v1", "v2")) == 101


# ------------------------------------------------------------------ command line


def test_cli_prints_the_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        cli,
        "fetch_range",
        lambda *a: ((pr(4, title="Fix chart"),), (digest.DirectCommit("abc1234", "Hotfix"),)),
    )
    profile = Path(__file__).parent.parent / "profiles" / "trio" / "profile.yaml"
    load_profile(profile)
    code = cli.main(
        [
            "digest",
            "--profile",
            str(profile),
            "--base",
            "v1",
            "--head",
            "v2",
            "--cache-dir",
            str(tmp_path),
            "--runs",
            str(tmp_path / "runs"),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "#4" in out
    assert "abc1234" in out
    assert "Not drafted" in out or "not drafted" in out


def test_cli_exits_non_zero_when_the_range_is_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*args: Any) -> None:
        raise GitHubError("compare returned 2 of 3 commits")

    monkeypatch.setattr(cli, "fetch_range", fail)
    profile = Path(__file__).parent.parent / "profiles" / "trio" / "profile.yaml"
    code = cli.main(
        [
            "digest",
            "--profile",
            str(profile),
            "--base",
            "v1",
            "--head",
            "v2",
            "--cache-dir",
            str(tmp_path),
        ]
    )
    assert code == 1
    assert "2 of 3" in capsys.readouterr().err
