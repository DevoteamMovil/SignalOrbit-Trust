"""Clase base para adaptadores de proveedores LLM."""

from abc import ABC, abstractmethod
from pydantic import BaseModel, Field


class ProviderResult(BaseModel):
    """Resultado de una llamada a un proveedor LLM."""

    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider_request_id: str | None = None
    finish_reason: str | None = None
    latency_ms: int
    raw_payload: dict | None = Field(default=None, exclude=True)
    logprobs_data: list[dict] | None = Field(default=None, exclude=True)


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
