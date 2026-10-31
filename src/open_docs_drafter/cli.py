"""Command-line entry point."""

import argparse
import json
import sys
from pathlib import Path

from open_docs_drafter import __version__, backtest
from open_docs_drafter.facts import Fact, inconsistencies
from open_docs_drafter.github import (
    GitHubClient,
    GitHubError,
    PullRequestCache,
    fetch_merged,
    find_token,
)
from open_docs_drafter.layers import fact_extraction
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

    fx = sub.add_parser(
        "facts", help="Extract exact, cited setting facts from the code at a git ref."
    )
    fx.add_argument("--profile", required=True)
    fx.add_argument("--repo", help="owner/name; defaults to the profile's code_repo")
    fx.add_argument("--ref", default="main", help="branch, tag or commit (default main)")
    fx.add_argument("--base", metavar="REF", help="show what changed from this ref to --ref")
    fx.add_argument("--setting", action="append", default=[], help="only these settings")
    fx.add_argument("--format", choices=["text", "json"], default="text")

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

    if args.command == "facts":
        return _facts(args, profile)

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


def _facts(args: argparse.Namespace, profile: Profile) -> int:
    if not profile.facts:
        print("error: this profile has no `facts` section", file=sys.stderr)
        return 1
    repo = args.repo or profile.project.code_repo
    client = GitHubClient(find_token())

    def snapshot(ref: str) -> dict[str, str]:
        paths = fact_extraction.fact_paths(profile, client.tree(repo, ref))
        return {p: client.file(repo, p, ref) for p in paths}

    try:
        head = snapshot(args.ref)
        base = snapshot(args.base) if args.base else None
    except GitHubError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    wanted = set(args.setting)
    head_facts = fact_extraction.extract_facts(profile, head)
    shown = [f for f in head_facts.facts if not wanted or f.setting in wanted]
    problems = [i for i in inconsistencies(head_facts) if not wanted or i.setting in wanted]
    changes = None
    if base is not None:
        changes = [
            c
            for c in fact_extraction.fact_changes(profile, base, head)
            if not wanted or c.setting in wanted
        ]

    if args.format == "json":
        data: dict[str, object] = {
            "repo": repo,
            "ref": args.ref,
            "facts": [_fact_json(f) for f in shown],
            "inconsistencies": [{"setting": i.setting, "message": i.message} for i in problems],
        }
        if changes is not None:
            data["base"] = args.base
            data["changes"] = [
                {
                    "setting": c.setting,
                    "kind": c.kind.value,
                    "old": _fact_json(c.old) if c.old else None,
                    "new": _fact_json(c.new) if c.new else None,
                }
                for c in changes
            ]
        print(json.dumps(data, indent=2))
        return 0

    by_setting: dict[str, list[Fact]] = {}
    for f in shown:
        by_setting.setdefault(f.setting, []).append(f)
    for setting in sorted(by_setting):
        print(setting)
        for f in by_setting[setting]:
            value = f.value if f.value is not None else f"NEEDS HUMAN ({f.needs_human})"
            unit = f" {f.unit}" if f.unit and f.kind.value in ("min", "max", "step") else ""
            print(f"  {f.kind.value:<15} {value}{unit}  [{f.citation}]")
    needing = [f for f in shown if f.value is None]
    print(
        f"\n{len(shown)} facts for {len(by_setting)} settings at {repo}@{args.ref}; "
        f"{len(needing)} need a human; {len(problems)} inconsistencies"
    )
    for i in problems:
        print(f"  INCONSISTENT {i.setting}: {i.message}")
    if changes is not None:
        print(f"\n{len(changes)} fact changes from {args.base} to {args.ref}:")
        for c in changes:
            where = c.new.citation if c.new else (c.old.citation if c.old else "")
            print(f"  {c.summary}  [{where}]")
    return 0


def _fact_json(f: Fact) -> dict[str, object]:
    return {
        "setting": f.setting,
        "kind": f.kind.value,
        "value": f.value,
        "unit": f.unit,
        "path": f.path,
        "line": f.line,
        "source": f.source,
        "needs_human": f.needs_human,
    }


if __name__ == "__main__":
    raise SystemExit(main())
