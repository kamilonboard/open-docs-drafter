"""Command-line entry point."""

import argparse
import sys

from open_docs_drafter import __version__
from open_docs_drafter.layers.triage import rule_based_tier
from open_docs_drafter.profile import ProfileError, load_profile


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

    result = rule_based_tier(profile, args.files, args.texts)
    print(f"Tier: {result.tier.name}")
    for m in result.matches:
        print(f"  {m.tier.name:<5} {m.rule_id}: {m.evidence}  ({m.reason})")
    for path in result.unmatched_files:
        print(f"  {profile.default_tier.name:<5} (no rule, default tier): {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
