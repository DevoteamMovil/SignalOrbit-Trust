#!/usr/bin/env python3
"""SignalOrbit — Trust Dashboard.

Dashboard unificado con tres secciones:
1. Discovery: Share of Model Voice, Win Rate, Citation Mix, Cross-Model Divergence
2. Integrity: Risk Score, Poisoning Signals, IOCs, MITRE mapping
3. Search Reality: Branded vs Non-Branded, GEO-to-SEO Gap

Uso:
    streamlit run src/dashboard_app.py
    streamlit run src/dashboard_app.py -- --mock
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from collections import defaultdict

import streamlit as st

# ─── Paths ──────────────────────────────────────────────────────────
DATA_DIR = Path("data")
MOCK_DIR = DATA_DIR / "mock"
NORMALIZED_PATH = DATA_DIR / "final" / "normalized_records.csv"
MOCK_DATA_PATH = MOCK_DIR / "mock_data.csv"
INTEGRITY_PATH = DATA_DIR / "integrity" / "integrity_events.jsonl"
MOCK_INTEGRITY_PATH = MOCK_DIR / "mock_integrity_events.jsonl"
GSC_PATH = DATA_DIR / "final" / "gsc_metrics.csv"
MOCK_GSC_PATH = MOCK_DIR / "gsc_export.csv"


# ─── Data loaders ──────────────────────────────────────────────────
@st.cache_data
def load_normalized(path: str) -> list[dict]:
    """Carga normalized_records.csv o mock_data.csv."""
    p = Path(path)
    if not p.exists():
        return []
    rows = []
    with open(p, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["is_recommended"] = row.get("is_recommended", "").lower() in ("true", "1", "yes")
            row["brand_present"] = row.get("brand_present", "").lower() in ("true", "1", "yes")
            try:
                row["recommendation_rank"] = int(float(row.get("recommendation_rank", 0)))
            except (ValueError, TypeError):
                row["recommendation_rank"] = 0
            rows.append(row)
    return rows


@st.cache_data
def load_integrity(path: str) -> list[dict]:
    """Carga integrity_events.jsonl."""
    p = Path(path)
    if not p.exists():
        return []
    events = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


@st.cache_data
def load_gsc(path: str) -> list[dict]:
    """Carga gsc_metrics.csv."""
    p = Path(path)
    if not p.exists():
        return []
    rows = []
    with open(p, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                row["clicks"] = int(float(row.get("clicks", 0)))
                row["impressions"] = int(float(row.get("impressions", 0)))
                row["ctr"] = float(row.get("ctr", 0))
                row["position"] = float(row.get("position", 0))
            except (ValueError, TypeError):
                pass
            rows.append(row)
    return rows


# ─── KPI calculators ───────────────────────────────────────────────
def calc_share_of_model_voice(data: list[dict], brand_domain: str) -> dict:
    """% de respuestas donde aparece la marca, por modelo."""
    model_queries = defaultdict(set)
    model_present = defaultdict(set)
    for row in data:
        ms = row.get("model_source", "")
        qid = row.get("query_id", "")
        model_queries[ms].add(qid)
        if row.get("brand_present"):
            model_present[ms].add(qid)

    result = {}
    for ms in model_queries:
        total = len(model_queries[ms])
        present = len(model_present[ms])
        result[ms] = round(present / total * 100, 1) if total > 0 else 0
    return result


def calc_win_rate(data: list[dict], brand_domain: str) -> dict:
    """% de veces que la marca es rank 1, por modelo."""
    model_queries = defaultdict(set)
    model_wins = defaultdict(set)
    for row in data:
        ms = row.get("model_source", "")
        qid = row.get("query_id", "")
        normalized = row.get("name_normalized", "")
        model_queries[ms].add(qid)
        if normalized == brand_domain and row.get("recommendation_rank") == 1:
            model_wins[ms].add(qid)

    result = {}
    for ms in model_queries:
        total = len(model_queries[ms])
        wins = len(model_wins[ms])
        result[ms] = round(wins / total * 100, 1) if total > 0 else 0
    return result


def calc_citation_mix(data: list[dict]) -> dict:
    """Distribución de owned/earned/marketplace/ugc."""
    counts = {"owned": 0, "earned": 0, "marketplace": 0, "official": 0, "review": 0, "ugc": 0}
    for row in data:
        ct = row.get("citation_type", "unknown")
        if ct in counts:
            counts[ct] += 1
    total = sum(counts.values())
    if total == 0:
        return counts
    return {k: round(v / total * 100, 1) for k, v in counts.items()}


def calc_brand_rankings(data: list[dict]) -> list[dict]:
    """Ranking de marcas por frecuencia de aparición, por modelo."""
    model_brands = defaultdict(lambda: defaultdict(int))
    for row in data:
        ms = row.get("model_source", "")
        name = row.get("name_normalized", "")
        if name:
            model_brands[ms][name] += 1

    rankings = []
    for ms, brands in model_brands.items():
        for brand, count in sorted(brands.items(), key=lambda x: -x[1]):
            rankings.append({"model": ms, "brand": brand, "mentions": count})
    return rankings


# ─── Dashboard ─────────────────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="SignalOrbit Trust Dashboard",
        page_icon="🛡️",
        layout="wide",
    )

    st.title("SignalOrbit — AI Discovery Trust Layer")
    st.caption("See where your brand appears in AI discovery — and whether that visibility is organic, missing, or potentially manipulated.")

    # Determine data sources (real or mock)
    use_mock = not NORMALIZED_PATH.exists()

    norm_path = str(MOCK_DATA_PATH) if use_mock else str(NORMALIZED_PATH)
    int_path = str(MOCK_INTEGRITY_PATH) if not INTEGRITY_PATH.exists() else str(INTEGRITY_PATH)
    gsc_path = str(MOCK_GSC_PATH) if not GSC_PATH.exists() else str(GSC_PATH)

    if use_mock:
        st.info("Mostrando datos de demo (mock). Ejecuta el pipeline completo para datos reales.", icon="ℹ️")

    data = load_normalized(norm_path)
    integrity = load_integrity(int_path)
    gsc = load_gsc(gsc_path)

    # Sidebar: filters
    st.sidebar.header("Filtros")

    # Get unique verticals/brands
    brand_domains = sorted(set(r.get("brand_domain", "") for r in data if r.get("brand_domain")))
    selected_brand = st.sidebar.selectbox("Marca principal", brand_domains if brand_domains else ["booking.com"])

    models = sorted(set(r.get("model_source", "") for r in data if r.get("model_source")))
    selected_models = st.sidebar.multiselect("Modelos", models, default=models)

    families = sorted(set(r.get("query_family", "") for r in data if r.get("query_family")))
    selected_families = st.sidebar.multiselect("Familias de query", families, default=families)

    # Filter data
    filtered = [
        r for r in data
        if r.get("model_source") in selected_models
        and r.get("query_family") in selected_families
        and r.get("brand_domain") == selected_brand
    ]

    # ─── Tabs ──────────────────────────────────────────────────
    tab1, tab2, tab3 = st.tabs(["Discovery", "Integrity", "Search Reality"])

    # ═══ TAB 1: DISCOVERY ═══════════════════════════════════════
    with tab1:
        st.header("Discovery Monitor")

        if not filtered:
            st.warning("No hay datos para los filtros seleccionados.")
        else:
            # KPI Row
            somv = calc_share_of_model_voice(filtered, selected_brand)
            winrate = calc_win_rate(filtered, selected_brand)

            col1, col2, col3 = st.columns(3)

            avg_somv = sum(somv.values()) / len(somv) if somv else 0
            avg_wr = sum(winrate.values()) / len(winrate) if winrate else 0
            n_brands = len(set(r.get("name_normalized", "") for r in filtered if r.get("name_normalized")))

            col1.metric("Share of Model Voice (avg)", f"{avg_somv:.1f}%")
            col2.metric("Win Rate (avg)", f"{avg_wr:.1f}%")
            col3.metric("Marcas detectadas", n_brands)

            # SoMV by model
            st.subheader("Share of Model Voice por modelo")
            somv_cols = st.columns(len(somv))
            for i, (model, pct) in enumerate(sorted(somv.items())):
                model_short = model.replace("openai_gpt_4_1", "GPT-4.1") \
                                   .replace("google_gemini_2_5_pro", "Gemini 2.5 Pro") \
                                   .replace("anthropic_claude_sonnet_4_6", "Claude Sonnet")
                somv_cols[i].metric(model_short, f"{pct:.1f}%")

            # Win Rate by model
            st.subheader("Recommendation Win Rate por modelo")
            wr_cols = st.columns(len(winrate))
            for i, (model, pct) in enumerate(sorted(winrate.items())):
                model_short = model.replace("openai_gpt_4_1", "GPT-4.1") \
                                   .replace("google_gemini_2_5_pro", "Gemini 2.5 Pro") \
                                   .replace("anthropic_claude_sonnet_4_6", "Claude Sonnet")
                wr_cols[i].metric(model_short, f"{pct:.1f}%")

            # Citation Mix
            st.subheader("Citation Source Mix")
            citmix = calc_citation_mix(filtered)
            citmix_filtered = {k: v for k, v in citmix.items() if v > 0}
            if citmix_filtered:
                st.bar_chart(citmix_filtered)
            else:
                st.info("No hay datos de citation mix.")

            # Brand rankings table
            st.subheader("Ranking de marcas por modelo")
            rankings = calc_brand_rankings(filtered)
            if rankings:
                # Format as table
                import pandas as pd
                df_rank = pd.DataFrame(rankings)
                df_rank["model"] = df_rank["model"].replace({
                    "openai_gpt_4_1": "GPT-4.1",
                    "google_gemini_2_5_pro": "Gemini 2.5 Pro",
                    "anthropic_claude_sonnet_4_6": "Claude Sonnet",
                })
                pivot = df_rank.pivot_table(index="brand", columns="model", values="mentions", fill_value=0)
                pivot["Total"] = pivot.sum(axis=1)
                pivot = pivot.sort_values("Total", ascending=False)
                st.dataframe(pivot, use_container_width=True)

            # Cross-model divergence
            st.subheader("Cross-Model Divergence")
            brand_by_model = defaultdict(dict)
            for r in rankings:
                brand_by_model[r["brand"]][r["model"]] = r["mentions"]
            if len(brand_by_model) > 1:
                import pandas as pd
                df_div = pd.DataFrame(brand_by_model).T.fillna(0)
                st.bar_chart(df_div)

    # ═══ TAB 2: INTEGRITY ══════════════════════════════════════
    with tab2:
        st.header("Integrity Scanner")

        if not integrity:
            st.info("No se han detectado señales de AI Recommendation Poisoning.")
        else:
            # Summary metrics
            risk_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            for e in integrity:
                rl = e.get("risk_level", "low")
                risk_counts[rl] = risk_counts.get(rl, 0) + 1

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total alertas", len(integrity))
            col2.metric("Critical", risk_counts["critical"])
            col3.metric("High", risk_counts["high"])
            col4.metric("Medium + Low", risk_counts["medium"] + risk_counts["low"])

            # Average risk score
            avg_risk = sum(e.get("risk_score", 0) for e in integrity) / len(integrity)
            st.metric("Risk Score promedio", f"{avg_risk:.0f}/100")

            # Alerts table
            st.subheader("Alertas de poisoning detectadas")
            for i, event in enumerate(integrity):
                risk_level = event.get("risk_level", "low").upper()
                risk_score = event.get("risk_score", 0)
                domain = event.get("ai_target_domain", "")
                brand = event.get("brand_mentioned_in_prompt", "N/A")
                decoded = event.get("decoded_prompt", "")
                source = event.get("source_page_url", "")
                keywords = event.get("memory_keywords_found", [])
                mitre = event.get("mitre_atlas_tags", [])
                evidence = event.get("evidence_type", "")

                color = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(risk_level, "⚪")

                with st.expander(f"{color} {risk_level} ({risk_score}/100) — {domain} — {brand or 'Unknown brand'}"):
                    st.markdown(f"**Source page:** `{source}`")
                    st.markdown(f"**AI Target:** `{domain}`")
                    st.markdown(f"**Decoded prompt:** `{decoded}`")
                    st.markdown(f"**Memory keywords:** {', '.join(keywords) if keywords else 'None'}")
                    st.markdown(f"**MITRE ATLAS:** {', '.join(mitre)}")
                    st.markdown(f"**Evidence type:** {evidence}")
                    if brand:
                        st.markdown(f"**Brand mentioned:** {brand}")

            # AI target domains distribution
            st.subheader("Distribución por dominio AI objetivo")
            domain_counts = defaultdict(int)
            for e in integrity:
                domain_counts[e.get("ai_target_domain", "unknown")] += 1
            if domain_counts:
                st.bar_chart(domain_counts)

            # MITRE mapping
            st.subheader("Mapeo MITRE ATLAS")
            mitre_counts = defaultdict(int)
            for e in integrity:
                for tag in e.get("mitre_atlas_tags", []):
                    mitre_counts[tag] += 1
            mitre_descriptions = {
                "AML.T0051": "LLM Prompt Injection",
                "AML.T0080": "AI Agent Memory Poisoning",
            }
            for tag, count in sorted(mitre_counts.items()):
                desc = mitre_descriptions.get(tag, tag)
                st.markdown(f"- **{tag}** — {desc}: {count} eventos")

    # ═══ TAB 3: SEARCH REALITY ═════════════════════════════════
    with tab3:
        st.header("Search Reality")

        if not gsc:
            st.info("No hay datos de Search Console. Importa un CSV con: python -m src.connect_search_console --csv data/mock/gsc_export.csv")
        else:
            # Summary
            total_clicks = sum(r.get("clicks", 0) for r in gsc)
            total_impressions = sum(r.get("impressions", 0) for r in gsc)
            brand_clicks = sum(r.get("clicks", 0) for r in gsc if r.get("brand_class") == "brand")
            nonbrand_clicks = sum(r.get("clicks", 0) for r in gsc if r.get("brand_class") == "nonbrand")

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Clicks", f"{total_clicks:,}")
            col2.metric("Total Impressions", f"{total_impressions:,}")
            col3.metric("Brand Clicks", f"{brand_clicks:,}")
            col4.metric("Non-Brand Clicks", f"{nonbrand_clicks:,}")

            # Brand vs non-brand
            st.subheader("Brand vs Non-Brand")
            brand_pct = round(brand_clicks / total_clicks * 100, 1) if total_clicks > 0 else 0
            st.bar_chart({"Brand": brand_pct, "Non-Brand": round(100 - brand_pct, 1)})

            # Top queries
            st.subheader("Top queries por clicks")
            import pandas as pd
            df_gsc = pd.DataFrame(gsc)
            if "clicks" in df_gsc.columns:
                df_top = df_gsc.nlargest(10, "clicks")[["query", "clicks", "impressions", "ctr", "position", "brand_class"]]
                st.dataframe(df_top, use_container_width=True)

            # GEO-to-SEO Gap
            st.subheader("GEO-to-SEO Gap")
            st.markdown("""
            **Concepto:** Compara la visibilidad de la marca en respuestas generativas (Share of Model Voice)
            con su rendimiento SEO real (clicks non-brand / total clicks).

            Una marca con alto SoMV pero bajo rendimiento SEO tiene una **oportunidad GEO**.
            Una marca con bajo SoMV pero alto SEO tiene un **riesgo de erosión**.
            """)

            if data:
                somv_avg = calc_share_of_model_voice(filtered, selected_brand)
                geo_score = sum(somv_avg.values()) / len(somv_avg) if somv_avg else 0
                seo_score = round(nonbrand_clicks / total_clicks * 100, 1) if total_clicks > 0 else 0

                gcol1, gcol2, gcol3 = st.columns(3)
                gcol1.metric("GEO Score (SoMV avg)", f"{geo_score:.1f}%")
                gcol2.metric("SEO Score (NB click share)", f"{seo_score:.1f}%")
                delta = round(geo_score - seo_score, 1)
                gcol3.metric("GEO-SEO Delta", f"{delta:+.1f}pp",
                             delta_color="normal" if delta >= 0 else "inverse")


if __name__ == "__main__":
    main()
