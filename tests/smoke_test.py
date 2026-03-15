#!/usr/bin/env python3
"""Smoke test: verifica conectividad con los 3 proveedores LLM."""

import sys
import time
import uuid

from dotenv import load_dotenv

from src.config.models import MODEL_SOURCE_MAP

SMOKE_PROMPT = "Responde solo: OK"
SYSTEM_PROMPT = "Eres un asistente útil, neutral y conciso. Responde en español."


def _get_adapter(provider_name: str):
    if provider_name == "openai":
        from src.providers.openai_provider import OpenAIProvider
        return OpenAIProvider()
    elif provider_name == "gemini":
        from src.providers.gemini_provider import GeminiProvider
        return GeminiProvider()
    elif provider_name == "anthropic":
        from src.providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider()
    return None


def main():
    load_dotenv()

    print("═" * 60)
    print("  SignalOrbit Smoke Test")
    print("═" * 60)

    results = []
    for model_source, cfg in MODEL_SOURCE_MAP.items():
        if not cfg["enabled"]:
            print(f"  {model_source:40s} SKIPPED (disabled)")
            continue

        provider_name = cfg["provider"]
        provider_model_id = cfg["provider_model_id"]

        try:
            adapter = _get_adapter(provider_name)
            if adapter is None:
                print(f"  {model_source:40s} SKIPPED (no adapter)")
                continue

            result = adapter.generate(
                prompt=SMOKE_PROMPT,
                system_prompt=SYSTEM_PROMPT,
                provider_model_id=provider_model_id,
                temperature=0.0,
                max_output_tokens=50,
                client_request_id=str(uuid.uuid4()),
            )

            text_preview = result.text[:100].replace("\n", " ")
            print(f"  {model_source:40s} OK  {result.latency_ms:5d}ms  "
                  f"in={result.input_tokens} out={result.output_tokens}  "
                  f"\"{text_preview}\"")
            results.append(("OK", model_source))

        except Exception as e:
            print(f"  {model_source:40s} FAIL  {e}")
            results.append(("FAIL", model_source))

    print("─" * 60)
    ok_count = sum(1 for s, _ in results if s == "OK")
    fail_count = sum(1 for s, _ in results if s == "FAIL")
    print(f"  Results: {ok_count} OK · {fail_count} FAIL")
    print("═" * 60)

    sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    main()
