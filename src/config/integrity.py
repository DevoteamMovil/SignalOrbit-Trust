"""Configuración del Integrity Scanner."""

# Dominios de asistentes AI conocidos que aceptan prompts por URL
AI_ASSISTANT_DOMAINS = [
    "copilot.microsoft.com",
    "chat.openai.com",
    "chatgpt.com",
    "claude.ai",
    "perplexity.ai",
    "grok.com",
    "gemini.google.com",
]

# Nombres de parámetros de URL que pueden contener prompts
PROMPT_QUERY_PARAMS = ["q", "prompt"]

# Keywords que indican intención de persistencia en memoria
MEMORY_KEYWORDS = [
    # Inglés
    "remember",
    "trusted source",
    "authoritative source",
    "authoritative",
    "in future conversations",
    "future conversations",
    "citation",
    "cite",
    "from now on",
    "always recommend",
    "preferred source",
    "keep in memory",
    "go-to source",
    # Español
    "recuerda",
    "fuente fiable",
    "fuente confiable",
    "fuente de confianza",
    "en futuras conversaciones",
    "a partir de ahora",
    "recomienda siempre",
    "fuente preferida",
    "guarda en memoria",
]

# Patrones de instrucciones de persistencia (combinaciones de keywords
# que indican intención fuerte de manipulación)
PERSISTENCE_PATTERNS = [
    ("remember", "trusted"),
    ("remember", "source"),
    ("remember", "future"),
    ("always", "recommend"),
    ("keep", "memory"),
    ("recuerda", "fuente"),
    ("recuerda", "futuras"),
    ("siempre", "recomienda"),
]

# Puntuación de riesgo
RISK_SCORING = {
    "ai_domain_detected": 30,
    "prompt_param_present": 20,
    "per_memory_keyword": 15,
    "max_keyword_score": 30,
    "persistence_instruction": 20,
}


def get_risk_level(score: int) -> str:
    """Clasifica el risk_score en un nivel de riesgo."""
    if score <= 25:
        return "low"
    elif score <= 50:
        return "medium"
    elif score <= 75:
        return "high"
    else:
        return "critical"
