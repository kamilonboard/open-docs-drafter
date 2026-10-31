"""A provider that returns prepared answers. For tests, planted-error cases and dry runs."""

import json
from collections.abc import Callable
from typing import Any

from open_docs_drafter.providers.base import ProviderResponse


class FakeProvider:
    name = "fake"

    def __init__(
        self,
        answer: dict[str, Any] | str | Callable[[str, str], dict[str, Any] | str] | None = None,
        *,
        model: str = "fake-model",
        stop_reason: str = "end_turn",
    ) -> None:
        self.model = model
        self.answer = answer
        self.stop_reason = stop_reason
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> ProviderResponse:
        self.calls.append((system, user, schema))
        answer = self.answer(system, user) if callable(self.answer) else self.answer
        if answer is None:
            answer = {
                "decision": "needs_human",
                "reason": "fake provider has no answer",
                "edits": [],
            }
        text = answer if isinstance(answer, str) else json.dumps(answer)
        refused = self.stop_reason == "refusal"
        return ProviderResponse(
            text=None if refused or self.stop_reason != "end_turn" else text,
            provider=self.name,
            model_requested=self.model,
            model_served=self.model,
            stop_reason=self.stop_reason,
            refusal="fake refusal" if refused else None,
        )
