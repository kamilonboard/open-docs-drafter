from pathlib import Path
from typing import Any

import pytest

from open_docs_drafter.admonitions import find_admonitions, protected_admonitions
from open_docs_drafter.drafts import Claim, DiffCitation, DocEdit, Draft, Operation, Side
from open_docs_drafter.facts import FactSet
from open_docs_drafter.layers.citation_check import check_draft
from open_docs_drafter.layers.edit_constraints import check_edits
from open_docs_drafter.models import ChangedFile, PullRequest
from open_docs_drafter.profile import ProfileError, load_profile, parse_profile

PAGE_PATH = "docs/configuration/settings/features/remote-control.md"
PAGE = (Path(__file__).parent / "fixtures" / "triodocs" / "remote-control.md").read_text()
PAGES = {PAGE_PATH: PAGE, "docs/includes/snippet.md": "Shared.\n"}
TRIO = load_profile(Path(__file__).parent.parent / "profiles" / "trio" / "profile.yaml")

CODE = "Trio/Sources/Services/RemoteControl/RemoteBolus.swift"
PR = PullRequest(
    1,
    "Remote bolus limit",
    "",
    "",
    (ChangedFile(CODE, "@@ -10 +10 @@\n-old\n+limitRemoteBolus()"),),
)
CITE = (DiffCitation(CODE, 10, Side.NEW, "limitRemoteBolus"),)


def claim(text: str = "Remote bolus now respects the looping phone's limits.") -> Claim:
    return Claim(text, CITE)


def run(*edits: DocEdit, profile=TRIO, pages=PAGES):  # type: ignore[no-untyped-def]
    draft = Draft(edits)
    citations = check_draft(draft, PR, FactSet([]))
    assert citations.accepted, citations.problems
    return check_edits(profile, draft, citations, pages)


def codes(result) -> set[str]:  # type: ignore[no-untyped-def]
    return {p.code for p in result.problems}


def edit(
    anchor: str | None,
    *claims: Claim,
    op: Operation = Operation.INSERT_AFTER,
    path: str = PAGE_PATH,
) -> DocEdit:
    return DocEdit(path, claims or (claim(),), op, anchor)


# ------------------------------------------------------------------ finding warning boxes


def test_finds_top_level_and_nested_boxes() -> None:
    boxes = find_admonitions(PAGE)
    assert [(a.kind, a.start_line) for a in boxes] == [("danger", 9), ("tip", 15), ("warning", 23)]
    assert [a.kind for a in protected_admonitions(PAGE)] == ["danger", "warning"]


def test_box_body_includes_blank_lines_and_list() -> None:
    danger = protected_admonitions(PAGE)[0]
    assert danger.text.endswith("Check current blood glucose and IOB before sending")
    assert "\n\n" in danger.text


# ------------------------------------------------------------------ accepted edits


def test_insert_after_a_paragraph() -> None:
    result = run(edit("Remote bolus amounts are limited by the looping phone's settings."))
    assert result.accepted, result.problems
    assert (
        result.new_pages[PAGE_PATH]
        .rstrip()
        .endswith("Remote bolus now respects the looping phone's limits.")
    )


def test_insert_after_a_warning_box_keeps_it_intact() -> None:
    anchor = "    - Check current blood glucose and IOB before sending"
    result = run(edit(anchor))
    assert result.accepted, result.problems


def test_replace_a_plain_paragraph() -> None:
    result = run(
        edit("Remote bolus sends a bolus command to the looping phone.", op=Operation.REPLACE)
    )
    assert result.accepted
    assert "Remote bolus sends a bolus command" not in result.new_pages[PAGE_PATH]


def test_two_edits_on_the_same_page_apply_in_order() -> None:
    result = run(
        edit("## Limits", claim("First.")),
        edit("First.", claim("Second.")),
    )
    assert result.accepted, result.problems
    page = result.new_pages[PAGE_PATH]
    assert page.index("First.") < page.index("Second.")


def test_original_pages_are_not_modified() -> None:
    run(edit("## Limits"))
    assert PAGES[PAGE_PATH] == PAGE


# ------------------------------------------------------------------ warning boxes are protected


@pytest.mark.parametrize(
    ("anchor", "op", "why"),
    [
        ('!!! danger "Important Safety Note"', Operation.REPLACE, "downgrade or delete the opener"),
        ("    - Verify the bolus amount before sending", Operation.REPLACE, "edit a line inside"),
        ("    - Verify the bolus amount before sending", Operation.INSERT_AFTER, "split the box"),
        (
            "        Only share the shared secret with people you trust.",
            Operation.REPLACE,
            "nested box",
        ),
        ("    !!! warning", Operation.INSERT_AFTER, "insert between opener and body"),
    ],
)
def test_warning_boxes_cannot_be_changed(anchor: str, op: Operation, why: str) -> None:
    result = run(edit(anchor, op=op))
    assert not result.accepted, why
    assert "warning-changed" in codes(result)
    assert result.new_pages == {}


def test_replacing_a_whole_warning_box_is_rejected() -> None:
    box = protected_admonitions(PAGE)[1].text
    result = run(edit(box, claim("Share the secret freely."), op=Operation.REPLACE))
    assert "warning-changed" in codes(result)


def test_tip_boxes_are_not_protected() -> None:
    result = run(edit("    You can add Remote Control to the home screen.", op=Operation.REPLACE))
    assert result.accepted


# ------------------------------------------------------------------ anchors


@pytest.mark.parametrize(
    ("anchor", "code"),
    [
        (None, "no-anchor"),
        ("\n", "no-anchor"),
        ("This text is not on the page.", "anchor-not-found"),
        ("Remote bolus", "anchor-ambiguous"),
        ("Trio can be controlled", "anchor-not-whole-lines"),
    ],
)
def test_bad_anchors(anchor: str | None, code: str) -> None:
    assert code in codes(run(edit(anchor)))


def test_anchor_with_trailing_newline_is_fine() -> None:
    assert run(edit("## Limits\n")).accepted


# ------------------------------------------------------------------ pages


@pytest.mark.parametrize(
    ("path", "code"),
    [
        ("mkdocs.yml", "page-not-allowed"),
        ("README.md", "page-not-allowed"),
        ("docs/includes/snippet.md", "page-not-allowed"),
        ("docs/new-page.md", "unknown-page"),
    ],
)
def test_page_rules(path: str, code: str) -> None:
    assert code in codes(run(edit("Shared.", path=path)))


def test_profile_without_docs_section_allows_nothing() -> None:
    bare = parse_profile(
        {
            "profile_version": 1,
            "project": {
                "name": "X",
                "code_repo": "a/b",
                "docs_repo": "a/c",
                "docs_branch": "main",
                "docs_format": "mkdocs",
            },
        }
    )
    assert "page-not-allowed" in codes(run(edit("## Limits"), profile=bare))


# ------------------------------------------------------------------ size and language


def test_too_many_claims() -> None:
    claims = [claim(f"Point {chr(65 + i)}.") for i in range(9)]
    assert "edit-too-large" in codes(run(edit("## Limits", *claims)))


def test_too_many_characters() -> None:
    long = claim("Remote bolus " * 120 + "ends.")
    assert "edit-too-large" in codes(run(edit("## Limits", long)))


def test_too_many_replaced_lines() -> None:
    anchor = "## Setup\n\n1. Open **Settings** on the looping phone.\n2. Turn on Remote Control.\n\n    !!! warning\n        Only share the shared secret with people you trust."
    assert "edit-too-large" in codes(run(edit(anchor, op=Operation.REPLACE)))


def test_too_many_edits() -> None:
    edits = [edit("## Limits", claim(f"Note {chr(65 + i)}.")) for i in range(6)]
    assert "too-many-edits" in codes(run(*edits))


@pytest.mark.parametrize("text", ["Удаленный болюс.", "リモートボーラス。", "Fernbolus 遠隔."])
def test_non_latin_text_rejected(text: str) -> None:
    assert "non-english-text" in codes(run(edit("## Limits", claim(text))))


def test_accented_latin_is_fine() -> None:
    assert run(edit("## Limits", claim("Works with the Omnipod DASH® café profile."))).accepted


# ------------------------------------------------------------------ layer order


def test_draft_rejected_by_layer_5_is_rejected() -> None:
    draft = Draft((edit("## Limits", Claim("Uncited claim.")),))
    citations = check_draft(draft, PR, FactSet([]))
    assert not citations.accepted
    result = check_edits(TRIO, draft, citations, PAGES)
    assert codes(result) == {"citation-check-failed"}


# ------------------------------------------------------------------ profile limits


def _with_limits(limits: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile_version": 1,
        "project": {
            "name": "X",
            "code_repo": "a/b",
            "docs_repo": "a/c",
            "docs_branch": "main",
            "docs_format": "mkdocs",
        },
        "docs": {"paths": ["docs/*.md"], "limits": limits},
    }


def test_profile_can_tighten_limits() -> None:
    profile = parse_profile(_with_limits({"max_claims_per_edit": 2}))
    assert profile.docs.limits.max_claims_per_edit == 2
    assert "edit-too-large" in codes(
        run(edit("## Limits", claim("A."), claim("B."), claim("C.")), profile=profile)
    )


@pytest.mark.parametrize(
    "limits",
    [
        {"max_claims_per_edit": 50},
        {"max_edits": 0},
        {"max_replaced_lines": "many"},
        {"unlimited": True},
    ],
)
def test_profile_cannot_loosen_limits(limits: dict[str, Any]) -> None:
    with pytest.raises(ProfileError):
        parse_profile(_with_limits(limits))


# ------------------------------------------------------------------ hiding warnings without changing them


@pytest.mark.parametrize(
    "text",
    [
        "See below. <!--",
        "Example: ```",
        "Note: <details><summary>More</summary>",
        "    Indented text joins the box above.",
        '!!! note "Safer"',
        "First line.\nSecond line.",
        "[safety]: https://example.com",
    ],
)
def test_structural_markdown_in_claims_is_rejected(text: str) -> None:
    result = run(edit("Remote bolus sends a bolus command to the looping phone.", claim(text)))
    assert "unsafe-markdown" in codes(result)


@pytest.mark.parametrize(
    "text",
    [
        "Use the **Remote Control** toggle in `Settings`.",
        "See [Remote Control](remote-control.md) for setup.",
    ],
)
def test_inline_markdown_is_fine(text: str) -> None:
    assert run(edit("## Limits", claim(text))).accepted


def test_warning_hidden_in_comment_is_detected() -> None:
    from open_docs_drafter.layers.edit_constraints import _hidden_warnings

    page = "Intro <!-- hidden\n\n!!! danger\n    Real insulin.\n\n-->\n"
    assert [p.code for p in _hidden_warnings("p.md", page)] == ["warning-hidden"]
    fenced = "```\n!!! warning\n    Careful.\n```\n"
    assert [p.code for p in _hidden_warnings("p.md", fenced)] == ["warning-hidden"]
    assert _hidden_warnings("p.md", PAGE) == []


def test_nested_warning_cannot_be_detached_from_its_list_item() -> None:
    result = run(edit("2. Turn on Remote Control."))
    assert "warning-changed" in codes(result)
    assert any("separated" in p.detail for p in result.problems)


def test_inserting_after_the_nested_box_is_fine() -> None:
    assert run(edit("3. Scan the QR code on the remote phone.")).accepted


def test_box_with_stray_leading_space_is_top_level() -> None:
    # Real TrioDocs case (docs/help/faq.md): " !!! important" with one stray space.
    page = 'Intro paragraph.\n\n !!! important "Important"\n    Use at your own risk.\n'
    pages = {**PAGES, "docs/help/faq.md": page}
    assert run(edit("Intro paragraph.", path="docs/help/faq.md"), pages=pages).accepted
