"""Claude, through the official Anthropic Python SDK (optional install: `.[claude]`).

Credentials come from the environment the SDK reads (ANTHROPIC_API_KEY, or an
`ant auth login` profile). Nothing here stores or logs keys.
"""

from typing import Any

from open_docs_drafter.providers.base import ProviderError, ProviderResponse

DEFAULT_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeProvider:
    """Structured JSON output from Claude.

    - effort: thinking depth; accuracy matters more than speed here, so "high".
    - fallbacks: if Claude's safety classifiers decline, Anthropic retries on its
      recommended fallback model. The model that answered is always recorded in
      `model_served`, so the audit log shows it. Turn off to pin one model exactly
      (hazard H10); a decline then becomes "needs human".
    """

    name = "claude"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        effort: str = "high",
        fallbacks: bool = True,
        max_tokens: int = 16000,
        client: Any = None,
    ) -> None:
        self.model = model
        self.effort = effort
        self.fallbacks = fallbacks
        self.max_tokens = max_tokens
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise ProviderError(
                    "The Claude provider needs the Anthropic SDK: "
                    "pip install 'open-docs-drafter[claude]'"
                ) from exc
            self._client = anthropic.Anthropic()
        return self._client

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> ProviderResponse:
        client = self._get_client()
        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            # The system prompt is identical for every PR, so cache it.
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": user}],
            "output_config": {
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": schema},
            },
        }
        try:
            if self.fallbacks:
                response = client.beta.messages.create(
                    betas=[FALLBACK_BETA], fallbacks="default", **request
                )
            else:
                response = client.messages.create(**request)
        except Exception as exc:  # The SDK's typed errors; reported, never retried silently
            raise ProviderError(f"Claude request failed: {type(exc).__name__}: {exc}") from exc

        stop_reason = str(response.stop_reason)
        text = None
        refusal = None
        if stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            refusal = f"declined by safety classifiers (category: {category or 'unknown'})"
        elif stop_reason == "end_turn":
            text = next((b.text for b in response.content if b.type == "text"), None)

        usage = getattr(response, "usage", None)
        return ProviderResponse(
            text=text,
            provider=self.name,
            model_requested=self.model,
            model_served=str(getattr(response, "model", self.model)),
            stop_reason=stop_reason,
            request_id=getattr(response, "_request_id", None),
            usage=usage.to_dict() if usage is not None and hasattr(usage, "to_dict") else {},
            refusal=refusal,
        )
