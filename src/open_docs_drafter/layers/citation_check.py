"""Layer 5: Citation and number check.

Confirms that every claim in a draft is backed by evidence, and that every number and
unit comes from the code:

- Every claim has at least one citation (evidence or silence).
- A diff citation names a file the PR changed, a line that exists in the diff on the
  stated side, and a quote that appears on that line.
- A fact citation, or a placeholder, names a fact from layer 3 that has an exact value.
- Numbers and units appear only through placeholders. A plain number ("30 minutes"), a
  number written as a word next to a unit ("thirty minutes"), or a unit written after a
  placeholder ("{{fact:x.default}} mmol/L") fails.

On failure: reject the draft. Any problem in any claim rejects the whole draft.

Whether a cited line actually supports what the claim says is a judgement, not a
lookup. That is layer 6's job (the independent verifier).

Plain code; no AI.
"""

import re
from dataclasses import dataclass
from decimal import Decimal

from open_docs_drafter.drafts import Claim, DiffCitation, Draft, FactCitation, Side
from open_docs_drafter.facts import Fact, FactSet, Kind
from open_docs_drafter.models import PullRequest, patch_lines

LAYER = 5
AI_INVOLVED = False

PLACEHOLDER = re.compile(r"\{\{fact:([A-Za-z_]\w*)\.([a-z_]+)(?:\|([a-z]+))?\}\}")
_MODIFIERS = {"percent", "raw"}
_NUMERIC_KINDS = {
    Kind.DEFAULT,
    Kind.JSON_DEFAULT,
    Kind.PICKER_DEFAULT,
    Kind.MIN,
    Kind.MAX,
    Kind.STEP,
}

_UNIT = (
    r"(?:mg/dl|mmol/l|mmol|u/h(?:r|our)?|units?|iu|u|g|grams?|%|percent|"
    r"min(?:ute)?s?|h(?:ou)?rs?|h|seconds?|secs?|s|days?)"
)
_RAW_NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?(?!\w)")
_NUMBER_WORD_WITH_UNIT = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|"
    r"twenty|thirty|forty|fifty|sixty|ninety|hundred|thousand|half|a\s+quarter)"
    r"[\s-]+" + _UNIT + r"(?![\w/])",
    re.IGNORECASE,
)
_UNIT_AFTER_PLACEHOLDER = re.compile(r"\}\}\s*" + _UNIT + r"(?![\w/])", re.IGNORECASE)


@dataclass(frozen=True)
class Problem:
    code: str
    detail: str


@dataclass(frozen=True)
class ClaimResult:
    claim: Claim
    problems: tuple[Problem, ...]
    rendered: str | None  # The claim with placeholders filled, if it passed.

    @property
    def ok(self) -> bool:
        return not self.problems


@dataclass(frozen=True)
class CitationCheckResult:
    claims: tuple[ClaimResult, ...]

    @property
    def accepted(self) -> bool:
        return bool(self.claims) and all(c.ok for c in self.claims)

    @property
    def problems(self) -> list[Problem]:
        return [p for c in self.claims for p in c.problems]


def check_draft(draft: Draft, pr: PullRequest, facts: FactSet) -> CitationCheckResult:
    """Check every claim. The draft is accepted only if every claim passes."""
    diff_index = _index_diff(pr)
    results = tuple(_check_claim(c, diff_index, facts) for c in draft.claims)
    if not results:
        empty = Claim("(empty draft)")
        results = (ClaimResult(empty, (Problem("empty-draft", "the draft has no claims"),), None),)
    return CitationCheckResult(results)


# ------------------------------------------------------------------ one claim


def _check_claim(
    claim: Claim, diff_index: dict[tuple[str, Side, int], str], facts: FactSet
) -> ClaimResult:
    problems: list[Problem] = []
    placeholders = list(PLACEHOLDER.finditer(claim.text))

    if not claim.citations and not placeholders:
        problems.append(Problem("no-citation", f"no evidence cited for: {claim.text!r}"))

    for c in claim.citations:
        if isinstance(c, DiffCitation):
            problems.extend(_check_diff_citation(c, diff_index))
        else:
            problems.extend(_check_fact_citation(c, facts))

    problems.extend(_check_text(claim.text))

    rendered_parts: list[str] = []
    last = 0
    for m in placeholders:
        rendered_parts.append(claim.text[last : m.start()])
        value, problem = _render(m, facts)
        if problem:
            problems.append(problem)
        rendered_parts.append(value or m.group(0))
        last = m.end()
    rendered_parts.append(claim.text[last:])

    rendered = "".join(rendered_parts) if not problems else None
    return ClaimResult(claim, tuple(problems), rendered)


def _check_diff_citation(
    c: DiffCitation, diff_index: dict[tuple[str, Side, int], str]
) -> list[Problem]:
    if not any(path == c.path for path, _, _ in diff_index):
        return [Problem("unknown-file", f"{c.path} is not changed by this PR")]
    line = diff_index.get((c.path, c.side, c.line))
    if line is None:
        return [Problem("line-not-in-diff", f"{c.path}:{c.line} ({c.side}) is not in the diff")]
    if _squash(c.quote) not in _squash(line):
        return [
            Problem(
                "quote-mismatch",
                f"{c.path}:{c.line} ({c.side}) does not contain {c.quote!r}; "
                f"it reads {line.strip()!r}",
            )
        ]
    return []


def _check_fact_citation(c: FactCitation, facts: FactSet) -> list[Problem]:
    _, problem = _lookup(c.setting, c.kind, facts)
    return [problem] if problem else []


def _check_text(text: str) -> list[Problem]:
    problems = []
    without = PLACEHOLDER.sub(" ", text)
    if "{{" in without or "}}" in without:
        problems.append(Problem("bad-placeholder", f"malformed placeholder in {text!r}"))
    raw = _RAW_NUMBER.findall(without)
    if raw:
        problems.append(
            Problem("raw-number", f"numbers must come from facts, not text: {', '.join(raw)}")
        )
    words = _NUMBER_WORD_WITH_UNIT.search(without)
    if words:
        problems.append(Problem("raw-number", f"number written as words: {words.group(0)!r}"))
    unit = _UNIT_AFTER_PLACEHOLDER.search(text)
    if unit:
        problems.append(
            Problem(
                "unit-after-placeholder",
                f"units must come from the fact, not text: {unit.group(0)[2:].strip()!r}",
            )
        )
    return problems


# ------------------------------------------------------------------ facts and placeholders


def _lookup(setting: str, kind: str, facts: FactSet) -> tuple[Fact | None, Problem | None]:
    try:
        k = Kind(kind)
    except ValueError:
        return None, Problem("unknown-fact", f"{setting}.{kind}: no such kind of fact")
    found = facts.get(setting, k)
    if not found:
        return None, Problem("unknown-fact", f"{setting}.{kind}: no such fact in the code")
    if any(f.value is None for f in found):
        reason = next(f.needs_human for f in found if f.value is None)
        return None, Problem("fact-needs-human", f"{setting}.{kind}: {reason}")
    if len({f.value for f in found}) > 1:
        cites = ", ".join(f"{f.value} ({f.citation})" for f in found)
        return None, Problem("ambiguous-fact", f"{setting}.{kind} has several values: {cites}")
    return found[0], None


def _render(m: re.Match[str], facts: FactSet) -> tuple[str | None, Problem | None]:
    setting, kind, modifier = m.group(1), m.group(2), m.group(3)
    fact, problem = _lookup(setting, kind, facts)
    if problem or fact is None or fact.value is None:
        return None, problem
    if modifier is not None and modifier not in _MODIFIERS:
        return None, Problem("bad-placeholder", f"unknown modifier |{modifier} in {m.group(0)}")
    if fact.kind not in _NUMERIC_KINDS:
        if modifier:
            return None, Problem("bad-placeholder", f"|{modifier} only applies to numbers")
        return fact.value, None

    unit = fact.unit or _unit_of(setting, facts)
    if modifier == "raw":
        return fact.value, None
    if modifier == "percent":
        if unit != "factor" or fact.number is None:
            return None, Problem("bad-placeholder", f"|percent needs a factor: {m.group(0)}")
        return f"{_plain(fact.number * 100)}%", None
    if unit and unit != "factor":
        return f"{fact.value} {unit}", None
    return fact.value, None


def _unit_of(setting: str, facts: FactSet) -> str | None:
    unit = facts.one(setting, Kind.UNIT)
    return unit.value if unit else None


def _plain(number: Decimal) -> str:
    text = format(number.normalize(), "f")
    return text


# ------------------------------------------------------------------ diff lines


def _index_diff(pr: PullRequest) -> dict[tuple[str, Side, int], str]:
    index: dict[tuple[str, Side, int], str] = {}
    for f in pr.files:
        index.setdefault((f.path, Side.NEW, 0), "")  # marks the file as part of the PR
        for line in patch_lines(f.patch):
            if line.new_line is not None:
                index[(f.path, Side.NEW, line.new_line)] = line.text
            if line.old_line is not None:
                index[(f.path, Side.OLD, line.old_line)] = line.text
    return index


def _squash(text: str) -> str:
    return " ".join(text.split())
