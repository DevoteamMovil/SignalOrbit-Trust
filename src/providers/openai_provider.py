"""Adaptador para OpenAI GPT-4.1."""

import os
import time
from openai import OpenAI
from src.providers.base import ProviderAdapter, ProviderResult


class OpenAIProvider(ProviderAdapter):
    provider = "openai"

    def __init__(self):
        self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

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
            logprobs=True,
            top_logprobs=3,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)

        choice = response.choices[0]

        # Extract logprobs: list of {token, logprob, top_logprobs} per token
        logprobs_data = None
        if choice.logprobs and choice.logprobs.content:
            logprobs_data = [
                {
                    "token": lp.token,
                    "logprob": lp.logprob,
                    "top_logprobs": [
                        {"token": t.token, "logprob": t.logprob}
                        for t in (lp.top_logprobs or [])
                    ],
                }
                for lp in choice.logprobs.content
            ]

        return ProviderResult(
            text=choice.message.content or "",
            input_tokens=response.usage.prompt_tokens if response.usage else None,
            output_tokens=response.usage.completion_tokens if response.usage else None,
            provider_request_id=response.id,
            finish_reason=choice.finish_reason,
            latency_ms=latency_ms,
            logprobs_data=logprobs_data,
        )
