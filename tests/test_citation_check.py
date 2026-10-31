import pytest

from open_docs_drafter.drafts import (
    Claim,
    DiffCitation,
    DocEdit,
    Draft,
    DraftFormatError,
    FactCitation,
    Side,
    parse_draft,
)
from open_docs_drafter.facts import Fact, FactSet, Kind
from open_docs_drafter.layers.citation_check import check_draft
from open_docs_drafter.models import ChangedFile, PullRequest, patch_lines

PICKER = "Trio/Sources/Models/DecimalPickerSettings.swift"
PATCH = (
    "@@ -86,3 +86,3 @@\n"
    "     var smbInterval = PickerSetting(value: 3, step: 1, min: 1, max: 10)\n"
    "-    var maxSMBBasalMinutes = PickerSetting(value: 30, step: 5, min: 15, max: 180)\n"
    "+    var maxSMBBasalMinutes = PickerSetting(value: 30, step: 5, min: 15, max: 240)\n"
    "     var insulinPeakTime = PickerSetting(value: 75)\n"
)
PR = PullRequest(1, "Raise SMB minutes cap", "", "", (ChangedFile(PICKER, PATCH),))


def fact(setting: str, kind: Kind, value: str | None, unit: str | None = None) -> Fact:
    return Fact(
        setting, kind, value, PICKER, 87, "src", unit=unit, needs_human=None if value else "x"
    )


FACTS = FactSet(
    [
        fact("maxSMBBasalMinutes", Kind.MAX, "240", "min"),
        fact("maxSMBBasalMinutes", Kind.MIN, "15", "min"),
        fact("maxSMBBasalMinutes", Kind.UNIT, "min", "min"),
        fact("maxSMBBasalMinutes", Kind.DEFAULT, "30"),
        fact("maxSMBBasalMinutes", Kind.LABEL, "Max SMB Basal Minutes"),
        fact("maxDailySafetyMultiplier", Kind.DEFAULT, "3"),
        fact("maxDailySafetyMultiplier", Kind.UNIT, "factor", "factor"),
        fact("highTarget", Kind.JSON_DEFAULT, "180"),
        fact("computed", Kind.DEFAULT, None),
        fact("dup", Kind.LABEL, "A"),
        fact("dup", Kind.LABEL, "B"),
    ]
)

GOOD_DIFF = DiffCitation(PICKER, 87, Side.NEW, "max: 240")


def check(*claims: Claim):  # type: ignore[no-untyped-def]
    return check_draft(Draft((DocEdit("docs/settings/smb.md", claims),)), PR, FACTS)


def codes(result) -> set[str]:  # type: ignore[no-untyped-def]
    return {p.code for p in result.problems}


# ------------------------------------------------------------------ diff line numbers


def test_patch_line_numbers() -> None:
    lines = patch_lines(PATCH)
    assert [(p.marker, p.old_line, p.new_line) for p in lines] == [
        (" ", 86, 86),
        ("-", 87, None),
        ("+", None, 87),
        (" ", 88, 88),
    ]


def test_lines_under_unreadable_hunk_header_get_no_numbers() -> None:
    assert patch_lines("@@\n+a\n-b") == []


# ------------------------------------------------------------------ accepted drafts


def test_good_draft_is_accepted_and_rendered() -> None:
    result = check(
        Claim(
            "{{fact:maxSMBBasalMinutes.label}} can now be set up to {{fact:maxSMBBasalMinutes.max}}.",
            (GOOD_DIFF,),
        )
    )
    assert result.accepted, result.problems
    assert result.claims[0].rendered == "Max SMB Basal Minutes can now be set up to 240 min."


def test_old_side_citation() -> None:
    result = check(
        Claim("The previous limit is removed.", (DiffCitation(PICKER, 87, Side.OLD, "max: 180"),))
    )
    assert result.accepted


def test_context_line_citation() -> None:
    assert check(
        Claim("Unchanged.", (DiffCitation(PICKER, 88, Side.NEW, "insulinPeakTime"),))
    ).accepted


def test_percent_modifier_for_factors() -> None:
    result = check(Claim("The default is {{fact:maxDailySafetyMultiplier.default|percent}}."))
    assert result.accepted
    assert result.claims[0].rendered == "The default is 300%."


def test_identifier_with_digits_is_not_a_number() -> None:
    assert check(Claim("See `min_5m_carbimpact`.", (GOOD_DIFF,))).accepted


# ------------------------------------------------------------------ evidence or silence


def test_claim_without_citation_rejects_draft() -> None:
    result = check(
        Claim("{{fact:maxSMBBasalMinutes.label}} changed.", (GOOD_DIFF,)),
        Claim("Uploads now work offline."),
    )
    assert not result.accepted
    assert codes(result) == {"no-citation"}
    assert result.claims[0].ok and not result.claims[1].ok


def test_empty_draft_is_rejected() -> None:
    result = check_draft(Draft(()), PR, FACTS)
    assert not result.accepted and codes(result) == {"empty-draft"}


@pytest.mark.parametrize(
    ("citation", "code"),
    [
        (DiffCitation("Trio/Other.swift", 1, Side.NEW, "x"), "unknown-file"),
        (DiffCitation(PICKER, 500, Side.NEW, "max"), "line-not-in-diff"),
        (DiffCitation(PICKER, 87, Side.NEW, "max: 300"), "quote-mismatch"),
        (DiffCitation(PICKER, 87, Side.OLD, "max: 240"), "quote-mismatch"),  # wrong side
        (FactCitation("maxSMBBasalMinutes", "colour"), "unknown-fact"),
        (FactCitation("noSuchSetting", "default"), "unknown-fact"),
        (FactCitation("computed", "default"), "fact-needs-human"),
        (FactCitation("dup", "label"), "ambiguous-fact"),
    ],
)
def test_bad_citations_reject(citation, code: str) -> None:  # type: ignore[no-untyped-def]
    result = check(Claim("The limit changed.", (citation,)))
    assert not result.accepted
    assert code in codes(result)


# ------------------------------------------------------------------ numbers and units


@pytest.mark.parametrize(
    "text",
    [
        "The maximum is now 240 minutes.",
        "Set it to 0.5.",
        "Raised from 180 to 240.",
        "The maximum is now four hours.",
        "The cap is thirty minutes.",
        "Allow one unit more.",
    ],
)
def test_raw_numbers_reject(text: str) -> None:
    result = check(Claim(text, (GOOD_DIFF,)))
    assert not result.accepted
    assert "raw-number" in codes(result)


@pytest.mark.parametrize(
    "text",
    [
        "The high target defaults to {{fact:highTarget.json_default}} mmol/L.",  # unit swap
        "Up to {{fact:maxSMBBasalMinutes.max}} hours.",
        "Default {{fact:maxDailySafetyMultiplier.default}} %.",
    ],
)
def test_unit_after_placeholder_rejects(text: str) -> None:
    result = check(Claim(text, (GOOD_DIFF,)))
    assert not result.accepted
    assert "unit-after-placeholder" in codes(result)


@pytest.mark.parametrize(
    "text",
    [
        "{{fact:maxSMBBasalMinutes.max}",
        "{{maxSMBBasalMinutes.max}}",
        "{{fact:maxSMBBasalMinutes.label|percent}}",
        "{{fact:maxSMBBasalMinutes.max|percent}}",  # minutes are not a factor
        "{{fact:maxSMBBasalMinutes.max|double}}",
    ],
)
def test_bad_placeholders_reject(text: str) -> None:
    result = check(Claim(text, (GOOD_DIFF,)))
    assert not result.accepted
    assert codes(result) & {"bad-placeholder", "unknown-fact"}


def test_placeholder_to_unreadable_fact_rejects() -> None:
    result = check(Claim("Default is {{fact:computed.default}}.", (GOOD_DIFF,)))
    assert "fact-needs-human" in codes(result)


def test_rejected_claims_are_not_rendered() -> None:
    result = check(Claim("Set to 5.", (GOOD_DIFF,)))
    assert result.claims[0].rendered is None


# ------------------------------------------------------------------ draft format


def test_parse_draft() -> None:
    draft = parse_draft(
        {
            "edits": [
                {
                    "doc_path": "docs/smb.md",
                    "claims": [
                        {
                            "text": "Up to {{fact:maxSMBBasalMinutes.max}}.",
                            "citations": [
                                {"path": PICKER, "line": 87, "side": "new", "quote": "max: 240"},
                                {"fact": "maxSMBBasalMinutes.max"},
                            ],
                        }
                    ],
                }
            ]
        }
    )
    assert draft.claims[0].citations == (GOOD_DIFF, FactCitation("maxSMBBasalMinutes", "max"))
    assert check_draft(draft, PR, FACTS).accepted


@pytest.mark.parametrize(
    "data",
    [
        {"edits": [{"doc_path": "a.md", "claims": [{"text": "x", "source": "model"}]}]},
        {
            "edits": [
                {
                    "doc_path": "a.md",
                    "claims": [
                        {"text": "x", "citations": [{"path": "p", "line": 0, "quote": "q"}]}
                    ],
                }
            ]
        },
        {
            "edits": [
                {
                    "doc_path": "a.md",
                    "claims": [
                        {
                            "text": "x",
                            "citations": [{"path": "p", "line": 1, "side": "mid", "quote": "q"}],
                        }
                    ],
                }
            ]
        },
        {
            "edits": [
                {"doc_path": "a.md", "claims": [{"text": "x", "citations": [{"fact": "nokind"}]}]}
            ]
        },
        {
            "edits": [
                {
                    "doc_path": "a.md",
                    "claims": [{"text": "x", "citations": [{"pr_description": True}]}],
                }
            ]
        },
        {"edits": [], "confidence": 0.99},
    ],
)
def test_parse_draft_is_strict(data) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(DraftFormatError):
        parse_draft(data)
