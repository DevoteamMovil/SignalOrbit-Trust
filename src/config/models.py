"""Configuración de modelos LLM para SignalOrbit."""

MODEL_SOURCE_MAP = {
    "openai_gpt_4_1": {
        "provider": "openai",
        "provider_model_id": "gpt-4.1",
        "enabled": True,
    },
    "google_gemini_2_5_pro": {
        "provider": "gemini",
        "provider_model_id": "gemini-2.5-pro",
        "enabled": True,
    },
    "anthropic_claude_sonnet_4_6": {
        "provider": "anthropic",
        "provider_model_id": "claude-sonnet-4-6",
        "enabled": True,
    },
    "xai_grok_3": {
        "provider": "xai",
        "provider_model_id": "grok-3",
        "enabled": False,
    },
}

GENERATION_DEFAULTS = {
    "temperature": 0.2,
    "max_output_tokens": 700,
    "system_prompt": "Eres un asistente útil, neutral y conciso. Responde en español.",
}
