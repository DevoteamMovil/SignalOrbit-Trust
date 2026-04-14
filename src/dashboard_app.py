#!/usr/bin/env python3
"""SignalOrbit — Trust Dashboard.

Dashboard unificado con tres secciones:
1. Discovery: Share of Model Voice, Win Rate, Citation Mix, Memorization Divergence Index
2. Integrity: Risk Score, Poisoning Signals, IOCs, MITRE mapping
3. Search Reality: Branded vs Non-Branded, GEO-to-SEO Gap

Uso:
    streamlit run src/dashboard_app.py
    streamlit run src/dashboard_app.py -- --mock
"""

import csv
import json
from pathlib import Path
from collections import defaultdict

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from src.live_query import (
    run_live_query, get_available_models, model_label as live_model_label,
)

# ─── Theme ────────────────────────────────────────────────────────
PRIMARY_COLOR = "#8A2BE2"
NEUTRAL_COLOR = "#F0F0F0"
PURPLE_GRADIENT = ["#4B0082", "#8A2BE2", "#D8BFD8", "#E6E6FA"]
MODEL_DISPLAY_MAP = {
    "openai_gpt_4_1": "GPT-4.1",
    "openai_gpt_4_1_mini": "GPT-4.1 Mini",
    "openai_gpt_4_1_nano": "GPT-4.1 Nano",
    "openai_o4_mini": "o4-mini",
    "google_gemini_2_5_pro": "Gemini 2.5 Pro",
    "google_gemini_2_5_flash": "Gemini 2.5 Flash",
    "google_gemini_2_0_flash": "Gemini 2.0 Flash",
    "anthropic_claude_sonnet_4_6": "Claude Sonnet",
    "anthropic_claude_haiku_3_5": "Claude Haiku 3.5",
    "xai_grok_3": "Grok 3",
}

# ─── Paths ────────────────────────────────────────────────────────
DATA_DIR = Path("data")
MOCK_DIR = DATA_DIR / "mock"
NORMALIZED_PATH = DATA_DIR / "final" / "normalized_records.csv"
MOCK_DATA_PATH = MOCK_DIR / "mock_data.csv"
INTEGRITY_PATH = DATA_DIR / "integrity" / "integrity_events.jsonl"
MOCK_INTEGRITY_PATH = MOCK_DIR / "mock_integrity_events.jsonl"
GSC_PATH = DATA_DIR / "final" / "gsc_metrics.csv"
MOCK_GSC_PATH = MOCK_DIR / "gsc_export.csv"
RAW_RESPONSES_PATH = DATA_DIR / "raw" / "raw_responses.jsonl"
SNAPSHOT_PATH = DATA_DIR / "final" / "demo_snapshot.json"


def _model_label(raw: str) -> str:
    """Convierte model_source interno a label legible."""
    return MODEL_DISPLAY_MAP.get(raw, raw)


def _transparent_layout(**extra) -> dict:
    """Base layout Plotly con fondos transparentes."""
    base = dict(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=40, b=60, l=60, r=40),
        font=dict(size=14),
    )
    base.update(extra)
    return base


# ─── Data loaders ─────────────────────────────────────────────────
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


@st.cache_data
def load_raw_responses(path: str) -> list[dict]:
    """Carga raw_responses.jsonl para extraer logprobs y avg_logprob."""
    p = Path(path)
    if not p.exists():
        return []
    records = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("status") == "ok":
                    records.append(rec)
            except json.JSONDecodeError:
                continue
    return records


# ─── Snapshot helpers ─────────────────────────────────────────────
def save_snapshot(data: list[dict], integrity: list[dict], gsc: list[dict]) -> None:
    """Serializa el estado actual del dashboard a un JSON para demos offline."""
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": {
            "version": "2.0",
            "timestamp_utc": pd.Timestamp.utcnow().isoformat(),
            "records": len(data),
            "integrity_events": len(integrity),
            "gsc_rows": len(gsc),
        },
        "normalized": data,
        "integrity": integrity,
        "gsc": gsc,
    }
    tmp = SNAPSHOT_PATH.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, default=str)
        tmp.replace(SNAPSHOT_PATH)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def load_snapshot() -> tuple[list[dict], list[dict], list[dict]]:
    """Carga datos desde el snapshot JSON. Devuelve (data, integrity, gsc)."""
    with open(SNAPSHOT_PATH, encoding="utf-8") as f:
        snap = json.load(f)
    return snap.get("normalized", []), snap.get("integrity", []), snap.get("gsc", [])


# ─── KPI calculators ──────────────────────────────────────────────
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


# ─── Dashboard ────────────────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="SignalOrbit Trust Dashboard",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title("SignalOrbit — AI Discovery Trust Layer")
    st.caption("See where your brand appears in AI discovery — and whether that visibility is organic, missing, or potentially manipulated.")

    # ── Sidebar ───────────────────────────────────────────────
    st.sidebar.markdown("### System Controls")

    # Offline snapshot toggle
    use_snapshot = st.sidebar.toggle(
        "Load Offline Snapshot",
        value=False,
        help="Load a previously saved demo snapshot instead of live data files.",
    )

    if use_snapshot:
        if not SNAPSHOT_PATH.exists():
            st.sidebar.error("No snapshot found. Generate one first using the button below.")
            st.stop()
        data, integrity, gsc = load_snapshot()
        st.sidebar.info("Running on offline snapshot.", icon="📦")
    else:
        # ── Data sources ──────────────────────────────────────
        use_mock = not NORMALIZED_PATH.exists()
        norm_path = str(MOCK_DATA_PATH) if use_mock else str(NORMALIZED_PATH)
        int_path = str(MOCK_INTEGRITY_PATH) if not INTEGRITY_PATH.exists() else str(INTEGRITY_PATH)
        gsc_path = str(MOCK_GSC_PATH) if not GSC_PATH.exists() else str(GSC_PATH)

        if use_mock:
            st.info("Showing demo data (mock). Run the full pipeline for live results.", icon="ℹ️")

        data = load_normalized(norm_path)
        integrity = load_integrity(int_path)
        gsc = load_gsc(gsc_path)

        # Save snapshot button
        if data and st.sidebar.button("💾 Save Demo Snapshot", use_container_width=True):
            try:
                save_snapshot(data, integrity, gsc)
                st.sidebar.success("Snapshot saved.", icon="✅")
            except Exception as e:
                st.sidebar.error(f"Snapshot failed: {e}")

    brand_domains = sorted(set(r.get("brand_domain", "") for r in data if r.get("brand_domain")))
    selected_brand = st.sidebar.selectbox("Brand Scope", brand_domains if brand_domains else ["N/A"])

    models = sorted(set(r.get("model_source", "") for r in data if r.get("model_source")))
    selected_models = st.sidebar.multiselect("Models", models, default=models,
                                              format_func=_model_label)

    families = sorted(set(r.get("query_family", "") for r in data if r.get("query_family")))
    selected_families = st.sidebar.multiselect("Query Families", families, default=families)

    # Filter
    filtered = [
        r for r in data
        if r.get("model_source") in selected_models
        and r.get("query_family") in selected_families
        and r.get("brand_domain") == selected_brand
    ]

    # ── Tabs ──────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs(["Discovery", "Integrity", "Search Reality", "⚡ Live Explorer"])

    # ═══════════════════════════════════════════════════════════
    #  TAB 1 — DISCOVERY
    # ═══════════════════════════════════════════════════════════
    with tab1:
        if not filtered:
            st.warning("No data for the selected filters.")
        else:
            # ── KPI Row ───────────────────────────────────────
            somv = calc_share_of_model_voice(filtered, selected_brand)
            winrate = calc_win_rate(filtered, selected_brand)
            avg_somv = sum(somv.values()) / len(somv) if somv else 0
            avg_wr = sum(winrate.values()) / len(winrate) if winrate else 0

            # GEO-to-SEO delta for KPI row
            total_clicks = sum(r.get("clicks", 0) for r in gsc)
            nonbrand_clicks = sum(r.get("clicks", 0) for r in gsc if r.get("brand_class") == "nonbrand")
            seo_baseline = round(nonbrand_clicks / total_clicks * 100, 1) if total_clicks > 0 else 0
            geo_seo_delta = round(avg_somv - seo_baseline, 1)

            k1, k2, k3 = st.columns(3)
            k1.metric("Share of Model Voice", f"{avg_somv:.1f}%",
                       help="Percentage of AI responses containing the brand.")
            k2.metric("Recommendation Win Rate", f"{avg_wr:.1f}%",
                       help="Percentage of appearances where brand is Rank 1.")
            k3.metric("GEO-to-SEO Delta", f"{geo_seo_delta:+.1f} pts",
                       delta=f"{geo_seo_delta:+.1f} vs SEO Baseline")

            st.markdown("---")

            # ── Visualization grid 2x2 ───────────────────────
            df_filtered = pd.DataFrame(filtered)
            df_filtered["model_label"] = df_filtered["model_source"].map(MODEL_DISPLAY_MAP).fillna(df_filtered["model_source"])

            col_v1, col_v2 = st.columns(2)

            # ▸ Model Visibility Distribution (stacked bar)
            with col_v1:
                st.subheader("Model Visibility Distribution")
                vis_df = df_filtered.groupby(["model_label", "name_normalized"]).size().reset_index(name="mentions")
                color_map = {selected_brand: PRIMARY_COLOR}
                for b in vis_df["name_normalized"].unique():
                    if b != selected_brand:
                        color_map[b] = NEUTRAL_COLOR
                fig_bar = px.bar(
                    vis_df, x="model_label", y="mentions", color="name_normalized",
                    color_discrete_map=color_map, barmode="relative",
                )
                fig_bar.update_layout(**_transparent_layout(
                    xaxis_title="", yaxis_title="Mentions", showlegend=False,
                    height=420,
                ))
                st.plotly_chart(fig_bar, use_container_width=True)

            # ▸ Sentiment Radar
            with col_v2:
                st.subheader("Statistical Sentiment Profile")
                brand_rows = df_filtered[df_filtered["name_normalized"] == selected_brand].copy()
                if not brand_rows.empty and "sentiment" in brand_rows.columns:
                    # Count sentiment occurrences per model
                    all_sentiments = ["neutral", "positive", "mixed", "negative"]
                    sent_counts = (
                        brand_rows.groupby(["model_label", "sentiment"])
                        .size()
                        .reset_index(name="count")
                    )
                    model_colors = [PRIMARY_COLOR, "#D8BFD8", "#4B0082", "#E6E6FA"]
                    fig_radar = go.Figure()
                    for i, model in enumerate(sorted(sent_counts["model_label"].unique())):
                        model_data = sent_counts[sent_counts["model_label"] == model]
                        # Build values for each sentiment axis
                        vals = []
                        for s in all_sentiments:
                            match = model_data[model_data["sentiment"] == s]
                            vals.append(int(match["count"].iloc[0]) if not match.empty else 0)
                        # Close the polygon
                        vals_closed = vals + [vals[0]]
                        theta_closed = [s.capitalize() for s in all_sentiments] + [all_sentiments[0].capitalize()]
                        fig_radar.add_trace(go.Scatterpolar(
                            r=vals_closed, theta=theta_closed,
                            fill="toself", name=model,
                            line_color=model_colors[i % len(model_colors)],
                            fillcolor=f"rgba({','.join(str(int(model_colors[i % len(model_colors)].lstrip('#')[j:j+2], 16)) for j in (0,2,4))},0.25)",
                        ))
                    max_count = sent_counts["count"].max() if not sent_counts.empty else 1
                    fig_radar.update_layout(
                        polar=dict(
                            radialaxis=dict(visible=True, range=[0, max_count + 1],
                                            showticklabels=True, tickfont=dict(size=11)),
                            angularaxis=dict(tickfont=dict(size=14)),
                        ),
                        showlegend=True,
                        legend=dict(font=dict(size=12), orientation="h",
                                    yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
                        height=450,
                        margin=dict(t=40, b=60, l=40, r=40),
                    )
                    st.plotly_chart(fig_radar, use_container_width=True)
                else:
                    st.info("No sentiment data available for the current selection.")

            st.markdown("<br>", unsafe_allow_html=True)
            col_v3, col_v4 = st.columns(2)

            # ▸ Cross-Model Consistency (grouped bar)
            with col_v3:
                st.subheader("Cross-Model Consistency")
                consistency_df = (
                    df_filtered.groupby(["model_label", "name_normalized"])
                    .size()
                    .reset_index(name="mentions")
                )
                if not consistency_df.empty:
                    # Sort brands by total mentions descending
                    brand_order = (
                        consistency_df.groupby("name_normalized")["mentions"]
                        .sum()
                        .sort_values(ascending=True)
                        .index.tolist()
                    )
                    n_brands = len(brand_order)
                    bar_h = max(400, n_brands * 35 + 120)
                    fig_consist = px.bar(
                        consistency_df,
                        y="name_normalized",
                        x="mentions",
                        color="model_label",
                        barmode="group",
                        orientation="h",
                        color_discrete_sequence=[PRIMARY_COLOR, "#D8BFD8"],
                        category_orders={"name_normalized": brand_order},
                        text="mentions",
                    )
                    fig_consist.update_layout(**_transparent_layout(
                        height=bar_h,
                        xaxis=dict(title="Mentions", tickfont=dict(size=12)),
                        yaxis=dict(title="", tickfont=dict(size=13)),
                        legend=dict(title="", font=dict(size=13), orientation="h",
                                    yanchor="bottom", y=1.02, xanchor="center", x=0.5),
                    ))
                    fig_consist.update_traces(textposition="outside", textfont_size=12)
                    st.plotly_chart(fig_consist, use_container_width=True)
                else:
                    st.info("Insufficient data for consistency chart.")

            # ▸ Citation Source Mix (Donut)
            with col_v4:
                st.subheader("Citation Source Mix")
                citmix = calc_citation_mix(filtered)
                citmix_pos = {k: v for k, v in citmix.items() if v > 0}
                if citmix_pos:
                    cit_df = pd.DataFrame({"type": citmix_pos.keys(), "pct": citmix_pos.values()})
                    fig_pie = px.pie(
                        cit_df, values="pct", names="type", hole=0.6,
                        color_discrete_sequence=PURPLE_GRADIENT,
                    )
                    fig_pie.update_layout(**_transparent_layout(height=420))
                    fig_pie.update_traces(textfont_size=14)
                    st.plotly_chart(fig_pie, use_container_width=True)
                else:
                    st.info("No citation mix data.")

            st.markdown("---")

            # ── Memorization Divergence Index ─────────────────
            st.subheader("Memorization Divergence Index")
            st.caption(
                "Measures how much models disagree on brand recommendations for the same query. "
                "High divergence suggests different training data composition (Membership Inference signal)."
            )
            rankings = calc_brand_rankings(filtered)
            brand_by_model = defaultdict(dict)
            for r in rankings:
                brand_by_model[r["brand"]][_model_label(r["model"])] = r["mentions"]
            if len(brand_by_model) > 1:
                df_div = pd.DataFrame(brand_by_model).T.fillna(0)
                model_cols = [c for c in df_div.columns]
                df_div["MDI"] = df_div[model_cols].apply(
                    lambda row: round(row.std() / row.mean() * 100, 1) if row.mean() > 0 else 0.0,
                    axis=1,
                )
                df_div = df_div.sort_values("MDI", ascending=False)

                # Heatmap for MDI
                n_brands = len(df_div)
                mdi_h = max(400, n_brands * 45 + 140)
                mdi_data = df_div[model_cols]
                fig_mdi = px.imshow(
                    mdi_data.values,
                    text_auto=True,
                    x=list(mdi_data.columns),
                    y=list(mdi_data.index),
                    color_continuous_scale=["#FFFFFF", "#4B0082"],
                    labels=dict(x="Model", y="Brand", color="Mentions"),
                    aspect="auto",
                )
                fig_mdi.update_layout(**_transparent_layout(
                    height=mdi_h,
                    xaxis=dict(title="", tickfont=dict(size=14), side="bottom"),
                    yaxis=dict(title="", tickfont=dict(size=13)),
                ))
                fig_mdi.update_traces(textfont=dict(size=15))
                st.plotly_chart(fig_mdi, use_container_width=True)

                # MDI scores table
                st.markdown("**MDI Score** (0 = identical across models, 100+ = high divergence)")
                mdi_display = df_div[["MDI"]].copy()
                mdi_display["Interpretation"] = mdi_display["MDI"].apply(
                    lambda x: "Low divergence (consistent)" if x < 30
                    else "Moderate divergence" if x < 60
                    else "High divergence (possible MIA signal)"
                )
                st.dataframe(mdi_display, use_container_width=True)

            # ── Model Confidence (logprobs) ───────────────────
            raw_records = load_raw_responses(str(RAW_RESPONSES_PATH))
            logprob_records = [r for r in raw_records if r.get("avg_logprob") is not None]
            if logprob_records:
                st.markdown("---")
                st.subheader("Model Confidence (logprobs)")
                st.caption(
                    "Average log-probability per response. Higher values (closer to 0) indicate "
                    "greater model confidence — a potential signal of training data memorization."
                )
                lp_data = [
                    {
                        "query_id": r.get("query_id", ""),
                        "model": _model_label(r.get("model_source", "")),
                        "avg_logprob": r["avg_logprob"],
                    }
                    for r in logprob_records
                ]
                df_lp = pd.DataFrame(lp_data)
                lp_by_model = df_lp.groupby("model")["avg_logprob"].agg(["mean", "min", "max", "count"]).round(4)
                lp_by_model.columns = ["Avg logprob", "Min", "Max", "Responses"]
                lp_by_model = lp_by_model.sort_values("Avg logprob", ascending=False)

                # KPI cards
                lp_cols = st.columns(min(len(lp_by_model), 5))
                for i, (model, row) in enumerate(lp_by_model.iterrows()):
                    if i < len(lp_cols):
                        lp_cols[i].metric(f"{model}", f"{row['Avg logprob']:.4f}",
                                          help=f"Range: {row['Min']:.4f} → {row['Max']:.4f} over {int(row['Responses'])} responses")

                # Bar chart
                fig_lp = px.bar(
                    lp_by_model.reset_index(),
                    x="model", y="Avg logprob",
                    color_discrete_sequence=[PRIMARY_COLOR],
                    error_y=None,
                )
                fig_lp.update_layout(**_transparent_layout(
                    height=320, xaxis_title="", yaxis_title="Avg log-probability",
                ))
                st.plotly_chart(fig_lp, use_container_width=True)

                # Full detail table
                with st.expander("Per-response logprob detail"):
                    st.dataframe(df_lp.sort_values("avg_logprob", ascending=False), use_container_width=True)

            # ── Export ────────────────────────────────────────
            st.markdown("---")
            st.subheader("Export Discovery Data")
            exp_col1, exp_col2 = st.columns(2)
            with exp_col1:
                csv_bytes = pd.DataFrame(filtered).to_csv(index=False).encode("utf-8")
                st.download_button(
                    "⬇ Download filtered records (CSV)",
                    data=csv_bytes,
                    file_name="signalorbit_discovery.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            with exp_col2:
                import json as _json
                json_bytes = _json.dumps(filtered, ensure_ascii=False, indent=2).encode("utf-8")
                st.download_button(
                    "⬇ Download filtered records (JSON)",
                    data=json_bytes,
                    file_name="signalorbit_discovery.json",
                    mime="application/json",
                    use_container_width=True,
                )

            # ── Audit Trail ───────────────────────────────────
            with st.expander("System Integrity Log (Entity Normalization Trace)"):
                audit_cols = ["query_id", "query_family", "model_source", "name_normalized",
                              "recommendation_rank", "sentiment"]
                available = [c for c in audit_cols if c in df_filtered.columns]
                if available:
                    st.dataframe(df_filtered[available].tail(15), use_container_width=True)

    # ═══════════════════════════════════════════════════════════
    #  TAB 2 — INTEGRITY
    # ═══════════════════════════════════════════════════════════
    with tab2:
        st.header("Integrity Scanner")

        if not integrity:
            st.info("No AI Recommendation Poisoning signals detected.")
        else:
            # Summary metrics
            risk_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            for e in integrity:
                rl = e.get("risk_level", "low")
                risk_counts[rl] = risk_counts.get(rl, 0) + 1

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Alerts", len(integrity))
            col2.metric("Critical", risk_counts["critical"])
            col3.metric("High", risk_counts["high"])
            col4.metric("Medium + Low", risk_counts["medium"] + risk_counts["low"])

            avg_risk = sum(e.get("risk_score", 0) for e in integrity) / len(integrity)
            st.metric("Average Risk Score", f"{avg_risk:.0f}/100")

            st.markdown("---")

            # Alerts
            st.subheader("Poisoning Alerts Detected")
            for event in integrity:
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

            st.markdown("---")

            # AI target distribution (Plotly bar)
            i_col1, i_col2 = st.columns(2)
            with i_col1:
                st.subheader("AI Target Domain Distribution")
                domain_counts = defaultdict(int)
                for e in integrity:
                    domain_counts[e.get("ai_target_domain", "unknown")] += 1
                if domain_counts:
                    dc_df = pd.DataFrame({"domain": domain_counts.keys(), "count": domain_counts.values()})
                    fig_dc = px.bar(dc_df, x="domain", y="count",
                                    color_discrete_sequence=[PRIMARY_COLOR])
                    fig_dc.update_layout(**_transparent_layout(
                        xaxis_title="", yaxis_title="Events", height=400,
                    ))
                    st.plotly_chart(fig_dc, use_container_width=True)

            # MITRE ATLAS mapping (Plotly bar)
            with i_col2:
                st.subheader("MITRE ATLAS Mapping")
                mitre_counts = defaultdict(int)
                for e in integrity:
                    for tag in e.get("mitre_atlas_tags", []):
                        mitre_counts[tag] += 1
                mitre_descriptions = {
                    "AML.T0051": "LLM Prompt Injection",
                    "AML.T0080": "AI Agent Memory Poisoning",
                }
                if mitre_counts:
                    mitre_df = pd.DataFrame([
                        {"tag": tag, "label": f"{tag} — {mitre_descriptions.get(tag, tag)}", "count": count}
                        for tag, count in sorted(mitre_counts.items())
                    ])
                    fig_mitre = px.bar(mitre_df, x="label", y="count",
                                       color_discrete_sequence=PURPLE_GRADIENT)
                    fig_mitre.update_layout(**_transparent_layout(
                        xaxis_title="", yaxis_title="Events", height=400,
                    ))
                    st.plotly_chart(fig_mitre, use_container_width=True)

            # ── Export ────────────────────────────────────────
            st.markdown("---")
            st.subheader("Export Integrity Data")
            ie_col1, ie_col2 = st.columns(2)
            with ie_col1:
                import json as _json
                json_bytes = _json.dumps(integrity, ensure_ascii=False, indent=2).encode("utf-8")
                st.download_button(
                    "⬇ Download integrity events (JSON)",
                    data=json_bytes,
                    file_name="signalorbit_integrity.json",
                    mime="application/json",
                    use_container_width=True,
                )
            with ie_col2:
                csv_bytes = pd.DataFrame(integrity).to_csv(index=False).encode("utf-8")
                st.download_button(
                    "⬇ Download integrity events (CSV)",
                    data=csv_bytes,
                    file_name="signalorbit_integrity.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

    # ═══════════════════════════════════════════════════════════
    #  TAB 3 — SEARCH REALITY
    # ═══════════════════════════════════════════════════════════
    with tab3:
        st.header("Search Reality")

        if not gsc:
            st.info("No Search Console data. Import CSV: python -m src.connect_search_console --csv data/mock/gsc_export.csv")
        else:
            total_clicks = sum(r.get("clicks", 0) for r in gsc)
            total_impressions = sum(r.get("impressions", 0) for r in gsc)
            brand_clicks = sum(r.get("clicks", 0) for r in gsc if r.get("brand_class") == "brand")
            nonbrand_clicks = sum(r.get("clicks", 0) for r in gsc if r.get("brand_class") == "nonbrand")

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Clicks", f"{total_clicks:,}")
            col2.metric("Total Impressions", f"{total_impressions:,}")
            col3.metric("Brand Clicks", f"{brand_clicks:,}")
            col4.metric("Non-Brand Clicks", f"{nonbrand_clicks:,}")

            st.markdown("---")

            sr_col1, sr_col2 = st.columns(2)

            # Brand vs Non-Brand (donut)
            with sr_col1:
                st.subheader("Brand vs Non-Brand")
                brand_pct = round(brand_clicks / total_clicks * 100, 1) if total_clicks > 0 else 0
                bn_df = pd.DataFrame({
                    "type": ["Brand", "Non-Brand"],
                    "pct": [brand_pct, round(100 - brand_pct, 1)],
                })
                fig_bn = px.pie(bn_df, values="pct", names="type", hole=0.6,
                                color_discrete_sequence=[PRIMARY_COLOR, NEUTRAL_COLOR])
                fig_bn.update_layout(**_transparent_layout(height=420))
                fig_bn.update_traces(textfont_size=14)
                st.plotly_chart(fig_bn, use_container_width=True)

            # Top queries
            with sr_col2:
                st.subheader("Top Queries by Clicks")
                df_gsc = pd.DataFrame(gsc)
                if "clicks" in df_gsc.columns:
                    df_top = df_gsc.nlargest(10, "clicks")[["query", "clicks", "impressions", "ctr", "position", "brand_class"]]
                    st.dataframe(df_top, use_container_width=True)

            st.markdown("---")

            # GEO-to-SEO Gap
            st.subheader("GEO-to-SEO Gap")
            st.caption(
                "Compares brand visibility in generative AI responses (Share of Model Voice) "
                "vs. real SEO performance. High SoMV + low SEO = GEO opportunity. "
                "Low SoMV + high SEO = erosion risk."
            )

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

                # Radar comparison GEO vs SEO by model
                if somv_avg and len(somv_avg) >= 2:
                    models_labels = [_model_label(m) for m in somv_avg.keys()]
                    geo_vals = list(somv_avg.values()) + [list(somv_avg.values())[0]]
                    theta_vals = models_labels + [models_labels[0]]

                    fig_gap = go.Figure()
                    fig_gap.add_trace(go.Scatterpolar(
                        r=geo_vals, theta=theta_vals, fill="toself",
                        name="GEO (SoMV)", line_color=PRIMARY_COLOR,
                        fillcolor="rgba(138,43,226,0.3)",
                    ))
                    fig_gap.update_layout(
                        polar=dict(
                            radialaxis=dict(visible=True, showticklabels=True, tickfont=dict(size=12)),
                            angularaxis=dict(tickfont=dict(size=14)),
                        ),
                        showlegend=True,
                        height=480,
                        margin=dict(t=60, b=60, l=60, r=60),
                    )
                    st.plotly_chart(fig_gap, use_container_width=True)

            # ── Export ────────────────────────────────────────
            st.markdown("---")
            st.subheader("Export Search Reality Data")
            gsc_col1, gsc_col2 = st.columns(2)
            with gsc_col1:
                csv_bytes = pd.DataFrame(gsc).to_csv(index=False).encode("utf-8")
                st.download_button(
                    "⬇ Download GSC data (CSV)",
                    data=csv_bytes,
                    file_name="signalorbit_gsc.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            with gsc_col2:
                import json as _json
                json_bytes = _json.dumps(gsc, ensure_ascii=False, indent=2).encode("utf-8")
                st.download_button(
                    "⬇ Download GSC data (JSON)",
                    data=json_bytes,
                    file_name="signalorbit_gsc.json",
                    mime="application/json",
                    use_container_width=True,
                )


    # ═══════════════════════════════════════════════════════════
    #  TAB 4 — LIVE EXPLORER
    # ═══════════════════════════════════════════════════════════
    with tab4:
        st.header("Live Query Explorer")
        st.caption(
            "Write any query in natural language and compare how different AI models respond. "
            "Select models from multiple providers and see results side by side."
        )

        # ── Query input ───────────────────────────────────────
        user_query = st.text_area(
            "Your query",
            placeholder=(
                "Example: Organiza un fin de semana en Sevilla para dos personas. "
                "Busca hoteles céntricos que acepten mascotas y tengan parking. "
                "Recomienda restaurantes para comer/cenar y propón una ruta de visitas."
            ),
            height=120,
            key="live_query_input",
        )

        # ── Model selection (grouped by provider) ─────────────
        st.markdown("**Select models to compare:**")
        available = get_available_models()
        selected_live_models: list[str] = []

        provider_cols = st.columns(len(available))
        for i, (provider_group, model_keys) in enumerate(available.items()):
            with provider_cols[i]:
                st.markdown(f"**{provider_group}**")
                for mk in model_keys:
                    if st.checkbox(
                        live_model_label(mk),
                        value=True,
                        key=f"live_model_{mk}",
                    ):
                        selected_live_models.append(mk)

        # ── Parameters ────────────────────────────────────────
        param_col1, param_col2 = st.columns(2)
        with param_col1:
            live_temp = st.slider(
                "Temperature", 0.0, 1.0, 0.2, 0.05,
                key="live_temperature",
                help="Lower = more deterministic, higher = more creative.",
            )
        with param_col2:
            live_max_tokens = st.slider(
                "Max output tokens", 256, 4096, 1024, 128,
                key="live_max_tokens",
                help="Maximum length of each model's response.",
            )

        # ── Execute button ────────────────────────────────────
        run_disabled = not user_query.strip() or not selected_live_models
        if st.button(
            "🚀 Compare Models",
            type="primary",
            disabled=run_disabled,
            use_container_width=True,
        ):
            with st.spinner(f"Querying {len(selected_live_models)} models in parallel…"):
                results = run_live_query(
                    prompt=user_query.strip(),
                    model_keys=selected_live_models,
                    temperature=live_temp,
                    max_output_tokens=live_max_tokens,
                )
            st.session_state["live_results"] = results

        # ── Results display ───────────────────────────────────
        if "live_results" in st.session_state and st.session_state["live_results"]:
            results = st.session_state["live_results"]

            # Summary metrics row
            ok_results = [r for r in results if r["status"] == "ok"]
            err_results = [r for r in results if r["status"] == "error"]

            m1, m2, m3 = st.columns(3)
            m1.metric("Models queried", len(results))
            m2.metric("Successful", len(ok_results))
            avg_lat = (
                round(sum(r["latency_ms"] for r in ok_results) / len(ok_results))
                if ok_results else 0
            )
            m3.metric("Avg latency", f"{avg_lat:,} ms")

            st.markdown("---")

            # Comparison summary table (overview first)
            st.subheader("Comparison Summary")
            summary_data = []
            for r in results:
                summary_data.append({
                    "Model": r["model_label"],
                    "Status": "✅ OK" if r["status"] == "ok" else "❌ Error",
                    "Latency (ms)": r["latency_ms"],
                    "Input Tokens": str(r["input_tokens"]) if r["input_tokens"] is not None else "—",
                    "Output Tokens": str(r["output_tokens"]) if r["output_tokens"] is not None else "—",
                    "Response Length": len(r["text"]),
                })
            st.dataframe(
                pd.DataFrame(summary_data),
                use_container_width=True,
                hide_index=True,
            )

            # Latency chart
            if ok_results:
                st.subheader("Latency Comparison")
                lat_df = pd.DataFrame([
                    {"Model": r["model_label"], "Latency (ms)": r["latency_ms"]}
                    for r in ok_results
                ])
                fig_lat = px.bar(
                    lat_df, x="Model", y="Latency (ms)",
                    color_discrete_sequence=[PRIMARY_COLOR],
                )
                fig_lat.update_layout(**_transparent_layout(
                    height=350, xaxis_title="", yaxis_title="ms",
                ))
                st.plotly_chart(fig_lat, use_container_width=True)

            # Full-width model responses (expanders avoid column overlap)
            st.markdown("---")
            st.subheader("Model Responses")
            for res in results:
                is_ok = res["status"] == "ok"
                icon = "✅" if is_ok else "❌"
                header = f"{icon} {res['model_label']}"
                if is_ok:
                    header += (
                        f"  —  ⏱ {res['latency_ms']:,} ms  ·  "
                        f"📥 {res['input_tokens'] or '?'} in  ·  "
                        f"📤 {res['output_tokens'] or '?'} out"
                    )
                with st.expander(header, expanded=True):
                    if is_ok:
                        st.markdown(res["text"])
                    else:
                        st.error(f"Error: {res['error']}")


if __name__ == "__main__":
    main()
