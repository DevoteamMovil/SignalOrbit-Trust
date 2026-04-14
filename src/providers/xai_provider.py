"""Adaptador para xAI Grok-3.

xAI exposes an OpenAI-compatible API, so we reuse the openai SDK
pointed at https://api.x.ai/v1.
"""

import os
import time

from openai import OpenAI

from src.providers.base import ProviderAdapter, ProviderResult


class XAIProvider(ProviderAdapter):
    provider = "xai"

    def __init__(self):
        self.client = OpenAI(
            api_key=os.environ["XAI_API_KEY"],
            base_url="https://api.x.ai/v1",
        )

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
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        t0 = time.perf_counter()
        response = self.client.chat.completions.create(
            model=provider_model_id,
            messages=messages,
            temperature=temperature,
            max_tokens=max_output_tokens,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)

        choice = response.choices[0]

        return ProviderResult(
            text=choice.message.content or "",
            input_tokens=response.usage.prompt_tokens if response.usage else None,
            output_tokens=response.usage.completion_tokens if response.usage else None,
            provider_request_id=response.id,
            finish_reason=choice.finish_reason,
            latency_ms=latency_ms,
        )
