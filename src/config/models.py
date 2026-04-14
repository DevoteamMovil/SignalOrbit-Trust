"""Configuración de modelos LLM para SignalOrbit."""

MODEL_SOURCE_MAP = {
    # ── OpenAI ────────────────────────────────────────────────
    "openai_gpt_4_1": {
        "provider": "openai",
        "provider_model_id": "gpt-4.1",
        "enabled": True,
    },
    "openai_gpt_4_1_mini": {
        "provider": "openai",
        "provider_model_id": "gpt-4.1-mini",
        "enabled": True,
    },
    "openai_gpt_4_1_nano": {
        "provider": "openai",
        "provider_model_id": "gpt-4.1-nano",
        "enabled": True,
    },
    "openai_o4_mini": {
        "provider": "openai",
        "provider_model_id": "o4-mini",
        "enabled": True,
    },
    # ── Google / Gemini ───────────────────────────────────────
    "google_gemini_2_5_pro": {
        "provider": "gemini",
        "provider_model_id": "gemini-2.5-pro",
        "enabled": True,
    },
    "google_gemini_2_5_flash": {
        "provider": "gemini",
        "provider_model_id": "gemini-2.5-flash",
        "enabled": True,
    },
    "google_gemini_2_0_flash": {
        "provider": "gemini",
        "provider_model_id": "gemini-2.0-flash",
        "enabled": True,
    },
    # ── Anthropic ─────────────────────────────────────────────
    "anthropic_claude_sonnet_4_6": {
        "provider": "anthropic",
        "provider_model_id": "claude-sonnet-4-6",
        "enabled": True,
    },
    "anthropic_claude_haiku_3_5": {
        "provider": "anthropic",
        "provider_model_id": "claude-3-5-haiku-latest",
        "enabled": True,
    },
    # ── xAI ──────────────────────────────────────────────────
    "xai_grok_3": {
        "provider": "xai",
        "provider_model_id": "grok-3",
        "enabled": True,
    },
}

GENERATION_DEFAULTS = {
    "temperature": 0.2,
    "max_output_tokens": 1024,
    "system_prompt": "Eres un asistente útil, neutral y conciso. Responde en español.",
}
