"""Escritura incremental a archivos JSONL."""

import json
from pathlib import Path


def append_record(filepath: str, record: dict) -> None:
    """Escribe un registro JSON en una línea al final del archivo."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()


def load_existing_keys(filepath: str) -> set[str]:
    """Carga las claves '{query_id}::{model_source}' ya existentes en el JSONL."""
    path = Path(filepath)
    keys = set()
    if not path.exists():
        return keys
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                qid = record.get("query_id", "")
                ms = record.get("model_source", "")
                if qid and ms:
                    keys.add(f"{qid}::{ms}")
            except json.JSONDecodeError:
                continue
    return keys
