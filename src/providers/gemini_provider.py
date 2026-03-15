"""Adaptador para Google Gemini."""

import os
import time
from google import genai
from google.genai import types
from src.providers.base import ProviderAdapter, ProviderResult

# Models that use "thinking" and consume tokens for internal reasoning.
_THINKING_MODELS = {"gemini-2.5-pro", "gemini-2.5-flash"}


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

        # For thinking models, set a thinking budget so not all tokens
        # are consumed by internal reasoning, leaving room for content.
        if provider_model_id in _THINKING_MODELS:
            config.thinking_config = types.ThinkingConfig(
                thinking_budget=1024,
            )
            # Ensure enough tokens for both thinking + actual response
            config.max_output_tokens = max(max_output_tokens * 4, 4096)

        t0 = time.perf_counter()
        response = self.client.models.generate_content(
            model=provider_model_id,
            contents=prompt,
            config=config,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)

        # Extract text — response.text can raise ValueError or return None
        # for thinking models, safety blocks, or multi-part responses.
        text = ""
        try:
            text = response.text or ""
        except (ValueError, AttributeError):
            pass

        # Fallback: extract non-thought text from candidates/parts manually
        if not text and response.candidates:
            content = response.candidates[0].content
            if content and content.parts:
                text_parts = []
                for part in content.parts:
                    is_thought = getattr(part, "thought", False)
                    if not is_thought and hasattr(part, "text") and part.text:
                        text_parts.append(part.text)
                text = "\n".join(text_parts)

        usage = response.usage_metadata
        input_tokens = getattr(usage, "prompt_token_count", None) if usage else None
        output_tokens = getattr(usage, "candidates_token_count", None) if usage else None

        # Capture finish_reason for debugging
        finish_reason = None
        if response.candidates:
            fr = getattr(response.candidates[0], "finish_reason", None)
            if fr is not None:
                finish_reason = str(fr)

        return ProviderResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            provider_request_id=None,
            finish_reason=finish_reason,
            latency_ms=latency_ms,
        )


