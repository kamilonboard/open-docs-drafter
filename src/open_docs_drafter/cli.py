"""Command-line entry point."""

import argparse
import difflib
import json
import sys
from pathlib import Path

from open_docs_drafter import __version__, backtest, pipeline
from open_docs_drafter.facts import Fact, inconsistencies
from open_docs_drafter.github import (
    FileCache,
    GitHubClient,
    GitHubError,
    PullRequestCache,
    fetch_merged,
    fetch_pull,
    find_token,
    snapshot,
)
from open_docs_drafter.layers import fact_extraction
from open_docs_drafter.layers.edit_constraints import page_allowed
from open_docs_drafter.layers.triage import rule_based_tier
from open_docs_drafter.profile import Profile, ProfileError, load_profile
from open_docs_drafter.providers import PROVIDERS, ProviderError, make_provider


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

    dr = sub.add_parser(
        "draft",
        help="Dry run: draft docs for one merged PR and run every check. Writes nothing to GitHub.",
    )
    dr.add_argument("--profile", required=True)
    dr.add_argument("--pr", type=int, required=True, help="merged pull request number")
    dr.add_argument("--repo", help="owner/name; defaults to the profile's code_repo")
    dr.add_argument("--provider", default="claude", choices=sorted(PROVIDERS))
    dr.add_argument("--model", help="model id (claude default: claude-opus-5-5)")
    dr.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"])
    dr.add_argument(
        "--no-fallbacks",
        action="store_true",
        help="pin the model exactly; a refusal becomes 'needs human' (hazard H10)",
    )
    dr.add_argument("--cache-dir", default=".cache")
    dr.add_argument("--out", default="runs", help="where to write the audit record")

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

    if args.command == "draft":
        return _draft(args, profile)

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


def _draft(args: argparse.Namespace, profile: Profile) -> int:
    repo = args.repo or profile.project.code_repo
    cache_root = Path(args.cache_dir)
    client = GitHubClient(find_token())
    files_cache = FileCache(cache_root / "files")
    options: dict[str, object] = {"model": args.model}
    if args.provider == "claude":
        options.update(effort=args.effort, fallbacks=not args.no_fallbacks)
    try:
        provider = make_provider(args.provider, **options)
        pr = fetch_pull(client, PullRequestCache(cache_root / "backtest", repo), repo, args.pr)
        head = pr.merge_commit_sha
        parents = client.commit(repo, head)["parents"]
        if not parents:
            raise GitHubError(f"merge commit {head} has no parent")
        base = parents[0]
        print(f"{repo}#{pr.number}: {pr.title}")
        print("  fetching code facts at the merge and before it ...", flush=True)

        def wants_fact_file(path: str) -> bool:
            return bool(fact_extraction.fact_paths(profile, [path]))

        head_files = snapshot(client, files_cache, repo, head, wants_fact_file)
        base_files = snapshot(client, files_cache, repo, base, wants_fact_file)
        docs_repo = profile.project.docs_repo
        docs_sha = client.commit(docs_repo, profile.project.docs_branch)["sha"]
        print(f"  fetching {docs_repo}@{profile.project.docs_branch} pages ...", flush=True)
        pages = snapshot(
            client, files_cache, docs_repo, docs_sha, lambda p: page_allowed(profile, p)
        )
    except (GitHubError, ProviderError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"  drafting with {provider.name} ({provider.model}) ...", flush=True)
    result = pipeline.run(
        profile, pr, provider=provider, base_files=base_files, head_files=head_files, pages=pages
    )
    record = pipeline.audit_record(profile, pr, result)
    record["refs"] = {"code_merge": head, "code_base": base, "docs": docs_sha}
    audit_path = pipeline.write_audit(record, Path(args.out))

    print(f"\nTier: {result.triage.tier.name}   Outcome: {result.outcome.value}")
    print(f"  {result.summary}")
    if result.input_check.findings:
        for f in result.input_check.findings:
            print(f"  layer 1 {f.severity}: {f.code}")
    if result.drafting.evidence:
        ev = result.drafting.evidence
        print("  Evidence pack for a human expert:")
        for c in ev.fact_changes:
            print(f"    fact change: {c}")
        for page in ev.candidate_pages:
            print(f"    likely page: {page}")
    if result.citations:
        for claim_result in result.citations.claims:
            for prob in claim_result.problems:
                print(f"  layer 5 {prob.code}: {prob.detail}")
    if result.edits:
        for edit_problem in result.edits.problems:
            print(f"  layer 7 {edit_problem.code}: {edit_problem.detail}")
        for path, new_text in result.edits.new_pages.items():
            diff = difflib.unified_diff(
                pages[path].splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
            print("".join(diff))
    print(f"Audit record: {audit_path}")
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
