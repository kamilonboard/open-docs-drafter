"""Model providers for the drafting layer (4) and, later, the verifier (6).

Add a provider by implementing `Provider` (see base.py) and registering it here.
"""

from typing import Any

from open_docs_drafter.providers.base import Provider, ProviderError, ProviderResponse
from open_docs_drafter.providers.claude import ClaudeProvider
from open_docs_drafter.providers.fake import FakeProvider

PROVIDERS: dict[str, Any] = {"claude": ClaudeProvider, "fake": FakeProvider}


def make_provider(name: str, **options: Any) -> Provider:
    if name not in PROVIDERS:
        raise ProviderError(f"unknown provider {name!r}; choose from {sorted(PROVIDERS)}")
    provider: Provider = PROVIDERS[name](**{k: v for k, v in options.items() if v is not None})
    return provider


__all__ = [
    "PROVIDERS",
    "ClaudeProvider",
    "FakeProvider",
    "Provider",
    "ProviderError",
    "ProviderResponse",
    "make_provider",
]
