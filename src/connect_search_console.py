#!/usr/bin/env python3
"""SignalOrbit — Search Console Connector.

Importa datos de Google Search Console por CSV o API.
Produce search_performance_record.jsonl / gsc_metrics.csv
con clasificación brand/nonbrand.

Uso:
    python -m src.connect_search_console --csv data/mock/gsc_export.csv
    python -m src.connect_search_console --csv data/mock/gsc_export.csv --output data/final/gsc_metrics.csv
"""

import argparse
import csv
from pathlib import Path
from collections import defaultdict

from src.logger import get_logger

log = get_logger(__name__)


# Brand keywords por vertical (diccionario auxiliar para clasificación)
BRAND_KEYWORDS = {
    # Travel
    "booking": "booking.com",
    "airbnb": "airbnb.com",
    "expedia": "expedia.com",
    "skyscanner": "skyscanner.com",
    "tripadvisor": "tripadvisor.com",
    "kayak": "kayak.com",
    # SaaS / CRM
    "hubspot": "hubspot.com",
    "salesforce": "salesforce.com",
    "pipedrive": "pipedrive.com",
    "zoho": "zoho.com",
    "monday": "monday.com",
    # Retail / Running
    "nike": "nike.com",
    "adidas": "adidas.com",
    "asics": "asics.com",
    "new balance": "new-balance.com",
    "hoka": "hoka.com",
    "brooks": "brooksrunning.com",
    "saucony": "saucony.com",
}


def classify_brand(query: str, site_domain: str = "") -> str:
    """Clasifica una query como brand, nonbrand o unknown.

    Regla: si la query contiene algún brand keyword → brand.
    Si el site_domain está en la query → brand.
    Sino → nonbrand.
    """
    q_lower = query.lower()

    # Check site domain first
    if site_domain:
        domain_name = site_domain.replace("www.", "").split(".")[0]
        if domain_name and domain_name in q_lower:
            return "brand"

    # Check brand keywords
    for keyword in BRAND_KEYWORDS:
        if keyword in q_lower:
            return "brand"

    return "nonbrand"


def _parse_number(value: str, is_float: bool = False):
    """Parsea un número de un CSV de Search Console (soporta formato EU y US)."""
    if not value or value.strip() == "":
        return 0.0 if is_float else 0
    value = value.strip().replace(",", ".")
    try:
        return float(value) if is_float else int(float(value))
    except ValueError:
        return 0.0 if is_float else 0


def import_from_csv(csv_path: str, output_path: str, site_domain: str = ""):
    """Importa datos de un CSV de Search Console y produce gsc_metrics.csv.

    Acepta CSVs con columnas:
    - Google SC export: Top queries/Top pages format
    - Custom: query, page, clicks, impressions, ctr, position, date
    """
    path = Path(csv_path)
    if not path.exists():
        log.error("CSV not found", extra={"path": csv_path})
        return

    rows = []
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        # Map headers (soportar español e inglés)
        header_map = {}
        for h in headers:
            h_lower = h.lower().strip()
            if h_lower in ("query", "consulta", "top queries"):
                header_map["query"] = h
            elif h_lower in ("page", "página", "url", "top pages"):
                header_map["page"] = h
            elif h_lower in ("clicks", "clics"):
                header_map["clicks"] = h
            elif h_lower in ("impressions", "impresiones"):
                header_map["impressions"] = h
            elif h_lower in ("ctr"):
                header_map["ctr"] = h
            elif h_lower in ("position", "posición"):
                header_map["position"] = h
            elif h_lower in ("date", "fecha"):
                header_map["date"] = h
            elif h_lower in ("site", "sitio"):
                header_map["site"] = h

        for row in reader:
            query = row.get(header_map.get("query", "query"), "").strip()
            page = row.get(header_map.get("page", "page"), "").strip()
            clicks = _parse_number(row.get(header_map.get("clicks", "clicks"), "0"))
            impressions = _parse_number(row.get(header_map.get("impressions", "impressions"), "0"))
            ctr_raw = row.get(header_map.get("ctr", "ctr"), "0")
            ctr = _parse_number(ctr_raw.replace("%", ""), is_float=True)
            if "%" in str(ctr_raw):
                ctr = ctr / 100.0
            position = _parse_number(row.get(header_map.get("position", "position"), "0"), is_float=True)
            date = row.get(header_map.get("date", "date"), "").strip()
            site = row.get(header_map.get("site", "site"), site_domain).strip()

            if not query:
                continue

            brand_class = classify_brand(query, site)

            rows.append({
                "site": site,
                "date": date,
                "query": query,
                "page": page,
                "clicks": clicks,
                "impressions": impressions,
                "ctr": round(ctr, 4),
                "position": round(position, 1),
                "brand_class": brand_class,
            })

    if not rows:
        log.warning("No valid rows found in CSV", extra={"path": csv_path})
        return

    # Write output
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["site", "date", "query", "page", "clicks", "impressions", "ctr", "position", "brand_class"]
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Summary
    brand_count = sum(1 for r in rows if r["brand_class"] == "brand")
    nonbrand_count = sum(1 for r in rows if r["brand_class"] == "nonbrand")
    total_clicks = sum(r["clicks"] for r in rows)
    total_impressions = sum(r["impressions"] for r in rows)

    log.info(
        "Search Console import complete",
        extra={
            "input": csv_path,
            "rows": len(rows),
            "brand": brand_count,
            "nonbrand": nonbrand_count,
            "total_clicks": total_clicks,
            "total_impressions": total_impressions,
            "output": output_path,
        },
    )


def main():
    parser = argparse.ArgumentParser(description="SignalOrbit Search Console Connector")
    parser.add_argument("--csv", required=True,
                        help="Path to Search Console CSV export")
    parser.add_argument("--output", default="data/final/gsc_metrics.csv",
                        help="Path to output CSV")
    parser.add_argument("--site", default="",
                        help="Site domain for brand classification (e.g. booking.com)")
    args = parser.parse_args()

    import_from_csv(args.csv, args.output, args.site)


if __name__ == "__main__":
    main()
