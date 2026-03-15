"""Lectura y filtrado de prompt_pack_v1.csv."""

import csv
from pathlib import Path

REQUIRED_FIELDS = {"query_id", "query_family", "prompt_text", "priority", "active"}
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}


def load_prompts(filepath: str, priority_filter: str | None = None) -> list[dict]:
    """Carga prompts del CSV, filtra por active=true y priority."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Prompt pack not found: {filepath}")

    prompts = []
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):
            # Validar campos obligatorios
            missing = REQUIRED_FIELDS - set(row.keys())
            if missing:
                print(f"  [WARN] Row {i}: missing fields {missing}, skipping")
                continue

            # Filtrar active
            if row.get("active", "").strip().lower() != "true":
                continue

            # Filtrar priority
            if priority_filter and row.get("priority", "").strip() != priority_filter:
                continue

            prompts.append(row)

    # Ordenar por priority
    prompts.sort(key=lambda r: PRIORITY_ORDER.get(r.get("priority", "P2"), 99))
    return prompts
