"""The interface every model provider implements.

A provider turns (system prompt, user message, JSON schema) into JSON text. It knows
nothing about docs or safety rules; those live in the layers. Swapping providers never
changes what the checks accept.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol


class ProviderError(RuntimeError):
    """The provider could not produce an answer (network, auth, quota, server error)."""


@dataclass(frozen=True)
class ProviderResponse:
    text: str | None  # JSON text, or None if the model refused or was cut off
    provider: str
    model_requested: str
    model_served: str  # Can differ from the request, e.g. after a refusal fallback
    stop_reason: str  # "end_turn", "refusal", "max_tokens", ...
    request_id: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    refusal: str | None = None  # Why the model declined, if it did


class Provider(Protocol):
    name: str
    model: str

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> ProviderResponse:
        """Answer with JSON matching `schema`."""
        ...
