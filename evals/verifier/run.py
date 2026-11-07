"""Live eval of layer 6, the independent verifier.

Each case is a one-claim draft about a real merged Trio PR, labelled supported,
not_supported, advice or omission (see cases.yaml). The runner calls the real layer 6
entry point, `verify()`, with the production prompt, and grades whether the draft was
escalated when it should be and passed when it should be.

    uv run python evals/verifier/run.py review                       # write cases.md to read
    uv run python evals/verifier/run.py run --provider oracle         # free harness checks
    uv run python evals/verifier/run.py run --provider claude --limit 5   # paid pilot
    uv run python evals/verifier/run.py run --provider claude         # full baseline
    uv run python evals/verifier/run.py summary                       # write summary.md

Paid runs refuse to start until the harness is approved: run once with --approve-harness
after reading the code. Any later change to the runner, the cases, the verifier or the
Claude provider needs approving again.

Outputs go to .claude/hillclimb/verifier/<variant>/: results.jsonl (one row per case and
repeat, written as each finishes), traces/<id>_rep<k>.json and errors.jsonl. A restart
skips (case, repeat) pairs already in results.jsonl.
"""

import argparse
import hashlib
import json
import math
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from open_docs_drafter.drafts import Claim, DiffCitation, DocEdit, Draft, Side
from open_docs_drafter.facts import FactSet
from open_docs_drafter.github import GitHubClient, PullRequestCache, fetch_pull, find_token
from open_docs_drafter.layers.citation_check import check_draft
from open_docs_drafter.layers.verifier import Verdict, verify
from open_docs_drafter.models import PullRequest
from open_docs_drafter.profile import load_profile
from open_docs_drafter.providers import ClaudeProvider, FakeProvider, ProviderError

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CASES = HERE / "cases.yaml"
FLOW = ROOT / ".claude" / "hillclimb" / "verifier"
STATE = FLOW / "_state.json"
PROFILE = ROOT / "profiles" / "trio" / "profile.yaml"
REPO = "nightscout/Trio"
HARNESS_PATHS = [
    "evals/verifier/run.py",
    "evals/verifier/cases.yaml",
    "src/open_docs_drafter/layers/verifier.py",
    "src/open_docs_drafter/providers/claude.py",
    "src/open_docs_drafter/providers/base.py",
    "uv.lock",
]
FAKE_MODES = {"oracle", "always-supported", "always-reject", "error"}
SHOULD_ESCALATE = {"not_supported", "advice", "omission"}

# $ per million tokens. Cache writes cost 1.25x input, cache reads 0.1x input.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-opus-4-8": (5.00, 25.00),
}


# ------------------------------------------------------------------ cases


def load_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    seen = set()
    for c in cases:
        unknown = set(c) - {"id", "pr", "label", "trap", "claim", "cites"}
        if unknown or c["id"] in seen or c["label"] not in {"supported", *SHOULD_ESCALATE}:
            raise SystemExit(f"bad case {c.get('id')}: unknown keys {unknown} or bad id/label")
        seen.add(c["id"])
    return cases


def load_pr(number: int, cache: PullRequestCache) -> PullRequest:
    pr = cache.get(number)
    if pr is None:
        pr = fetch_pull(GitHubClient(find_token()), cache, REPO, number)
    return pr


def build_draft(case: dict[str, Any]) -> Draft:
    cites = tuple(DiffCitation(p, int(n), Side(s), str(q)) for p, n, s, q in case["cites"])
    return Draft((DocEdit("docs/eval.md", (Claim(case["claim"], cites),)),))


# ------------------------------------------------------------------ harness gate


def harness_sha() -> str:
    h = hashlib.sha256()
    for rel in HARNESS_PATHS:
        h.update(rel.encode())
        h.update((ROOT / rel).read_bytes())
    return h.hexdigest()


def read_state() -> dict[str, Any]:
    if STATE.exists():
        state: dict[str, Any] = json.loads(STATE.read_text())
        return state
    return {}


def write_state(state: dict[str, Any]) -> None:
    FLOW.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2) + "\n")


def check_gate(approve: bool) -> None:
    state = read_state()
    current = harness_sha()
    if approve:
        state.update(
            harness_sha=current,
            harness_paths=HARNESS_PATHS,
            approved_at=datetime.now(UTC).isoformat(),
        )
        write_state(state)
        print(f"Harness approved ({current[:12]}).")
        return
    if state.get("harness_sha") != current:
        print(
            "The harness has not been approved, or changed since it was approved.\n"
            "Read the runner, cases and verifier, then run again with --approve-harness.",
            file=sys.stderr,
        )
        raise SystemExit(2)


# ------------------------------------------------------------------ providers


def fake_verifier(mode: str, case: dict[str, Any]) -> FakeProvider:
    if mode == "error":

        class Failing(FakeProvider):
            def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> Any:
                raise ProviderError("induced error for the harness check")

        return Failing(model=f"fake-{mode}")
    if mode == "oracle":
        label = case["label"]
        verdict = "supported" if label == "omission" else label
        omissions = ["the draft leaves out a safety-relevant change"] if label == "omission" else []
    elif mode == "always-supported":
        verdict, omissions = "supported", []
    else:
        verdict, omissions = "not_supported", []
    answer = {
        "claims": [{"id": 1, "verdict": verdict, "explanation": mode}],
        "omissions": omissions,
    }
    return FakeProvider(answer, model=f"fake-{mode}")


# ------------------------------------------------------------------ one attempt


def run_case(
    case: dict[str, Any], rep: int, pr: PullRequest, args: argparse.Namespace
) -> tuple[str, dict[str, Any], list[dict[str, Any]] | None]:
    """Returns ("ok" | "error", row, trace)."""
    profile = load_profile(PROFILE)
    draft = build_draft(case)
    citations = check_draft(draft, pr, FactSet([]))
    if not citations.accepted:  # The verifier never sees drafts layer 5 rejects.
        problems = "; ".join(p.detail for p in citations.problems)
        return "error", {"failure": "case-rejected-by-layer-5", "detail": problems}, None

    verifier: ClaudeProvider | FakeProvider
    if args.provider == "claude":
        verifier = ClaudeProvider(
            model=args.model,
            effort=args.effort,
            fallbacks=not args.no_fallbacks,
            timeout=args.timeout_s,
        )
    else:
        verifier = fake_verifier(args.provider, case)

    started = time.monotonic()
    result = verify(
        profile,
        pr,
        draft,
        citations,
        FactSet([]),
        [],
        drafter=FakeProvider(model="none"),
        verifier=verifier,
    )
    latency = round(time.monotonic() - started, 2)
    response = result.response
    codes = {p.code for p in result.problems}

    if "verifier-unavailable" in codes and response is None:
        detail = next(p.detail for p in result.problems if p.code == "verifier-unavailable")
        return "error", {"failure": "serving-error", "detail": detail}, None
    if response is not None and args.provider == "claude" and response.model_served != args.model:
        return (
            "error",
            {
                "failure": "served-model-mismatch",
                "detail": f"asked for {args.model}, served by {response.model_served}",
                "model": response.model_served,
                "usage": response.usage,
            },
            None,
        )

    if response is not None and response.stop_reason == "refusal":
        status = "refusal"
    elif response is not None and response.stop_reason == "max_tokens":
        status = "truncated"
    elif "verifier-output-invalid" in codes:
        status = "invalid_output"
    else:
        status = "ok"

    escalated = not result.accepted
    expected = case["label"] in SHOULD_ESCALATE
    verdict = result.verdicts[0].verdict.value if result.verdicts else None
    if case["label"] == "omission":
        exact = verdict == Verdict.SUPPORTED.value and bool(result.omissions)
    elif case["label"] == "supported":
        exact = verdict == Verdict.SUPPORTED.value and not result.omissions
    else:
        exact = verdict == case["label"]

    row: dict[str, Any] = {
        "prompt_id": case["id"],
        "rep": rep,
        "prompt": case["claim"],
        "tags": [case["label"], case["trap"], f"PR #{case['pr']}"],
        "status": status,
        "stop_reason": response.stop_reason if response else None,
        "grade": {
            "correct": float(escalated == expected) if status == "ok" else None,
            "exact": float(exact) if status == "ok" else None,
        },
        "explanation": {"correct": result.verdicts[0].explanation if result.verdicts else ""},
        "model": response.model_served if response else None,
        "usage": response.usage if response else {},
        "latency_s": latency,
        "meta": {
            "label": case["label"],
            "trap": case["trap"],
            "pr": case["pr"],
            "escalated": escalated,
            "verdict": verdict,
            "omissions": list(result.omissions),
            "problems": [f"{p.code}: {p.detail}" for p in result.problems],
            "request_id": response.request_id if response else None,
            "fallbacks": not args.no_fallbacks if args.provider == "claude" else None,
        },
    }
    trace = [
        {"role": "system", "content": result.system or ""},
        {"role": "user", "content": result.user or ""},
        {
            "role": "assistant",
            "content": result.raw_output or (response.refusal if response else "") or "",
        },
    ]
    return "ok", row, trace


# ------------------------------------------------------------------ run


def cmd_run(args: argparse.Namespace) -> int:
    if args.provider == "claude":
        check_gate(args.approve_harness)
        variant_dir = FLOW / args.variant
    else:
        variant_dir = FLOW / "_checks" / args.provider
    if args.provider not in FAKE_MODES | {"claude"}:
        raise SystemExit(f"unknown provider {args.provider}")

    cases = load_cases()
    if args.limit:
        cases = cases[: args.limit]
    variant_dir.mkdir(parents=True, exist_ok=True)
    (variant_dir / "traces").mkdir(exist_ok=True)
    results_path = variant_dir / "results.jsonl"
    errors_path = variant_dir / "errors.jsonl"
    done = set()
    if results_path.exists():
        for line in results_path.read_text().splitlines():
            row = json.loads(line)
            done.add((row["prompt_id"], row["rep"]))

    cache = PullRequestCache(ROOT / ".cache" / "backtest", REPO)
    prs = {n: load_pr(n, cache) for n in sorted({c["pr"] for c in cases})}
    todo = [(c, r) for c in cases for r in range(args.reps) if (c["id"], r) not in done]
    print(
        f"{len(todo)} attempts to run ({len(cases)} cases x {args.reps} reps, {len(done)} already done)"
    )
    if not todo:
        return 0

    lock = threading.Lock()
    started = time.monotonic()
    counts: Counter[str] = Counter()

    def work(case: dict[str, Any], rep: int) -> None:
        try:
            kind, row, trace = run_case(case, rep, prs[case["pr"]], args)
        except Exception as exc:  # Harness failure: record it, never score it.
            kind, row, trace = "error", {"failure": "harness-error", "detail": repr(exc)}, None
        with lock:
            if kind == "ok":
                (variant_dir / "traces" / f"{case['id']}_rep{rep}.json").write_text(
                    json.dumps(trace, indent=1)
                )
                with results_path.open("a") as f:
                    f.write(json.dumps(row) + "\n")
                counts[row["status"]] += 1
            else:
                row.update(prompt_id=case["id"], rep=rep, at=datetime.now(UTC).isoformat())
                with errors_path.open("a") as f:
                    f.write(json.dumps(row) + "\n")
                counts["error:" + row["failure"]] += 1

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(work, c, r) for c, r in todo]
        for i, _ in enumerate(as_completed(futures), start=1):
            if i % 10 == 0 or i == len(futures):
                print(f"  {i}/{len(futures)} done", flush=True)

    print(f"Finished in {time.monotonic() - started:.0f}s: {dict(counts)}")
    print(summarise(variant_dir, write=args.provider == "claude"))
    return 0


# ------------------------------------------------------------------ summary


def wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    z = 1.96
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def rate(k: int, n: int) -> str:
    if n == 0:
        return "n/a"
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {100 * k / n:.0f}% (95% CI {100 * lo:.0f}-{100 * hi:.0f}%)"


def cost_of(row: dict[str, Any]) -> float | None:
    price = PRICES.get(row.get("model") or "")
    usage = row.get("usage") or {}
    if not price or not usage:
        return None
    pin, pout = price
    return (
        float(
            usage.get("input_tokens", 0) * pin
            + usage.get("cache_creation_input_tokens", 0) * pin * 1.25
            + usage.get("cache_read_input_tokens", 0) * pin * 0.1
            + usage.get("output_tokens", 0) * pout
        )
        / 1e6
    )


def summarise(variant_dir: Path, *, write: bool) -> str:
    results_path = variant_dir / "results.jsonl"
    rows = (
        [json.loads(x) for x in results_path.read_text().splitlines() if x]
        if results_path.exists()
        else []
    )
    errors_path = variant_dir / "errors.jsonl"
    errors = (
        [json.loads(x) for x in errors_path.read_text().splitlines()]
        if errors_path.exists()
        else []
    )
    ok = [r for r in rows if r["status"] == "ok"]
    bad = [r for r in ok if r["meta"]["label"] in SHOULD_ESCALATE]
    good = [r for r in ok if r["meta"]["label"] == "supported"]
    caught = sum(r["meta"]["escalated"] for r in bad)
    false_alarms = sum(r["meta"]["escalated"] for r in good)
    exact = sum(r["grade"]["exact"] for r in ok)
    statuses = Counter(r["status"] for r in rows)

    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_trap: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in ok:
        by_label[r["meta"]["label"]].append(r)
        by_trap[r["meta"]["trap"]].append(r)
        by_case[r["prompt_id"]].append(r)
    unstable = sorted(
        c for c, rs in by_case.items() if len({x["meta"]["escalated"] for x in rs}) > 1
    )

    costs = [c for c in (cost_of(r) for r in rows) if c is not None]
    latencies = sorted(r["latency_s"] for r in ok)
    tokens_in = sorted(
        (
            r["usage"].get("input_tokens", 0)
            + r["usage"].get("cache_read_input_tokens", 0)
            + r["usage"].get("cache_creation_input_tokens", 0)
        )
        for r in rows
        if r.get("usage")
    )
    tokens_out = sorted(r["usage"].get("output_tokens", 0) for r in rows if r.get("usage"))

    def mid(xs: list[Any]) -> Any:
        return xs[len(xs) // 2] if xs else "n/a"

    lines = [
        f"# Verifier eval: {variant_dir.name}",
        "",
        f"Models: {', '.join(sorted({str(r['model']) for r in rows}))}. "
        f"Rows: {len(rows)} ({dict(statuses)}); failed attempts: {len(errors)}.",
        "",
        "| Measure | Result |",
        "|---|---|",
        f"| **Bad claims caught** (escalated) | {rate(caught, len(bad))} |",
        f"| **False alarms** on good claims | {rate(false_alarms, len(good))} |",
        f"| Exact verdict | {rate(int(exact), len(ok))} |",
        f"| Cases whose repeats disagree | {len(unstable)}{': ' + ', '.join(unstable) if unstable else ''} |",
        f"| Cost | ${sum(costs):.2f} total, ${sum(costs) / max(len(costs), 1):.3f} per call |"
        if costs
        else "| Cost | n/a (fake provider) |",
        f"| Tokens per call (median) | in {mid(tokens_in)}, out {mid(tokens_out)} |",
        f"| Latency per call (median, max) | {mid(latencies)} s, {latencies[-1] if latencies else 'n/a'} s |",
        "",
        "## By label",
        "",
        "| Label | Escalated | Exact verdict |",
        "|---|---|---|",
    ]
    for label in ["supported", "not_supported", "advice", "omission"]:
        rs = by_label.get(label, [])
        esc = sum(r["meta"]["escalated"] for r in rs)
        lines.append(
            f"| {label} | {rate(esc, len(rs))} | {rate(int(sum(r['grade']['exact'] for r in rs)), len(rs))} |"
        )
    lines += ["", "## By trap (bad claims)", "", "| Trap | Caught |", "|---|---|"]
    for trap, rs in sorted(by_trap.items()):
        if trap != "none":
            lines.append(f"| {trap} | {rate(sum(r['meta']['escalated'] for r in rs), len(rs))} |")
    lines += ["", "## Misses and false alarms", ""]
    wrong = [r for r in ok if r["grade"]["correct"] == 0.0]
    if not wrong:
        lines.append("None.")
    for r in sorted(wrong, key=lambda x: (x["prompt_id"], x["rep"])):
        kind = "FALSE ALARM" if r["meta"]["label"] == "supported" else "MISSED"
        lines.append(
            f"- **{kind}** `{r['prompt_id']}` rep {r['rep']} ({r['meta']['label']}, {r['meta']['trap']}): "
            f"verdict {r['meta']['verdict']}, omissions {r['meta']['omissions'] or 'none'}. "
            f"Trace: `{variant_dir.name}/traces/{r['prompt_id']}_rep{r['rep']}.json`"
        )
    if errors:
        lines += ["", "## Failed attempts (not scored)", ""]
        for e in errors:
            lines.append(
                f"- `{e['prompt_id']}` rep {e['rep']}: {e['failure']}: {e.get('detail', '')[:160]}"
            )
    text = "\n".join(lines) + "\n"
    if write:
        (variant_dir / "summary.md").write_text(text)
    return text


def cmd_summary(args: argparse.Namespace) -> int:
    print(summarise(FLOW / args.variant, write=True))
    return 0


# ------------------------------------------------------------------ review


def cmd_review(args: argparse.Namespace) -> int:
    cases = load_cases()
    cache = PullRequestCache(ROOT / ".cache" / "backtest", REPO)
    labels = Counter(c["label"] for c in cases)
    out = [
        "# Verifier eval cases",
        "",
        f"{len(cases)} cases on {len({c['pr'] for c in cases})} real merged Trio PRs: "
        + ", ".join(f"{n} {label}" for label, n in sorted(labels.items()))
        + ". Each case is a one-claim draft; the verifier sees the PR's full diff.",
        "",
        "| id | PR | label | trap | claim |",
        "|---|---|---|---|---|",
    ]
    for c in cases:
        out.append(f"| `{c['id']}` | #{c['pr']} | {c['label']} | {c['trap']} | {c['claim']} |")
    out.append("")
    for c in cases:
        pr = load_pr(c["pr"], cache)
        out += [f"## `{c['id']}`: {c['label']} ({c['trap']})", "", f"PR #{c['pr']}: {pr.title}", ""]
        out.append(f"> {c['claim']}")
        out += ["", "Cited lines:", ""]
        for path, line, side, quote in c["cites"]:
            out.append(f"- `{path}` {side} line {line}, quoting `{quote}`")
        out.append("")
    (HERE / "cases.md").write_text("\n".join(out))
    print(f"Wrote {HERE / 'cases.md'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("review", help="write cases.md for review")
    run = sub.add_parser("run", help="run the eval")
    run.add_argument(
        "--provider",
        default="claude",
        help="claude, or a free check: " + ", ".join(sorted(FAKE_MODES)),
    )
    run.add_argument("--model", default="claude-opus-5-5")
    run.add_argument("--effort", default="high")
    run.add_argument("--no-fallbacks", action="store_true")
    run.add_argument("--variant", default="baseline", help="baseline or v1, v2, ...")
    run.add_argument("--reps", type=int, default=2)
    run.add_argument("--limit", type=int, help="only the first N cases (for a pilot)")
    run.add_argument("--concurrency", type=int, default=4)
    run.add_argument("--timeout-s", type=float, default=300.0, help="per request")
    run.add_argument(
        "--approve-harness", action="store_true", help="approve the current harness (you)"
    )
    summary = sub.add_parser("summary", help="rewrite summary.md")
    summary.add_argument("--variant", default="baseline")
    args = parser.parse_args()
    return {"review": cmd_review, "run": cmd_run, "summary": cmd_summary}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
