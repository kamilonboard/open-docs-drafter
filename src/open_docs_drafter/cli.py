"""Command-line entry point."""

import argparse

from open_docs_drafter import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="open-docs-drafter",
        description="Draft documentation updates from merged code changes (draft PRs only).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
