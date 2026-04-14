"""Caché a disco por hash SHA256."""

import hashlib
import json
from pathlib import Path
from src.providers.base import ProviderResult

CACHE_DIR = Path(".cache")


def make_key(
    provider_model_id: str,
    prompt_text: str,
    system_prompt: str,
    temperature: float,
    max_output_tokens: int,
) -> str:
    """Genera clave SHA256 a partir de los parámetros de la llamada."""
    raw = f"{provider_model_id}|{prompt_text}|{system_prompt}|{temperature}|{max_output_tokens}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get(key: str) -> ProviderResult | None:
    """Recupera un resultado del caché. Devuelve None si no existe o está corrupto.

    Si el archivo existe pero está corrupto (JSON truncado por interrupción del proceso),
    lo elimina para que la siguiente llamada lo regenere limpiamente.
    """
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return ProviderResult(
            text=data["text"],
            input_tokens=data.get("input_tokens"),
            output_tokens=data.get("output_tokens"),
            provider_request_id=data.get("provider_request_id"),
            finish_reason=data.get("finish_reason"),
            latency_ms=data.get("latency_ms", 0),
            logprobs_data=data.get("logprobs_data"),
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        # Archivo corrupto — eliminarlo para que se regenere en la próxima llamada
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def put(key: str, result: ProviderResult) -> None:
    """Guarda un resultado en el caché usando escritura atómica (tmp → rename).

    Evita archivos corruptos si el proceso se interrumpe durante la escritura.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{key}.json"
    tmp_path = CACHE_DIR / f"{key}.tmp"
    data = {
        "text": result.text,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "provider_request_id": result.provider_request_id,
        "finish_reason": result.finish_reason,
        "latency_ms": result.latency_ms,
        "logprobs_data": result.logprobs_data,
    }
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        tmp_path.replace(path)  # atomic on POSIX; best-effort on Windows
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
