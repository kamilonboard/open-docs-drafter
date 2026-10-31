import json
from pathlib import Path
from typing import Any

import pytest

from open_docs_drafter import pipeline
from open_docs_drafter.facts import FactSet
from open_docs_drafter.layers.citation_check import check_draft
from open_docs_drafter.layers.verifier import (
    OUTPUT_SCHEMA,
    Independence,
    Verdict,
    independence,
    verify,
)
from open_docs_drafter.models import ChangedFile, PullRequest
from open_docs_drafter.profile import load_profile
from open_docs_drafter.providers import ClaudeProvider, FakeProvider, ProviderError

ROOT = Path(__file__).parent
TRIO = load_profile(ROOT.parent / "profiles" / "trio" / "profile.yaml")
REMOTE = "Trio/Sources/Services/RemoteControl/RemoteBolusHandler.swift"
PAGE = "docs/configuration/settings/features/remote-control.md"
PAGES = {PAGE: (ROOT / "fixtures" / "triodocs" / "remote-control.md").read_text()}
SECRET_DESCRIPTION = "PR-AUTHOR-TEXT: this also makes remote bolus work offline."
PR = PullRequest(
    9,
    "Show remote bolus confirmation",
    SECRET_DESCRIPTION,
    "",
    (
        ChangedFile(
            REMOTE,
            "@@ -40 +40,2 @@\n     deliverBolus(amount)\n+    notifyUser(.remoteBolusDelivered)\n",
        ),
    ),
)
DRAFTER_REASON = "DRAFTER-REASONING: I inferred an offline queue."


def drafter_answer(*texts: str) -> dict[str, Any]:
    return {
        "decision": "draft",
        "reason": DRAFTER_REASON,
        "edits": [
            {
                "doc_path": PAGE,
                "operation": "insert_after",
                "anchor": "Remote bolus sends a bolus command to the looping phone.",
                "claims": [
                    {
                        "text": t,
                        "diff_citations": [
                            {
                                "path": REMOTE,
                                "line": 41,
                                "side": "new",
                                "quote": "remoteBolusDelivered",
                            }
                        ],
                        "fact_citations": [],
                    }
                    for t in texts
                ],
            }
        ],
    }


CLAIM = "The looping phone shows a notification after a remote bolus is delivered."


def verdicts(*items: tuple[int, str], omissions: list[str] | None = None) -> dict[str, Any]:
    return {
        "claims": [{"id": i, "verdict": v, "explanation": f"because {i}"} for i, v in items],
        "omissions": omissions or [],
    }


def run(verifier_answer: Any, *claims: str, verifier: Any = None):  # type: ignore[no-untyped-def]
    drafter = FakeProvider(drafter_answer(*(claims or (CLAIM,))), model="drafter-model")
    verifier = verifier or FakeProvider(verifier_answer, model="verifier-model")
    result = pipeline.run(
        TRIO, PR, provider=drafter, verifier=verifier, base_files={}, head_files={}, pages=PAGES
    )
    return result, drafter, verifier


def codes(result) -> set[str]:  # type: ignore[no-untyped-def]
    assert result.verification is not None
    return {p.code for p in result.verification.problems}


# ------------------------------------------------------------------ outcomes


def test_all_supported_is_ready_for_review() -> None:
    result, _, _ = run(verdicts((1, "supported")))
    assert result.outcome is pipeline.Outcome.READY_FOR_REVIEW, result.summary
    assert result.verification is not None and result.verification.accepted


@pytest.mark.parametrize(
    ("verdict", "code"), [("not_supported", "claim-not-supported"), ("advice", "claim-advice")]
)
def test_one_bad_claim_escalates_the_whole_draft(verdict: str, code: str) -> None:
    result, _, _ = run(
        verdicts((1, "supported"), (2, verdict)), CLAIM, "Uploads also work offline."
    )
    assert result.outcome is pipeline.Outcome.ESCALATED
    assert codes(result) == {code}


def test_omission_escalates() -> None:
    result, _, _ = run(
        verdicts((1, "supported"), omissions=["the diff resets remote control settings"])
    )
    assert result.outcome is pipeline.Outcome.ESCALATED and codes(result) == {"omission"}


@pytest.mark.parametrize(
    "answer",
    [
        "not json",
        {"claims": [], "omissions": []},  # no verdicts at all
        verdicts((2, "supported")),  # wrong id
        verdicts((1, "supported"), (1, "supported")),  # duplicate id
        verdicts(
            (1, "supported"), (2, "supported")
        ),  # extra verdict for a claim that doesn't exist
        {"claims": [{"id": 1, "verdict": "supported", "explanation": "x"}]},  # no omissions key
        {"verdicts": []},
    ],
)
def test_unusable_verifier_output_fails_closed(answer: Any) -> None:
    result, _, _ = run(answer)
    assert result.outcome is pipeline.Outcome.ESCALATED
    assert codes(result) == {"verifier-output-invalid"}


def test_unknown_verdict_counts_against_the_claim() -> None:
    result, _, _ = run(
        {"claims": [{"id": 1, "verdict": "probably_fine", "explanation": "x"}], "omissions": []}
    )
    assert result.outcome is pipeline.Outcome.ESCALATED
    assert result.verification is not None
    assert result.verification.verdicts[0].verdict is Verdict.NOT_SUPPORTED


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_verifier_with_no_answer_fails_closed(stop_reason: str) -> None:
    result, _, _ = run(
        None, verifier=FakeProvider(verdicts((1, "supported")), stop_reason=stop_reason)
    )
    assert result.outcome is pipeline.Outcome.ESCALATED and codes(result) == {
        "verifier-unavailable"
    }


def test_verifier_error_fails_closed() -> None:
    class Broken(FakeProvider):
        def complete_json(self, system, user, schema):  # type: ignore[no-untyped-def]
            raise ProviderError("quota exceeded")

    result, _, _ = run(None, verifier=Broken())
    assert result.outcome is pipeline.Outcome.ESCALATED and codes(result) == {
        "verifier-unavailable"
    }


def test_verifier_cannot_rescue_a_rejected_draft() -> None:
    result, _, verifier = run(verdicts((1, "supported")), "It shows within 5 seconds.")
    assert result.outcome is pipeline.Outcome.REJECTED  # layer 5
    assert verifier.calls == []  # never asked, never paid for


def test_layer_7_rejection_skips_the_verifier() -> None:
    drafter_data = drafter_answer(CLAIM)
    drafter_data["edits"][0]["anchor"] = (
        "    - Verify the bolus amount before sending"  # inside a danger box
    )
    verifier = FakeProvider(verdicts((1, "supported")))
    result = pipeline.run(
        TRIO,
        PR,
        provider=FakeProvider(drafter_data),
        verifier=verifier,
        base_files={},
        head_files={},
        pages=PAGES,
    )
    assert result.outcome is pipeline.Outcome.REJECTED and verifier.calls == []


def test_direct_call_with_rejected_citations_fails_closed() -> None:
    from open_docs_drafter.drafts import Claim, DocEdit, Draft

    draft = Draft((DocEdit(PAGE, (Claim("Uncited."),)),))
    citations = check_draft(draft, PR, FactSet([]))
    verifier = FakeProvider(verdicts((1, "supported")))
    out = verify(
        TRIO, PR, draft, citations, FactSet([]), [], drafter=FakeProvider(), verifier=verifier
    )
    assert not out.accepted and verifier.calls == []


# ------------------------------------------------------------------ independence


def test_verifier_never_sees_drafter_reasoning_or_pr_text() -> None:
    _, drafter, verifier = run(verdicts((1, "supported")))
    system, user, schema = verifier.calls[0]
    assert DRAFTER_REASON not in system + user
    assert SECRET_DESCRIPTION not in system + user
    assert PR.title not in user
    drafter_system = drafter.calls[0][0]
    assert drafter_system != system  # a different brief, not the drafter's prompt
    assert schema is OUTPUT_SCHEMA


def test_verifier_sees_rendered_claims_with_their_evidence() -> None:
    _, _, verifier = run(verdicts((1, "supported")))
    user = verifier.calls[0][1]
    assert f'<claim id="1">\n{CLAIM}' in user
    assert f"{REMOTE} new line 41: notifyUser(.remoteBolusDelivered)" in user
    assert "new 41 +" in user  # the full diff, to spot omissions


def test_placeholders_are_filled_and_their_facts_shown() -> None:
    from open_docs_drafter.drafts import Claim, DiffCitation, DocEdit, Draft, Side
    from open_docs_drafter.facts import Fact, Kind

    facts = FactSet([Fact("maxIOB", Kind.MAX, "30", "P.swift", 4, "max: 30", unit="U")])
    draft = Draft(
        (
            DocEdit(
                PAGE,
                (
                    Claim(
                        "Up to {{fact:maxIOB.max}}.",
                        (DiffCitation(REMOTE, 41, Side.NEW, "notifyUser"),),
                    ),
                ),
            ),
        )
    )
    citations = check_draft(draft, PR, facts)
    verifier = FakeProvider(verdicts((1, "supported")))
    verify(TRIO, PR, draft, citations, facts, [], drafter=FakeProvider(), verifier=verifier)
    user = verifier.calls[0][1]
    assert "Up to 30 U." in user and "{{fact:" not in user.split("<claims>")[1].split("\n")[2]
    assert "fact maxIOB.max = 30 U (filled into the sentence)" in user


def test_independence_levels() -> None:
    a = ClaudeProvider(model="claude-opus-5-5")
    assert independence(a, ClaudeProvider(model="claude-opus-5-5")) is Independence.SAME_MODEL
    assert (
        independence(a, ClaudeProvider(model="claude-sonnet-5-5")) is Independence.DIFFERENT_MODEL
    )
    assert independence(a, FakeProvider()) is Independence.DIFFERENT_PROVIDER


def test_audit_records_the_verifier() -> None:
    result, _, _ = run(verdicts((1, "supported")))
    record = pipeline.audit_record(TRIO, PR, result)
    v = record["layer_6_verifier"]
    assert v["accepted"] is True
    assert v["model_served"] == "verifier-model"
    assert v["independence"] == "different model, same provider"
    assert v["verdicts"][0]["verdict"] == "supported"
    assert v["system_prompt"] and v["user_message"] and json.loads(v["raw_output"])


def test_schema_is_strict() -> None:
    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(OUTPUT_SCHEMA)
