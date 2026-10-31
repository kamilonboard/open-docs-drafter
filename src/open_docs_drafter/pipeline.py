"""Run the layers in order on one merged pull request.

    1 input check -> 2 triage -> 3 facts -> 4 drafting -> 5 citation check
    -> (6 verifier: not built yet) -> 7 edit constraints -> 8 human review

Each layer can stop the run. The result records what every layer saw and decided, for
the audit log. Nothing here writes to GitHub.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from open_docs_drafter import __version__
from open_docs_drafter.layers import drafting, fact_extraction
from open_docs_drafter.layers.citation_check import CitationCheckResult, check_draft
from open_docs_drafter.layers.edit_constraints import EditCheckResult, check_edits
from open_docs_drafter.layers.input_check import InputCheckResult, check_input
from open_docs_drafter.layers.triage import TriageResult, rule_based_tier
from open_docs_drafter.models import PullRequest, changed_lines
from open_docs_drafter.profile import Profile
from open_docs_drafter.providers import Provider


class Outcome(StrEnum):
    RED_EVIDENCE_PACK = "red_evidence_pack"  # Human expert writes it; no AI text
    NO_DOCS_CHANGE = "no_docs_change"
    NEEDS_HUMAN = "needs_human"
    REJECTED = "rejected"  # A check layer rejected the draft
    AWAITING_VERIFIER = "awaiting_verifier"  # Passed layers 5 and 7; layer 6 not built yet


@dataclass(frozen=True)
class PipelineResult:
    outcome: Outcome
    summary: str
    input_check: InputCheckResult
    triage: TriageResult
    drafting: drafting.DraftingResult
    citations: CitationCheckResult | None = None
    edits: EditCheckResult | None = None


def run(
    profile: Profile,
    pr: PullRequest,
    *,
    provider: Provider,
    base_files: Mapping[str, str],
    head_files: Mapping[str, str],
    pages: Mapping[str, str],
) -> PipelineResult:
    # Layer 1: PR text is untrusted.
    ic = check_input(profile, pr)

    # Layer 2: tier from files and diff lines, plus PR text. Text can only raise it.
    diff_lines = [line for f in pr.files for line in changed_lines(f.patch)]
    triage = rule_based_tier(profile, [f.path for f in pr.files], [pr.title, pr.body, *diff_lines])

    # Layer 3: exact facts at the merge, and what the PR changed.
    head_facts = fact_extraction.extract_facts(profile, head_files)
    changes = fact_extraction.fact_changes(profile, base_files, head_files)

    # Layer 4: draft (never for red).
    dr = drafting.draft(profile, pr, ic, triage.tier, head_facts, changes, pages, provider)
    if dr.status is drafting.Status.RED_EVIDENCE_PACK:
        return PipelineResult(Outcome.RED_EVIDENCE_PACK, dr.reason, ic, triage, dr)
    if dr.status is drafting.Status.NO_DOCS_CHANGE:
        return PipelineResult(Outcome.NO_DOCS_CHANGE, dr.reason, ic, triage, dr)
    if dr.status is drafting.Status.NEEDS_HUMAN or dr.draft is None:
        return PipelineResult(Outcome.NEEDS_HUMAN, dr.reason, ic, triage, dr)

    # Layer 5: every claim backed by evidence; numbers only from facts.
    citations = check_draft(dr.draft, pr, head_facts)
    if not citations.accepted:
        return PipelineResult(
            Outcome.REJECTED,
            f"layer 5 rejected the draft: {_codes(citations.problems)}",
            ic,
            triage,
            dr,
            citations,
        )

    # Layer 7: safe edits to allowed pages; warning boxes untouched.
    edits = check_edits(profile, dr.draft, citations, pages)
    if not edits.accepted:
        return PipelineResult(
            Outcome.REJECTED,
            f"layer 7 rejected the draft: {_codes(edits.problems)}",
            ic,
            triage,
            dr,
            citations,
            edits,
        )

    return PipelineResult(
        Outcome.AWAITING_VERIFIER,
        "passed layers 5 and 7; the independent verifier (layer 6) and a human "
        "still need to check it",
        ic,
        triage,
        dr,
        citations,
        edits,
    )


def _codes(problems: Any) -> str:
    return ", ".join(sorted({p.code for p in problems}))


# ------------------------------------------------------------------ audit log


def audit_record(profile: Profile, pr: PullRequest, result: PipelineResult) -> dict[str, Any]:
    """Everything needed to trace a draft: inputs, model, prompts, output and every check."""
    dr = result.drafting
    response = dr.response
    return {
        "tool_version": __version__,
        "created_at": datetime.now(UTC).isoformat(),
        "project": profile.project.name,
        "profile_status": profile.status,
        "pull_request": {"repo": profile.project.code_repo, "number": pr.number, "title": pr.title},
        "outcome": result.outcome.value,
        "summary": result.summary,
        "layer_1_input_check": {
            "discarded": result.input_check.discarded,
            "findings": [f"{f.severity}:{f.code}: {f.detail}" for f in result.input_check.findings],
        },
        "layer_2_triage": {
            "tier": result.triage.tier.name,
            "matches": [f"{m.rule_id}: {m.evidence}" for m in result.triage.matches],
            "unmatched_files": list(result.triage.unmatched_files),
        },
        "layer_4_drafting": {
            "status": dr.status.value,
            "reason": dr.reason,
            "settings_involved": list(dr.settings_involved),
            "pages_shown": list(dr.pages_shown),
            "provider": response.provider if response else None,
            "model_requested": response.model_requested if response else None,
            "model_served": response.model_served if response else None,
            "stop_reason": response.stop_reason if response else None,
            "request_id": response.request_id if response else None,
            "usage": response.usage if response else None,
            "system_prompt": dr.system,
            "user_message": dr.user,
            "raw_output": dr.raw_output,
            "evidence_pack": dr.evidence.__dict__ if dr.evidence else None,
        },
        "layer_5_citation_check": None
        if result.citations is None
        else {
            "accepted": result.citations.accepted,
            "claims": [
                {
                    "text": c.claim.text,
                    "rendered": c.rendered,
                    "problems": [f"{p.code}: {p.detail}" for p in c.problems],
                }
                for c in result.citations.claims
            ],
        },
        "layer_6_verifier": "not built yet",
        "layer_7_edit_constraints": None
        if result.edits is None
        else {
            "accepted": result.edits.accepted,
            "problems": [f"{p.code}: {p.detail}" for p in result.edits.problems],
            "pages_changed": sorted(result.edits.new_pages),
        },
    }


def write_audit(record: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = record["created_at"].replace(":", "").replace("-", "")[:15]
    path = out_dir / f"pr{record['pull_request']['number']}_{stamp}.json"
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return path
