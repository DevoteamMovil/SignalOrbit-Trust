"""Stub para xAI Grok-3 (P1, no implementado)."""

from src.providers.base import ProviderAdapter, ProviderResult


class XAIProvider(ProviderAdapter):
    provider = "xai"

    def generate(self, **kwargs) -> ProviderResult:
        raise NotImplementedError("xAI provider is not yet implemented (P1)")
