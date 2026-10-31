"""Command-line entry point."""

import argparse
import sys
from pathlib import Path

from open_docs_drafter import __version__, backtest
from open_docs_drafter.github import (
    GitHubClient,
    GitHubError,
    PullRequestCache,
    fetch_merged,
    find_token,
)
from open_docs_drafter.layers.triage import rule_based_tier
from open_docs_drafter.profile import Profile, ProfileError, load_profile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="open-docs-drafter",
        description="Draft documentation updates from merged code changes (draft PRs only).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    check = sub.add_parser("check-profile", help="Validate a project profile file.")
    check.add_argument("profile")

    triage = sub.add_parser(
        "triage", help="Show the rule-based tier for a set of changed files and text."
    )
    triage.add_argument("--profile", required=True)
    triage.add_argument("--file", action="append", default=[], dest="files", metavar="PATH")
    triage.add_argument("--text", action="append", default=[], dest="texts", metavar="TEXT")

    bt = sub.add_parser(
        "backtest", help="Run rule-based triage over recently merged pull requests."
    )
    bt.add_argument("--profile", required=True)
    bt.add_argument("--repo", help="owner/name; defaults to the profile's code_repo")
    bt.add_argument("--limit", type=int, default=40, help="number of merged PRs (default 40)")
    bt.add_argument("--base", help="only PRs merged into this branch")
    bt.add_argument("--baseline", metavar="PROFILE", help="report PRs whose tier differs")
    bt.add_argument("--cache-dir", default=".cache/backtest")
    bt.add_argument("--offline", action="store_true", help="use cached PRs only")
    bt.add_argument("--format", choices=["text", "markdown", "json"], default="text")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    try:
        profile = load_profile(args.profile)
    except (ProfileError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.command == "check-profile":
        print(
            f"OK: {profile.project.name} profile ({profile.status}), "
            f"{len(profile.rules)} project rules + core rules, "
            f"default tier {profile.default_tier.name.lower()}"
        )
        return 0

    if args.command == "backtest":
        return _backtest(args, profile)

    result = rule_based_tier(profile, args.files, args.texts)
    print(f"Tier: {result.tier.name}")
    for m in result.matches:
        print(f"  {m.tier.name:<5} {m.rule_id}: {m.evidence}  ({m.reason})")
    for path in result.unmatched_files:
        print(f"  {profile.default_tier.name:<5} (no rule, default tier): {path}")
    return 0


def _backtest(args: argparse.Namespace, profile: Profile) -> int:
    repo = args.repo or profile.project.code_repo
    cache = PullRequestCache(Path(args.cache_dir), repo)

    baseline = None
    if args.baseline:
        try:
            baseline = load_profile(args.baseline)
        except (ProfileError, OSError) as exc:
            print(f"error: baseline: {exc}", file=sys.stderr)
            return 1

    if args.offline:
        prs = cache.all()[: args.limit]
        if not prs:
            print(
                f"error: no cached PRs in {cache.dir}; run once without --offline", file=sys.stderr
            )
            return 1
    else:
        try:
            prs = fetch_merged(GitHubClient(find_token()), cache, repo, args.limit, args.base)
        except GitHubError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    results = backtest.run(profile, prs)
    changes = backtest.compare(backtest.run(baseline, prs), results) if baseline else None
    formatter = {
        "text": backtest.format_text,
        "markdown": backtest.format_markdown,
        "json": backtest.format_json,
    }[args.format]
    print(formatter(results, changes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
