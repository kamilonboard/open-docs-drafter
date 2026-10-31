# Contributing

## Setup

Install [uv](https://docs.astral.sh/uv/), then:

```sh
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

## Ground rules

- The core rules in the README can't be weakened by a pull request without a design discussion first.
- Layers 1, 3, 5 and 7 are plain code with their own tests. Don't add AI calls to them.
- Every new check needs a planted-error test that proves it catches the problem.
- Before changing a project profile, run `backtest` with `--baseline` set to the old profile, and
  explain every PR whose tier went down.
