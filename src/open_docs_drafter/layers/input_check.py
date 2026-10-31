"""Layer 1: Input check.

Cross-checks the pull request's title and description against the actual diff, and
removes or rejects text that could steer later layers. The title and description are
written by whoever opened the pull request, so they are untrusted data.

On failure: discard the title and description, and use the diff only.

Findings come in two severities:
- DISCARD: the text is not used at all by later layers.
- NOTE: the text was cleaned and is still used. Cleaning removes HTML comments and
  invisible characters, and replaces any number-with-unit that the diff doesn't contain.

Everything here is plain code with fixed patterns. It can't catch every trick, so it is
one layer of several: later layers never treat PR text as instructions, and only the diff
counts as evidence.
"""

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath

from open_docs_drafter.layers.triage import rule_based_tier
from open_docs_drafter.models import PullRequest, changed_lines
from open_docs_drafter.profile import Profile
from open_docs_drafter.tiers import Tier

LAYER = 1
AI_INVOLVED = False

MAX_TEXT_CHARS = 20_000


class Severity(StrEnum):
    DISCARD = "discard"
    NOTE = "note"


@dataclass(frozen=True)
class Finding:
    code: str
    severity: Severity
    detail: str


@dataclass(frozen=True)
class InputCheckResult:
    title: str | None  # Cleaned title, or None if discarded.
    description: str | None  # Cleaned description, or None if discarded.
    findings: tuple[Finding, ...]
    diff_tier: Tier  # Tier from changed files and diff lines only, ignoring PR text.

    @property
    def discarded(self) -> bool:
        return any(f.severity is Severity.DISCARD for f in self.findings)


# ------------------------------------------------------------------ patterns

# Bidirectional overrides and Unicode tag characters have no place in a PR description
# and can hide or reorder text. Their presence alone discards the text.
_DANGEROUS_CHARS = re.compile("[‪-‮⁦-⁩\U000e0000-\U000e007f]")

_HTML_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.DOTALL)

_HIDDEN_HTML = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(?![.\d])"
    r"|opacity\s*:\s*0(?![.\d])|<[a-z]+[^>]*\shidden(?:[\s>=/])",
    re.IGNORECASE,
)

_INSTRUCTION_PATTERNS = [
    r"\b(?:ignore|disregard|forget|override)\s+(?:all\s+|any\s+|the\s+|your\s+)*"
    r"(?:previous|prior|above|earlier|preceding|system|original)\s+"
    r"(?:instructions?|prompts?|rules?|messages?|context|guidelines?)",
    r"\b(?:ignore|disregard|forget)\s+(?:everything\s+|all\s+|anything\s+)?(?:the\s+)?"
    r"(?:above|preceding|before\s+this)\b",
    r"\b(?:ignore|disregard|forget|override|bypass)\s+(?:all\s+)?(?:your|safety)\s+"
    r"(?:instructions?|rules?|guidelines?|guardrails?|checks?|prompts?|constraints?)\b",
    r"\b(?:new|updated|real|actual|hidden)\s+instructions?\s*:",
    # Speaking to the tool or a model directly.
    # Not "model": Trio has a Model/ folder, so "Model: ..." is normal developer text.
    r"^\s*(?:ai|llm|bot|assistant|claude|gpt|chatgpt|copilot|gemini)\s*[:,]",
    r"\b(?:dear|hey|hi|hello)\s+(?:the\s+)?(?:documentation\s+|docs\s+|review\s+)?"
    r"(?:bot|ai|assistant|llm|model|drafter)\b",
    r"\b(?:documentation|docs)\s+(?:bot|ai|assistant|llm)\b",
    r"\b(?:when|while)\s+(?:summari[sz]ing|drafting|documenting|writing\s+(?:the\s+)?"
    r"(?:docs|documentation|release\s+notes))\b",
    r"\bpretend\s+(?:you\s+are|to\s+be)\b",
    r"\b(?:act|behave|respond)\s+as\s+(?:if\s+you\s+(?:are|were)\b|an?\s+(?:ai|assistant|"
    r"admin(?:istrator)?|maintainer|reviewer|system|developer)\b)",
    r"\b(?:system|developer)\s+(?:prompt|message|instructions?)\b",
    r"^\s*(?:system|assistant)\s*:",
    r"<\|?(?:im_start|im_end|system|endoftext|eot_id)\|?>",
    r"\[/?INST\]",
    r"\byou\s+are\s+(?:now\s+)?(?:an?\s+|the\s+)?(?:ai|assistant|language\s+model|llm|model|chatbot|bot)\b",
    r"\bnote\s+(?:to|for)\s+(?:the\s+)?(?:ai|llm|bot|model|assistant|reviewer\s+bot|drafter)\b",
    r"\b(?:classify|mark|treat|label|tag|set|tier)\s+(?:this|the|it)?\s*"
    r"(?:pr|change|pull\s+request|diff)?\s*(?:as|to)\s+(?:green|safe|low[- ]risk|amber|trivial)\b",
    r"\btier\s*[:=]\s*(?:green|amber)\b",
    r"\bdo\s+not\s+(?:flag|escalate|mention|report|cite|warn|tier)\b",
    r"\b(?:no|skip|without)\s+(?:human\s+)?review\s+(?:is\s+)?(?:needed|required|necessary)\b",
    r"\b(?:respond|reply|answer|output|write)\s+only\s+(?:with|the)\b",
    r"\b(?:remove|delete|drop|soften)\s+(?:the|any|all)?\s*(?:warnings?|cautions?|caution\s+box(?:es)?)\b",
]
_INSTRUCTIONS = re.compile("|".join(f"(?:{p})" for p in _INSTRUCTION_PATTERNS), re.I | re.M)

# Requests about what the docs should say. Often honest ("the docs should mention the new
# toggle"), so only noted; any claim must still be backed by the diff in layer 5.
_DOCS_DIRECTIVE = re.compile(
    r"\b(?:the\s+)?(?:docs?|documentation|release\s+notes?|wiki)\s+"
    r"(?:should|must|needs?\s+to|has\s+to|will\s+need\s+to)\s+"
    r"(?:say|state|mention|describe|claim|read|explain|note)\b",
    re.IGNORECASE,
)

# Claims that a change is harmless. Checked against the diff's own tier.
_SCOPE_CLAIM = re.compile(
    r"\b(?:ui[- ]only|cosmetic(?:\s+changes?)?(?:\s+only)?|no\s+functional\s+changes?"
    r"|no\s+(?:behaviou?r|logic|algorithm)\s+changes?|docs?[- ]only|documentation[- ]only"
    r"|(?:just|only)\s+a\s+typo|typo\s+fix(?:es)?|fix(?:es)?\s+(?:a\s+)?typos?"
    r"|pure\s+refactor(?:ing)?|refactor(?:ing)?[- ]only|formatting[- ]only|text[- ]only"
    r"|wording[- ]only|copy[- ]only|visual[- ]only|minor\s+ui(?:\s+(?:change|tweak)s?)?)\b",
    re.IGNORECASE,
)

# Numbers with units that matter for therapy. Each must appear in the changed lines.
_NUMBER_WITH_UNIT = re.compile(
    r"(?<![\w.,])(\d+(?:[.,]\d+)?)\s*"
    r"(mg/dl|mmol/l|mmol|u/h(?:r|our)?|units?|iu|u|g|grams?|%|percent|"
    r"min(?:ute)?s?|h(?:ou)?rs?|h)(?![\w/])",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?(?![\d])")

_FILE_REFERENCE = re.compile(
    r"(?<![\w/.-])([\w./-]+\.(?:swift|js|ts|json|kt|java|py|ya?ml|md|plist|xcstrings|strings|m|h))\b"
)


# ------------------------------------------------------------------ the check


def check_input(profile: Profile, pr: PullRequest) -> InputCheckResult:
    findings: list[Finding] = []
    title = _clean(pr.title, "title", findings)
    body = _clean(pr.body, "description", findings)
    text = f"{title}\n{body}"

    diff_lines = [line for f in pr.files for line in changed_lines(f.patch)]
    diff_tier = rule_based_tier(profile, [f.path for f in pr.files], diff_lines).tier

    _check_instructions(pr.title, pr.body, findings)
    _check_scope_claims(text, diff_tier, findings)
    directive = _DOCS_DIRECTIVE.search(text)
    if directive:
        findings.append(
            Finding(
                "docs-directive",
                Severity.NOTE,
                f"text tells the docs what to say: {directive.group(0)!r}; treat as a hint only",
            )
        )
    _check_file_references(text, [f.path for f in pr.files], findings)
    missing: list[str] = []
    title = _redact_numbers(title, diff_lines, missing)
    body = _redact_numbers(body, diff_lines, missing)
    if missing:
        findings.append(
            Finding(
                "unverified-number",
                Severity.NOTE,
                "redacted numbers with units not found in the changed lines: "
                + ", ".join(missing[:5]),
            )
        )

    discarded = any(f.severity is Severity.DISCARD for f in findings)
    return InputCheckResult(
        title=None if discarded else title,
        description=None if discarded else body,
        findings=tuple(findings),
        diff_tier=diff_tier,
    )


def _clean(raw: str, field: str, findings: list[Finding]) -> str:
    if _DANGEROUS_CHARS.search(raw):
        findings.append(
            Finding(
                "hidden-unicode",
                Severity.DISCARD,
                f"{field} contains bidirectional-override or tag characters",
            )
        )
    if _HIDDEN_HTML.search(raw):
        findings.append(
            Finding(
                "hidden-html", Severity.DISCARD, f"{field} contains HTML styled to be invisible"
            )
        )

    text = _normalise(raw)
    if text != unicodedata.normalize("NFKC", raw):
        findings.append(
            Finding(
                "invisible-characters", Severity.NOTE, f"removed invisible characters from {field}"
            )
        )

    without_comments = _HTML_COMMENT.sub("", text)
    if without_comments != text:
        findings.append(
            Finding("html-comment", Severity.NOTE, f"removed HTML comments from {field}")
        )
    text = without_comments.strip()

    if len(text) > MAX_TEXT_CHARS:
        findings.append(
            Finding("too-long", Severity.NOTE, f"{field} cut to {MAX_TEXT_CHARS} characters")
        )
        text = text[:MAX_TEXT_CHARS]
    return text


def _normalise(text: str) -> str:
    """NFKC (folds look-alike letters such as full-width), minus invisible format characters."""
    text = unicodedata.normalize("NFKC", text)
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


def _check_instructions(raw_title: str, raw_body: str, findings: list[Finding]) -> None:
    # Scan the normalised text with comments still in, so nothing hidden in them is missed.
    for field, raw in (("title", raw_title), ("description", raw_body)):
        match = _INSTRUCTIONS.search(_normalise(raw))
        if match:
            findings.append(
                Finding(
                    "embedded-instructions",
                    Severity.DISCARD,
                    f"{field} contains instruction-like text: {match.group(0).strip()!r}",
                )
            )


def _check_scope_claims(text: str, diff_tier: Tier, findings: list[Finding]) -> None:
    match = _SCOPE_CLAIM.search(text)
    if not match or diff_tier is Tier.GREEN:
        return
    claim = match.group(0)
    if diff_tier is Tier.RED:
        findings.append(
            Finding(
                "scope-claim-contradicts-diff",
                Severity.DISCARD,
                f"text claims {claim!r} but the diff itself is red tier",
            )
        )
    else:
        findings.append(
            Finding(
                "scope-claim-unconfirmed",
                Severity.NOTE,
                f"text claims {claim!r} but the diff is {diff_tier.name.lower()} tier",
            )
        )


REDACTED_NUMBER = "[number not in diff]"


def _redact_numbers(text: str, diff_lines: list[str], missing: list[str]) -> str:
    """Replace each number-with-unit that the changed lines don't contain.

    PR descriptions often hold worked examples and test steps ("added 10 g carb"), so the
    rest of the text stays. Later layers never see the number; any number in the docs
    must come from the code (layer 3).
    """
    in_diff = {_number_key(n) for line in diff_lines for n in _NUMBER.findall(line)}

    def replace(match: re.Match[str]) -> str:
        if _number_key(match.group(1)) in in_diff:
            return match.group(0)
        missing.append(match.group(0).strip())
        return REDACTED_NUMBER

    return _NUMBER_WITH_UNIT.sub(replace, text)


def _number_key(number: str) -> str:
    """'5,50' and '5.5' compare equal; '05' and '5' too."""
    value = number.replace(",", ".")
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    return value.lstrip("0") or "0"


def _check_file_references(text: str, changed: list[str], findings: list[Finding]) -> None:
    names = {PurePosixPath(p).name.lower() for p in changed}
    paths = [p.lower() for p in changed]
    unknown = []
    for ref in dict.fromkeys(_FILE_REFERENCE.findall(text)):
        ref_l = ref.lower().lstrip("./")
        if PurePosixPath(ref_l).name not in names and not any(p.endswith(ref_l) for p in paths):
            unknown.append(ref)
    if unknown:
        findings.append(
            Finding(
                "unmatched-file-reference",
                Severity.NOTE,
                "files mentioned but not changed: " + ", ".join(unknown[:5]),
            )
        )
