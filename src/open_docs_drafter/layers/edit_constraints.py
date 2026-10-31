"""Layer 7: Edit constraints.

Applies a draft's edits to the current docs pages and rejects the draft if any edit:

- targets a page the profile doesn't allow (English source pages only; no new files, no
  config or navigation files, no translations)
- has no anchor, or an anchor that isn't whole lines appearing exactly once in the page
- is larger than the size limits
- removes, changes or downgrades an existing warning box, or puts text inside one
- adds text in a non-Latin script (the docs source is English)

It runs after layer 5, on the claims as layer 5 rendered them. A draft that layer 5
rejected is rejected here too.

On failure: reject the draft. Plain code; no AI.
"""

import re
import unicodedata
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from fnmatch import fnmatchcase

from open_docs_drafter.admonitions import Admonition, protected_admonitions
from open_docs_drafter.drafts import DocEdit, Draft, Operation
from open_docs_drafter.layers.citation_check import CitationCheckResult
from open_docs_drafter.profile import EditLimits, Profile

LAYER = 7
AI_INVOLVED = False


@dataclass(frozen=True)
class Problem:
    code: str
    detail: str


@dataclass(frozen=True)
class EditCheckResult:
    problems: tuple[Problem, ...]
    new_pages: dict[str, str]  # Page path -> full new text. Empty if rejected.

    @property
    def accepted(self) -> bool:
        return not self.problems


def check_edits(
    profile: Profile,
    draft: Draft,
    citations: CitationCheckResult,
    pages: Mapping[str, str],
) -> EditCheckResult:
    """Apply the draft to `pages` (path -> current text) and check every constraint."""
    problems: list[Problem] = []
    limits = profile.docs.limits

    if not citations.accepted:
        problems.append(Problem("citation-check-failed", "layer 5 rejected this draft"))
        return EditCheckResult(tuple(problems), {})

    rendered = [c.rendered for c in citations.claims]
    if len(rendered) != len(draft.claims) or any(r is None for r in rendered):
        problems.append(Problem("citation-check-failed", "claims don't match layer 5's result"))
        return EditCheckResult(tuple(problems), {})

    if len(draft.edits) > limits.max_edits:
        problems.append(
            Problem("too-many-edits", f"{len(draft.edits)} edits; the limit is {limits.max_edits}")
        )

    new_pages: dict[str, str] = {}
    position = 0
    total_added = 0
    for i, edit in enumerate(draft.edits):
        texts = [r or "" for r in rendered[position : position + len(edit.claims)]]
        position += len(edit.claims)
        where = f"edit {i + 1} ({edit.doc_path})"

        page_problems = _check_page(profile, edit, pages, where)
        problems.extend(page_problems)
        if page_problems:
            continue

        content = "\n\n".join(texts)
        total_added += len(content)
        problems.extend(_check_size(edit, content, limits, where))
        problems.extend(_check_script(content, where))
        problems.extend(_check_markdown(texts, where))

        current = new_pages.get(edit.doc_path, pages[edit.doc_path])
        applied, apply_problem = _apply(edit, current, content, limits, where)
        if apply_problem:
            problems.append(apply_problem)
            continue
        new_pages[edit.doc_path] = applied

    if total_added > limits.max_added_chars_total:
        problems.append(
            Problem(
                "draft-too-large",
                f"{total_added} characters added; the limit is {limits.max_added_chars_total}",
            )
        )

    for path, new_text in new_pages.items():
        problems.extend(_check_warnings(path, pages[path], new_text))
        already_hidden = {p.detail for p in _hidden_warnings(path, pages[path])}
        problems.extend(
            p for p in _hidden_warnings(path, new_text) if p.detail not in already_hidden
        )

    return EditCheckResult(tuple(problems), {} if problems else new_pages)


# ------------------------------------------------------------------ checks


def _check_page(
    profile: Profile, edit: DocEdit, pages: Mapping[str, str], where: str
) -> list[Problem]:
    docs = profile.docs
    path = edit.doc_path
    allowed = any(fnmatchcase(path, p) for p in docs.paths) and not any(
        fnmatchcase(path, p) for p in docs.exclude
    )
    if not allowed or not path.endswith(".md"):
        return [Problem("page-not-allowed", f"{where}: not an editable English source page")]
    if path not in pages:
        return [Problem("unknown-page", f"{where}: page doesn't exist; new pages need a human")]
    if not edit.claims:
        return [Problem("empty-edit", f"{where}: no claims")]
    if edit.anchor is None:
        return [Problem("no-anchor", f"{where}: an edit must say where it goes")]
    return []


def _check_size(edit: DocEdit, content: str, limits: EditLimits, where: str) -> list[Problem]:
    problems = []
    if len(edit.claims) > limits.max_claims_per_edit:
        problems.append(
            Problem(
                "edit-too-large",
                f"{where}: {len(edit.claims)} claims; the limit is {limits.max_claims_per_edit}",
            )
        )
    if len(content) > limits.max_added_chars_per_edit:
        problems.append(
            Problem(
                "edit-too-large",
                f"{where}: {len(content)} characters; "
                f"the limit is {limits.max_added_chars_per_edit}",
            )
        )
    return problems


_UNSAFE_MARKDOWN = re.compile(
    r"<!--|-->|```|~~~|</?[A-Za-z][^>]*>|^\s*(?:!!!|\?\?\?)|^[ \t]|^\s*\[[^\]]+\]:\s",
    re.MULTILINE,
)


def _check_markdown(texts: list[str], where: str) -> list[Problem]:
    """Claims are one line of plain prose (inline `code`, **bold** and links are fine).

    Anything structural could hide or swallow the text around it: an HTML comment or an
    unclosed code fence before a warning box hides the box without changing its text.
    """
    for text in texts:
        if "\n" in text or "\r" in text:
            return [Problem("unsafe-markdown", f"{where}: a claim must be one line")]
        m = _UNSAFE_MARKDOWN.search(text)
        if m:
            return [
                Problem(
                    "unsafe-markdown",
                    f"{where}: claims can't contain {m.group(0).strip()!r} "
                    "(HTML, comments, code fences, indentation or boxes)",
                )
            ]
    return []


def _hidden_warnings(path: str, page: str) -> list[Problem]:
    """Protected boxes that sit inside an HTML comment or a fenced code block."""
    problems = []
    lines = page.splitlines()
    in_fence = False
    in_comment = False
    hidden_lines: set[int] = set()
    for number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if in_comment or in_fence:
            hidden_lines.add(number)
        if not in_comment and stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if not in_fence:
            start = line.rfind("<!--")
            end = line.rfind("-->")
            if start > end:
                in_comment = True
            elif end > start and in_comment:
                in_comment = False
    for box in protected_admonitions(page):
        if box.start_line in hidden_lines:
            problems.append(
                Problem(
                    "warning-hidden",
                    f"{path}: the warning box {box.title!r} is inside a comment or code block",
                )
            )
    return problems


def _check_script(content: str, where: str) -> list[Problem]:
    for ch in content:
        if ch.isalpha() and not unicodedata.name(ch, "").startswith("LATIN"):
            return [Problem("non-english-text", f"{where}: contains {ch!r}; the source is English")]
    return []


def _apply(
    edit: DocEdit, page: str, content: str, limits: EditLimits, where: str
) -> tuple[str, Problem | None]:
    anchor = (edit.anchor or "").strip("\n")
    if not anchor.strip():
        return page, Problem("no-anchor", f"{where}: the anchor is blank")
    count = page.count(anchor)
    if count == 0:
        return page, Problem("anchor-not-found", f"{where}: anchor not found in the page")
    if count > 1:
        return page, Problem("anchor-ambiguous", f"{where}: anchor appears {count} times")
    start = page.index(anchor)
    end = start + len(anchor)
    if (start > 0 and page[start - 1] != "\n") or (end < len(page) and page[end] != "\n"):
        return page, Problem("anchor-not-whole-lines", f"{where}: anchor must be whole lines")

    if edit.operation is Operation.REPLACE:
        removed = anchor.count("\n") + 1
        if removed > limits.max_replaced_lines:
            return page, Problem(
                "edit-too-large",
                f"{where}: replaces {removed} lines; the limit is {limits.max_replaced_lines}",
            )
        return page[:start] + content + page[end:], None
    if edit.operation is Operation.INSERT_BEFORE:
        return page[:start] + content + "\n\n" + page[start:], None
    return page[:end] + "\n\n" + content + page[end:], None


def _check_warnings(path: str, old: str, new: str) -> list[Problem]:
    """Every protected box in the old page must appear, word for word, in the new page,
    under the same parent line.

    The parent matters for nested boxes: text inserted between a list item and the box
    under it ends the list, and the indented box then renders as a code block.
    """
    before = Counter(_box_in_context(old, a) for a in protected_admonitions(old))
    after = Counter(_box_in_context(new, a) for a in protected_admonitions(new))
    problems = []
    for (text, parent), count in before.items():
        if after[(text, parent)] < count:
            title = text.splitlines()[0].strip()
            moved = any(t == text for t, _ in after)
            problems.append(
                Problem(
                    "warning-changed",
                    f"{path}: the warning box {title!r} was "
                    + (
                        "separated from the text it belongs to"
                        if moved
                        else "removed, changed or moved into other text"
                    )
                    + "; warning boxes can only be changed by a human",
                )
            )
    return problems


def _box_in_context(page: str, box: Admonition) -> tuple[str, str]:
    """The box's text and its parent: the nearest earlier non-blank line indented less."""
    lines = page.splitlines()
    indent = len(box.text) - len(box.text.lstrip())
    if indent < 4:  # Markdown only nests a block at 4 or more spaces.
        return box.text, ""
    for line in reversed(lines[: box.start_line - 1]):
        if line.strip() and len(line) - len(line.lstrip()) < indent:
            return box.text, line
    return box.text, ""
