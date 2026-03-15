"""Adaptador para Google Gemini 2.5 Pro."""

import os
import time
from google import genai
from google.genai import types
from src.providers.base import ProviderAdapter, ProviderResult


class GeminiProvider(ProviderAdapter):
    provider = "gemini"

    def __init__(self):
        self.client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

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
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        if system_prompt:
            config.system_instruction = system_prompt

        t0 = time.perf_counter()
        response = self.client.models.generate_content(
            model=provider_model_id,
            contents=prompt,
            config=config,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)

        text = response.text or ""
        usage = response.usage_metadata
        input_tokens = getattr(usage, "prompt_token_count", None) if usage else None
        output_tokens = getattr(usage, "candidates_token_count", None) if usage else None

        return ProviderResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            provider_request_id=None,
            finish_reason=None,
            latency_ms=latency_ms,
        )
