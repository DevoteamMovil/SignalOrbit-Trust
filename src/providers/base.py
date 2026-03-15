"""Clase base para adaptadores de proveedores LLM."""

from dataclasses import dataclass, field
from abc import ABC, abstractmethod


@dataclass
class ProviderResult:
    """Resultado de una llamada a un proveedor LLM."""
    text: str
    input_tokens: int | None
    output_tokens: int | None
    provider_request_id: str | None
    finish_reason: str | None
    latency_ms: int
    raw_payload: dict | None = field(default=None, repr=False)
    logprobs_data: list[dict] | None = field(default=None, repr=False)


class ProviderAdapter(ABC):
    """Interfaz abstracta para adaptadores de proveedores."""

    provider: str

    @abstractmethod
    def generate(
        self,
        *,
        prompt: str,
        system_prompt: str | None,
        provider_model_id: str,
        temperature: float,
        max_output_tokens: int,
        client_request_id: str,
    ) -> ProviderResult:
        ...
