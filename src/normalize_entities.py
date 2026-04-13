#!/usr/bin/env python3
"""SignalOrbit — Normalizador determinista de entidades.

Lee parsed_records.jsonl, normaliza nombres de marcas usando brand_aliases.csv,
y produce normalized_records.csv con KPIs calculados.

Uso:
    python -m src.normalize_entities
    python -m src.normalize_entities --input data/parsed/parsed_records.jsonl --output data/final/normalized_records.csv
"""

import argparse
import csv
import json
from pathlib import Path
from collections import defaultdict

from src.logger import get_logger

log = get_logger(__name__)


# Aliases por defecto (se amplían con brand_aliases.csv)
DEFAULT_ALIASES = {
    # Travel
    "booking": "booking.com",
    "booking.com": "booking.com",
    "booking com": "booking.com",
    "airbnb": "airbnb.com",
    "airbnb.com": "airbnb.com",
    "expedia": "expedia.com",
    "expedia.com": "expedia.com",
    "skyscanner": "skyscanner.com",
    "kayak": "kayak.com",
    "tripadvisor": "tripadvisor.com",
    "trip advisor": "tripadvisor.com",
    # SaaS / CRM
    "hubspot": "hubspot.com",
    "hub spot": "hubspot.com",
    "hubspot.com": "hubspot.com",
    "salesforce": "salesforce.com",
    "salesforce.com": "salesforce.com",
    "pipedrive": "pipedrive.com",
    "pipedrive.com": "pipedrive.com",
    "zoho": "zoho.com",
    "zoho crm": "zoho.com",
    "zoho.com": "zoho.com",
    "monday": "monday.com",
    "monday.com": "monday.com",
    # Retail / Running
    "nike": "nike.com",
    "nike.com": "nike.com",
    "adidas": "adidas.com",
    "adidas.com": "adidas.com",
    "asics": "asics.com",
    "asics.com": "asics.com",
    "new balance": "new-balance.com",
    "new-balance": "new-balance.com",
    "new balance.com": "new-balance.com",
    "new-balance.com": "new-balance.com",
    "hoka": "hoka.com",
    "hoka.com": "hoka.com",
    "hoka one one": "hoka.com",
    "brooks": "brooksrunning.com",
    "saucony": "saucony.com",
    "mizuno": "mizuno.com",
    "puma": "puma.com",
}


def load_aliases(filepath: str) -> dict[str, str]:
    """Carga aliases desde CSV. Formato: alias,canonical"""
    aliases = dict(DEFAULT_ALIASES)
    path = Path(filepath)
    if not path.exists():
        return aliases
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            alias = row.get("alias", "").strip().lower()
            canonical = row.get("canonical", "").strip().lower()
            if alias and canonical:
                aliases[alias] = canonical
    return aliases


def normalize_brand(name_raw: str, aliases: dict[str, str]) -> str:
    """Normaliza un nombre de marca usando el diccionario de aliases."""
    key = name_raw.strip().lower()
    return aliases.get(key, key)


def process_records(input_path: str, output_path: str, aliases_path: str):
    """Lee parsed_records.jsonl, normaliza y produce normalized_records.csv."""
    aliases = load_aliases(aliases_path)

    path = Path(input_path)
    if not path.exists():
        log.error("Input not found", extra={"path": input_path})
        return

    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                log.warning("Skipping malformed JSON line", extra={"path": input_path})
                continue

    if not records:
        log.warning("No records found", extra={"path": input_path})
        return

    # Flatten: one row per brand mention
    rows = []
    for rec in records:
        query_id = rec.get("query_id", "")
        model_source = rec.get("model_source", "")
        query_family = rec.get("query_family", "")
        query_prompt = rec.get("query_prompt", "")
        brand_domain = rec.get("brand_domain", "")
        brand_present = rec.get("brand_present", False)

        brands = rec.get("brands_extracted", [])
        if not brands:
            # Record with no brands still gets a row
            rows.append({
                "query_id": query_id,
                "model_source": model_source,
                "query_family": query_family,
                "brand_domain": brand_domain,
                "brand_present": brand_present,
                "name_raw": "",
                "name_normalized": "",
                "is_recommended": False,
                "recommendation_rank": 0,
                "sentiment": "",
                "citation_type": "",
                "context": "",
                "n_citations": len(rec.get("citations", [])),
                "owned_count": rec.get("owned_vs_earned", {}).get("owned", 0),
                "earned_count": rec.get("owned_vs_earned", {}).get("earned", 0),
                "marketplace_count": rec.get("owned_vs_earned", {}).get("marketplace", 0),
                "ugc_count": rec.get("owned_vs_earned", {}).get("ugc", 0),
            })
        else:
            for brand in brands:
                name_raw = brand.get("name_raw", "")
                name_normalized = normalize_brand(name_raw, aliases)
                rows.append({
                    "query_id": query_id,
                    "model_source": model_source,
                    "query_family": query_family,
                    "brand_domain": brand_domain,
                    "brand_present": brand_present,
                    "name_raw": name_raw,
                    "name_normalized": name_normalized,
                    "is_recommended": brand.get("is_recommended", False),
                    "recommendation_rank": brand.get("recommendation_rank", 0),
                    "sentiment": brand.get("sentiment", ""),
                    "citation_type": brand.get("citation_type", ""),
                    "context": brand.get("context", ""),
                    "n_citations": len(rec.get("citations", [])),
                    "owned_count": rec.get("owned_vs_earned", {}).get("owned", 0),
                    "earned_count": rec.get("owned_vs_earned", {}).get("earned", 0),
                    "marketplace_count": rec.get("owned_vs_earned", {}).get("marketplace", 0),
                    "ugc_count": rec.get("owned_vs_earned", {}).get("ugc", 0),
                })

    # Write CSV
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "query_id", "model_source", "query_family", "brand_domain", "brand_present",
        "name_raw", "name_normalized", "is_recommended", "recommendation_rank",
        "sentiment", "citation_type", "context", "n_citations",
        "owned_count", "earned_count", "marketplace_count", "ugc_count",
    ]
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    log.info(
        "Normalization complete",
        extra={
            "input_records": len(records),
            "output_rows": len(rows),
            "unique_brands": len(set(r["name_normalized"] for r in rows if r["name_normalized"])),
            "output": output_path,
        },
    )


def main():
    parser = argparse.ArgumentParser(description="SignalOrbit Entity Normalizer")
    parser.add_argument("--input", default="data/parsed/parsed_records.jsonl",
                        help="Path to parsed_records.jsonl")
    parser.add_argument("--output", default="data/final/normalized_records.csv",
                        help="Path to output CSV")
    parser.add_argument("--aliases", default="data/brand_aliases.csv",
                        help="Path to brand_aliases.csv")
    args = parser.parse_args()

    process_records(args.input, args.output, args.aliases)


if __name__ == "__main__":
    main()
