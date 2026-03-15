"""Adaptador para Anthropic Claude Sonnet 4.6."""

import os
import time
from anthropic import Anthropic
from src.providers.base import ProviderAdapter, ProviderResult


class AnthropicProvider(ProviderAdapter):
    provider = "anthropic"

    def __init__(self):
        self.client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

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
        kwargs = {
            "model": provider_model_id,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_output_tokens,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        t0 = time.perf_counter()
        response = self.client.messages.create(**kwargs)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        text = response.content[0].text if response.content else ""
        return ProviderResult(
            text=text,
            input_tokens=response.usage.input_tokens if response.usage else None,
            output_tokens=response.usage.output_tokens if response.usage else None,
            provider_request_id=response.id,
            finish_reason=response.stop_reason,
            latency_ms=latency_ms,
        )
