#!/usr/bin/env python3
"""SignalOrbit — Parser estructurado de respuestas LLM.

Lee raw_responses.jsonl y extrae marcas, sentimiento, citas y contexto
usando un LLM como parser. Produce parsed_records.jsonl con el contrato
audit_record_canonical.

Uso:
    python -m src.parse_records
    python -m src.parse_records --input data/raw/raw_responses.jsonl --output data/parsed/parsed_records.jsonl
    python -m src.parse_records --parser-model openai
"""

import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.io.write_jsonl import append_record, load_existing_keys
from src.cache import disk_cache

# Prompt de parsing: extrae marcas, sentimiento, citas, ranking
PARSER_SYSTEM_PROMPT = """Eres un analizador de respuestas de modelos de lenguaje. Tu trabajo es extraer información estructurada de una respuesta generada por un LLM.

Dada una respuesta a una consulta del usuario, extrae:

1. MARCAS mencionadas: nombre exacto como aparece, si es recomendada, su posición relativa (rank), sentimiento (positive/neutral/negative/mixed), y tipo de cita si hay URL asociada.
2. CITAS o URLs mencionadas: la etiqueta o nombre del sitio, la URL si existe, y el tipo de fuente.
3. Si la marca principal (brand_domain) está presente en la respuesta.

Responde SOLO con un JSON válido, sin texto adicional ni markdown. El formato exacto es:

{
  "brands_extracted": [
    {
      "name_raw": "Nombre tal como aparece",
      "is_recommended": true,
      "recommendation_rank": 1,
      "sentiment": "positive",
      "citation_type": "owned",
      "context": "Frase relevante donde aparece"
    }
  ],
  "citations": [
    {
      "label": "Nombre del sitio",
      "url": "https://...",
      "source_type": "owned"
    }
  ],
  "brand_present": true
}

Reglas:
- recommendation_rank: 1 = primera recomendada, 2 = segunda, etc. 0 si se menciona pero no se recomienda explícitamente.
- sentiment: positive, neutral, negative, o mixed.
- citation_type y source_type: owned (sitio oficial de la marca), earned (prensa, blogs terceros), marketplace (Amazon, tienda online), review (sitio de reseñas), official (fuente gubernamental o institucional), ugc (Reddit, foros, redes sociales), unknown (no se puede determinar).
- brand_present: true si brand_domain o una variante clara de esa marca aparece en la respuesta.
- Si no hay marcas, devuelve brands_extracted como lista vacía.
- Si no hay citas/URLs, devuelve citations como lista vacía.
- NO inventes datos. Solo extrae lo que está en la respuesta."""


def _build_parser_prompt(raw_response: str, query_prompt: str, brand_domain: str) -> str:
    """Construye el prompt de usuario para el parser."""
    return f"""Analiza la siguiente respuesta de un modelo de lenguaje.

<query>{query_prompt}</query>

<brand_domain>{brand_domain}</brand_domain>

<response>
{raw_response}
</response>

Extrae las marcas, citas y determina si la marca principal está presente. Responde SOLO con JSON válido."""


def _parse_with_openai(prompt: str, system_prompt: str) -> dict:
    """Usa OpenAI como parser."""
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=1500,
    )
    text = response.choices[0].message.content or ""
    return _extract_json(text)


def _parse_with_gemini(prompt: str, system_prompt: str) -> dict:
    """Usa Gemini como parser."""
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    config = types.GenerateContentConfig(
        temperature=0.0,
        max_output_tokens=1500,
        system_instruction=system_prompt,
    )
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=config,
    )
    text = response.text or ""
    return _extract_json(text)


def _parse_with_anthropic(prompt: str, system_prompt: str) -> dict:
    """Usa Anthropic como parser."""
    from anthropic import Anthropic
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-sonnet-4-6",
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=1500,
    )
    text = response.content[0].text if response.content else ""
    return _extract_json(text)


def _extract_json(text: str) -> dict:
    """Extrae JSON de una respuesta que puede contener markdown u otro texto."""
    # Intenta parsear directamente
    text = text.strip()
    if text.startswith("```"):
        # Extraer bloque de código
        match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Intento: buscar el primer { ... } completo
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return {"brands_extracted": [], "citations": [], "brand_present": False}


def _get_parser_fn(parser_model: str):
    """Devuelve la función de parsing según el modelo elegido."""
    parsers = {
        "openai": _parse_with_openai,
        "gemini": _parse_with_gemini,
        "anthropic": _parse_with_anthropic,
    }
    if parser_model not in parsers:
        raise ValueError(f"Unknown parser model: {parser_model}. Use: {list(parsers.keys())}")
    return parsers[parser_model]


def _build_canonical_record(raw_record: dict, parsed: dict, brand_domain: str) -> dict:
    """Construye el audit_record_canonical a partir del raw + parsed."""
    brands = parsed.get("brands_extracted", [])
    citations = parsed.get("citations", [])
    brand_present = parsed.get("brand_present", False)

    # Calcular owned_vs_earned
    source_counts = {
        "owned": 0, "earned": 0, "marketplace": 0,
        "official": 0, "review": 0, "ugc": 0,
    }
    for c in citations:
        st = c.get("source_type", "unknown")
        if st in source_counts:
            source_counts[st] += 1

    return {
        "run_id": raw_record.get("run_id", ""),
        "query_id": raw_record.get("query_id", ""),
        "query_family": raw_record.get("query_family", ""),
        "query_prompt": raw_record.get("query_prompt", ""),
        "model_source": raw_record.get("model_source", ""),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "brand_domain": brand_domain,
        "brands_extracted": [
            {
                "name_raw": b.get("name_raw", ""),
                "name_normalized": "",  # Se llena en normalize_entities.py
                "is_recommended": b.get("is_recommended", False),
                "recommendation_rank": b.get("recommendation_rank", 0),
                "sentiment": b.get("sentiment", "neutral"),
                "citation_type": b.get("citation_type", "unknown"),
                "context": b.get("context", ""),
            }
            for b in brands
        ],
        "citations": [
            {
                "label": c.get("label", ""),
                "url": c.get("url", ""),
                "source_type": c.get("source_type", "unknown"),
            }
            for c in citations
        ],
        "owned_vs_earned": source_counts,
        "brand_present": brand_present,
        "notes": "",
    }


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="SignalOrbit Structured Parser")
    parser.add_argument("--input", default="data/raw/raw_responses.jsonl",
                        help="Path to raw_responses.jsonl")
    parser.add_argument("--output", default="data/parsed/parsed_records.jsonl",
                        help="Path to output parsed_records.jsonl")
    parser.add_argument("--parser-model", default="openai",
                        choices=["openai", "gemini", "anthropic"],
                        help="LLM to use for parsing (default: openai)")
    parser.add_argument("--brand-domain", default=None,
                        help="Override brand_domain for all records")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max records to parse (0 = all)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[ERROR] Input not found: {args.input}")
        return

    # Load raw records
    raw_records = []
    with open(input_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if record.get("status") == "ok" and record.get("raw_response"):
                    raw_records.append(record)
            except json.JSONDecodeError:
                continue

    if not raw_records:
        print("[WARN] No valid records found in input.")
        return

    if args.limit > 0:
        raw_records = raw_records[:args.limit]

    # Skip already parsed
    existing_keys = load_existing_keys(args.output)

    parse_fn = _get_parser_fn(args.parser_model)

    print("═" * 55)
    print("  SignalOrbit Structured Parser")
    print("═" * 55)
    print(f"  Input: {args.input}")
    print(f"  Records: {len(raw_records)} · Parser: {args.parser_model}")
    print("─" * 55)

    parsed_count = 0
    error_count = 0

    for i, raw in enumerate(raw_records, 1):
        query_id = raw.get("query_id", "")
        model_source = raw.get("model_source", "")
        composite_key = f"{query_id}::{model_source}"

        if composite_key in existing_keys:
            print(f"  [{i}/{len(raw_records)}] SKIP {composite_key}")
            continue

        # Determine brand_domain from prompt_pack or override
        brand_domain = args.brand_domain or raw.get("brand_domain", "") or "unknown"

        prompt = _build_parser_prompt(
            raw_response=raw["raw_response"],
            query_prompt=raw.get("query_prompt", ""),
            brand_domain=brand_domain,
        )

        # Check parser cache first
        parser_cache_key = disk_cache.make_key(
            f"parser:{args.parser_model}",
            raw["raw_response"],
            raw.get("query_prompt", ""),
            0.0,  # parser temperature is always 0
            0,    # placeholder
        )
        parser_cache_path = disk_cache.CACHE_DIR / f"parser_{parser_cache_key}.json"

        parsed = None
        if parser_cache_path.exists():
            try:
                with open(parser_cache_path, encoding="utf-8") as cf:
                    parsed = json.load(cf)
            except (json.JSONDecodeError, KeyError):
                parsed = None

        if parsed is None:
            try:
                parsed = parse_fn(prompt, PARSER_SYSTEM_PROMPT)
                # Cache the parser result
                disk_cache.CACHE_DIR.mkdir(parents=True, exist_ok=True)
                with open(parser_cache_path, "w", encoding="utf-8") as cf:
                    json.dump(parsed, cf, ensure_ascii=False)
            except Exception as e:
                error_count += 1
                print(f"  [{i}/{len(raw_records)}] ERROR {composite_key}: {e}")
                time.sleep(0.5)
                continue

        try:
            canonical = _build_canonical_record(raw, parsed, brand_domain)
            append_record(args.output, canonical)
            existing_keys.add(composite_key)
            parsed_count += 1

            n_brands = len(canonical["brands_extracted"])
            present = "YES" if canonical["brand_present"] else "no"
            print(f"  [{i}/{len(raw_records)}] OK {composite_key} · "
                  f"{n_brands} brands · present={present}")

        except Exception as e:
            error_count += 1
            print(f"  [{i}/{len(raw_records)}] ERROR {composite_key}: {e}")

        # Rate limit
        time.sleep(0.5)

    print("─" * 55)
    print(f"  Parsed: {parsed_count} · Errors: {error_count}")
    print(f"  Output: {args.output}")
    print("═" * 55)


if __name__ == "__main__":
    main()
