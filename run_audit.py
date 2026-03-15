#!/usr/bin/env python3
"""SignalOrbit — Runner multimodelo.

Envía prompts del prompt_pack a múltiples LLMs y captura respuestas.

Uso:
    python run_audit.py --priority P0
    python run_audit.py --priority P0 --models openai_gpt_4_1,google_gemini_2_5_pro
    python run_audit.py --priority P0 --from-cache-only
    python run_audit.py --priority P0 --dry-run
"""

import argparse
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.config.models import MODEL_SOURCE_MAP, GENERATION_DEFAULTS
from src.io.load_prompts import load_prompts
from src.io.write_jsonl import append_record, load_existing_keys
from src.cache import disk_cache

# Retry config
MAX_RETRIES = 3
RETRY_BACKOFF = [2, 4, 8]
RETRY_STATUS_CODES = {429, 500, 502, 503}
CALL_TIMEOUT = 60
RATE_LIMIT_DELAY = 1.0


def _make_run_id(output_path: str) -> str:
    """Genera run_id secuencial basado en registros existentes."""
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    existing = load_existing_keys(output_path)
    seq = len(existing) // max(len([m for m in MODEL_SOURCE_MAP.values() if m["enabled"]]), 1) + 1
    return f"run-{date_str}-{seq:03d}"


def _get_provider_instance(provider_name: str):
    """Instancia un adaptador de proveedor por nombre."""
    if provider_name == "openai":
        from src.providers.openai_provider import OpenAIProvider
        return OpenAIProvider()
    elif provider_name == "gemini":
        from src.providers.gemini_provider import GeminiProvider
        return GeminiProvider()
    elif provider_name == "anthropic":
        from src.providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider()
    elif provider_name == "xai":
        from src.providers.xai_provider import XAIProvider
        return XAIProvider()
    else:
        raise ValueError(f"Unknown provider: {provider_name}")


def _call_with_retry(adapter, *, prompt, system_prompt, provider_model_id,
                     temperature, max_output_tokens, client_request_id):
    """Llama al proveedor con retry y backoff exponencial."""
    last_exc = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            return adapter.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                provider_model_id=provider_model_id,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                client_request_id=client_request_id,
            )
        except Exception as e:
            last_exc = e
            # Check if retryable
            status_code = getattr(e, "status_code", None)
            is_timeout = isinstance(e, (TimeoutError,))
            is_retryable = status_code in RETRY_STATUS_CODES or is_timeout

            if not is_retryable or attempt >= MAX_RETRIES:
                raise

            wait = RETRY_BACKOFF[attempt] if attempt < len(RETRY_BACKOFF) else RETRY_BACKOFF[-1]
            print(f"    [RETRY] Attempt {attempt + 1}/{MAX_RETRIES}, waiting {wait}s...")
            time.sleep(wait)

    raise last_exc  # Should not reach here


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="SignalOrbit Audit Runner")
    parser.add_argument("--priority", default="P0", help="Filter by priority (default: P0)")
    parser.add_argument("--models", default=None, help="Comma-separated model_source list")
    parser.add_argument("--from-cache-only", action="store_true", help="Only use cached results")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    parser.add_argument("--input", default="data/prompt_pack_v2.csv", help="Path to prompt CSV")
    parser.add_argument("--output", default="data/raw/raw_responses.jsonl", help="Path to output JSONL")
    args = parser.parse_args()

    # Determine models to use
    if args.models:
        model_keys = [m.strip() for m in args.models.split(",")]
    else:
        model_keys = [k for k, v in MODEL_SOURCE_MAP.items() if v["enabled"]]

    # Validate model keys
    for mk in model_keys:
        if mk not in MODEL_SOURCE_MAP:
            print(f"[ERROR] Unknown model_source: {mk}")
            return

    # Load prompts
    prompts = load_prompts(args.input, priority_filter=args.priority)
    if not prompts:
        print(f"[WARN] No prompts found for priority={args.priority} in {args.input}")
        return

    # Load existing keys to skip duplicates
    existing_keys = load_existing_keys(args.output)

    run_id = _make_run_id(args.output)
    system_prompt = GENERATION_DEFAULTS["system_prompt"]
    temperature = GENERATION_DEFAULTS["temperature"]
    max_output_tokens = GENERATION_DEFAULTS["max_output_tokens"]

    total = len(prompts) * len(model_keys)

    print("═" * 55)
    print(f"  SignalOrbit Audit Run: {run_id}")
    print("═" * 55)
    print(f"  Prompts: {len(prompts)} · Models: {len(model_keys)} · Total: {total}")
    if args.dry_run:
        print("  Mode: DRY RUN (no calls will be made)")
    elif args.from_cache_only:
        print("  Mode: CACHE ONLY (no API calls)")
    print("─" * 55)

    if args.dry_run:
        for prompt_row in prompts:
            for mk in model_keys:
                key = f"{prompt_row['query_id']}::{mk}"
                status = "SKIP (exists)" if key in existing_keys else "PENDING"
                print(f"  {key} → {status}")
        print("═" * 55)
        return

    # Instantiate providers (lazy, per-provider)
    provider_instances = {}
    stats = {mk: {"ok": 0, "error": 0, "cache": 0, "skip": 0} for mk in model_keys}
    t_start = time.perf_counter()

    for prompt_row in prompts:
        query_id = prompt_row["query_id"]
        prompt_text = prompt_row["prompt_text"]
        query_family = prompt_row.get("query_family", "")

        for mk in model_keys:
            composite_key = f"{query_id}::{mk}"

            # Skip if already in JSONL
            if composite_key in existing_keys:
                stats[mk]["skip"] += 1
                continue

            model_cfg = MODEL_SOURCE_MAP[mk]
            provider_name = model_cfg["provider"]
            provider_model_id = model_cfg["provider_model_id"]

            # Check cache
            cache_key = disk_cache.make_key(
                provider_model_id, prompt_text, system_prompt, temperature, max_output_tokens
            )
            cached_result = disk_cache.get(cache_key)

            if cached_result:
                record = _build_record(
                    run_id=run_id,
                    query_id=query_id,
                    query_family=query_family,
                    query_prompt=prompt_text,
                    model_source=mk,
                    provider=provider_name,
                    provider_model_id=provider_model_id,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    result=cached_result,
                    cache_hit=True,
                )
                append_record(args.output, record)
                existing_keys.add(composite_key)
                stats[mk]["cache"] += 1
                print(f"  [CACHE] {composite_key}")
                continue

            if args.from_cache_only:
                print(f"  [CACHE MISS] {composite_key}")
                continue

            # Lazy-init provider
            if provider_name not in provider_instances:
                try:
                    provider_instances[provider_name] = _get_provider_instance(provider_name)
                except Exception as e:
                    print(f"  [ERROR] Cannot init {provider_name}: {e}")
                    stats[mk]["error"] += 1
                    continue

            adapter = provider_instances[provider_name]
            client_request_id = str(uuid.uuid4())

            try:
                result = _call_with_retry(
                    adapter,
                    prompt=prompt_text,
                    system_prompt=system_prompt,
                    provider_model_id=provider_model_id,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    client_request_id=client_request_id,
                )
                # Save to cache
                disk_cache.put(cache_key, result)

                record = _build_record(
                    run_id=run_id,
                    query_id=query_id,
                    query_family=query_family,
                    query_prompt=prompt_text,
                    model_source=mk,
                    provider=provider_name,
                    provider_model_id=provider_model_id,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    result=result,
                    cache_hit=False,
                    client_request_id=client_request_id,
                )
                append_record(args.output, record)
                existing_keys.add(composite_key)
                stats[mk]["ok"] += 1
                print(f"  [OK] {composite_key} ({result.latency_ms}ms)")

            except Exception as e:
                error_record = _build_error_record(
                    run_id=run_id,
                    query_id=query_id,
                    query_family=query_family,
                    query_prompt=prompt_text,
                    model_source=mk,
                    provider=provider_name,
                    provider_model_id=provider_model_id,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    error=str(e),
                    client_request_id=client_request_id,
                )
                append_record(args.output, error_record)
                existing_keys.add(composite_key)
                stats[mk]["error"] += 1
                print(f"  [ERROR] {composite_key}: {e}")

            # Rate limit between calls to same provider
            time.sleep(RATE_LIMIT_DELAY)

    elapsed = time.perf_counter() - t_start
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)

    print("─" * 55)
    for mk in model_keys:
        s = stats[mk]
        print(f"  {mk:40s}: {s['ok']:2d} OK · {s['error']:2d} ERR · {s['cache']:2d} CACHE")
    print("─" * 55)
    print(f"  Elapsed: {minutes}m {seconds:02d}s · Output: {args.output}")
    print("═" * 55)


def _build_record(*, run_id, query_id, query_family, query_prompt, model_source,
                  provider, provider_model_id, temperature, max_output_tokens,
                  result, cache_hit, client_request_id=None):
    """Construye un registro JSONL para una respuesta exitosa."""
    return {
        "run_id": run_id,
        "query_id": query_id,
        "query_family": query_family,
        "surface": "api",
        "query_prompt": query_prompt,
        "model_source": model_source,
        "provider": provider,
        "provider_model_id": provider_model_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "status": "ok",
        "latency_ms": result.latency_ms,
        "client_request_id": client_request_id or str(uuid.uuid4()),
        "provider_request_id": result.provider_request_id,
        "cache_hit": cache_hit,
        "raw_response": result.text,
        "citations": [],
        "brands": [],
        "usage": {
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
        },
        "error": None,
    }


def _build_error_record(*, run_id, query_id, query_family, query_prompt, model_source,
                        provider, provider_model_id, temperature, max_output_tokens,
                        error, client_request_id=None):
    """Construye un registro JSONL para un error."""
    return {
        "run_id": run_id,
        "query_id": query_id,
        "query_family": query_family,
        "surface": "api",
        "query_prompt": query_prompt,
        "model_source": model_source,
        "provider": provider,
        "provider_model_id": provider_model_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "status": "error",
        "latency_ms": 0,
        "client_request_id": client_request_id or str(uuid.uuid4()),
        "provider_request_id": None,
        "cache_hit": False,
        "raw_response": "",
        "citations": [],
        "brands": [],
        "usage": {"input_tokens": None, "output_tokens": None},
        "error": error,
    }


if __name__ == "__main__":
    main()
