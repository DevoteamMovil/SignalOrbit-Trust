"""SignalOrbit — Live Query Engine.

Ejecuta consultas de texto libre contra múltiples LLMs en paralelo
y devuelve resultados comparativos.

Uso interno desde dashboard_app.py (tab Live Explorer).
"""

import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv

from src.config.models import MODEL_SOURCE_MAP, GENERATION_DEFAULTS

load_dotenv()

# ── Provider factory ──────────────────────────────────────────────

_provider_cache: dict = {}


def _get_provider(provider_name: str):
    """Instancia (o reutiliza) un adaptador de proveedor."""
    if provider_name in _provider_cache:
        return _provider_cache[provider_name]

    if provider_name == "openai":
        from src.providers.openai_provider import OpenAIProvider
        adapter = OpenAIProvider()
    elif provider_name == "gemini":
        from src.providers.gemini_provider import GeminiProvider
        adapter = GeminiProvider()
    elif provider_name == "anthropic":
        from src.providers.anthropic_provider import AnthropicProvider
        adapter = AnthropicProvider()
    elif provider_name == "xai":
        from src.providers.xai_provider import XAIProvider
        adapter = XAIProvider()
    else:
        raise ValueError(f"Provider not supported: {provider_name}")

    _provider_cache[provider_name] = adapter
    return adapter


# ── Display labels ────────────────────────────────────────────────

MODEL_LABELS = {
    "openai_gpt_4_1": "GPT-4.1",
    "openai_gpt_4_1_mini": "GPT-4.1 Mini",
    "openai_gpt_4_1_nano": "GPT-4.1 Nano",
    "openai_o4_mini": "o4-mini",
    "google_gemini_2_5_pro": "Gemini 2.5 Pro",
    "google_gemini_2_5_flash": "Gemini 2.5 Flash",
    "google_gemini_2_0_flash": "Gemini 2.0 Flash",
    "anthropic_claude_sonnet_4_6": "Claude Sonnet",
    "anthropic_claude_haiku_3_5": "Claude Haiku 3.5",
    "xai_grok_3": "Grok 3",
}


def model_label(key: str) -> str:
    """Label legible para un model_source key."""
    return MODEL_LABELS.get(key, key)


def get_available_models() -> dict[str, list[str]]:
    """Devuelve modelos habilitados agrupados por proveedor.

    Returns:
        {"OpenAI": ["openai_gpt_4_1", ...], "Google / Gemini": [...], ...}
    """
    provider_display = {
        "openai": "OpenAI",
        "gemini": "Google / Gemini",
        "anthropic": "Anthropic",
        "xai": "xAI",
    }
    groups: dict[str, list[str]] = {}
    for key, cfg in MODEL_SOURCE_MAP.items():
        if not cfg["enabled"]:
            continue
        group = provider_display.get(cfg["provider"], cfg["provider"])
        groups.setdefault(group, []).append(key)
    return groups


# ── Single model call ─────────────────────────────────────────────

def _query_single_model(
    model_key: str,
    prompt: str,
    system_prompt: str,
    temperature: float,
    max_output_tokens: int,
) -> dict:
    """Llama a un modelo y devuelve un dict de resultado."""
    cfg = MODEL_SOURCE_MAP.get(model_key)
    if not cfg:
        return {
            "model_source": model_key,
            "model_label": model_label(model_key),
            "status": "error",
            "error": f"Model not found: {model_key}",
            "text": "",
            "latency_ms": 0,
            "input_tokens": None,
            "output_tokens": None,
        }

    try:
        adapter = _get_provider(cfg["provider"])
        result = adapter.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            provider_model_id=cfg["provider_model_id"],
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            client_request_id=str(uuid.uuid4()),
        )
        return {
            "model_source": model_key,
            "model_label": model_label(model_key),
            "status": "ok",
            "error": None,
            "text": result.text,
            "latency_ms": result.latency_ms,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
        }
    except Exception as e:
        return {
            "model_source": model_key,
            "model_label": model_label(model_key),
            "status": "error",
            "error": str(e),
            "text": "",
            "latency_ms": 0,
            "input_tokens": None,
            "output_tokens": None,
        }


# ── Parallel multi-model query ───────────────────────────────────

def run_live_query(
    prompt: str,
    model_keys: list[str],
    system_prompt: str | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
) -> list[dict]:
    """Ejecuta una consulta contra múltiples modelos en paralelo.

    Args:
        prompt: Texto libre del usuario.
        model_keys: Lista de claves de MODEL_SOURCE_MAP.
        system_prompt: System prompt (default: GENERATION_DEFAULTS).
        temperature: Temperatura (default: GENERATION_DEFAULTS).
        max_output_tokens: Máx tokens de salida (default: GENERATION_DEFAULTS).

    Returns:
        Lista de dicts con keys: model_source, model_label, status,
        error, text, latency_ms, input_tokens, output_tokens.
    """
    if system_prompt is None:
        system_prompt = GENERATION_DEFAULTS["system_prompt"]
    if temperature is None:
        temperature = GENERATION_DEFAULTS["temperature"]
    if max_output_tokens is None:
        max_output_tokens = GENERATION_DEFAULTS["max_output_tokens"]

    results = []
    with ThreadPoolExecutor(max_workers=min(len(model_keys), 6)) as pool:
        futures = {
            pool.submit(
                _query_single_model, mk, prompt, system_prompt,
                temperature, max_output_tokens,
            ): mk
            for mk in model_keys
        }
        for future in as_completed(futures):
            results.append(future.result())

    # Ordenar por nombre de modelo para consistencia
    results.sort(key=lambda r: r["model_label"])
    return results
