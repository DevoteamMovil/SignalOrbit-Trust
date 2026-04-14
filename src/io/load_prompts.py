"""Lectura y filtrado de prompt_pack_v1.csv."""

import csv
from pathlib import Path

from src.logger import get_logger

log = get_logger(__name__)

REQUIRED_FIELDS = {"query_id", "query_family", "prompt_text", "priority", "active"}
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}
VALID_PRIORITIES = set(PRIORITY_ORDER.keys())
VALID_ACTIVE_VALUES = {"true", "false", "1", "0", "yes", "no"}


def load_prompts(filepath: str, priority_filter: str | None = None) -> list[dict]:
    """Carga prompts del CSV, filtra por active=true y priority.

    Emite warnings estructurados para:
    - Filas con campos obligatorios ausentes
    - Valores de 'active' no reconocidos (e.g. "True", "TRUE", "yes")
    - Valores de 'priority' fuera del rango conocido (e.g. "p0", "P3")
    """
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
                log.warning(
                    "Row missing required fields, skipping",
                    extra={"row": i, "missing": sorted(missing)},
                )
                continue

            raw_active = row.get("active", "").strip()
            raw_priority = row.get("priority", "").strip()

            # Warn on unrecognised 'active' values before normalising
            if raw_active.lower() not in VALID_ACTIVE_VALUES:
                log.warning(
                    "Unrecognised 'active' value — row will be skipped",
                    extra={"row": i, "query_id": row.get("query_id"), "active": raw_active},
                )

            # Filtrar active (only exact lowercase "true" / "1" / "yes" pass)
            if raw_active.lower() != "true":
                continue

            # Warn on unknown priority values (still load, just flag it)
            if raw_priority not in VALID_PRIORITIES:
                log.warning(
                    "Unknown priority value",
                    extra={"row": i, "query_id": row.get("query_id"), "priority": raw_priority},
                )

            # Filtrar priority
            if priority_filter and raw_priority != priority_filter:
                continue

            prompts.append(row)

    # Ordenar por priority
    prompts.sort(key=lambda r: PRIORITY_ORDER.get(r.get("priority", "P2"), 99))
    return prompts
