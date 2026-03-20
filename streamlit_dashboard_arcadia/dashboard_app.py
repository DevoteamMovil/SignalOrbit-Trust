import os
import json
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# --- 1. GLOBAL SYSTEM CONFIGURATION ---
st.set_page_config(
    page_title="GEO Observability Layer",
    layout="wide",
    initial_sidebar_state="expanded"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARSED_INPUT = os.path.join(BASE_DIR, "data", "parsed", "parsed_records.jsonl")
SEO_INPUT = os.path.join(BASE_DIR, "data", "final", "gsc_metrics.csv")
NORMALIZED_OUTPUT = os.path.join(BASE_DIR, "data", "final", "normalized_records.csv")
SNAPSHOT_OUTPUT = os.path.join(BASE_DIR, "data", "final", "demo_snapshot.json")

PRIMARY_COLOR = "#8A2BE2"
NEUTRAL_COLOR = "#F0F0F0"
TEXT_COLOR = "#1E1E1E"

MODEL_DISPLAY_MAP = {
    "google_gemini_2_5_pro": "Gemini 2.5 Pro",
    "openai_gpt_4_1": "GPT-4.1",
    "anthropic_claude_sonnet_4_5": "Claude 3.5 Sonnet",
    "xai_grok_3": "Grok 3"
}

# --- 2. DATA PROCESSING LAYER ---
def execute_normalization_pipeline(df: pd.DataFrame) -> pd.DataFrame:
    """Standardizes brand entities and filters out non-business entities."""
    aliases_path = os.path.join(BASE_DIR, "data", "brand_aliases.csv")
    
    if os.path.exists(aliases_path):
        df_aliases = pd.read_csv(aliases_path)
        df_aliases['name_raw_lower'] = df_aliases['name_raw'].str.lower().str.strip()
        name_map = dict(zip(df_aliases['name_raw_lower'], df_aliases['name_normalized']))
        category_map = dict(zip(df_aliases['name_normalized'], df_aliases['category']))
    else:
        name_map = {}
        category_map = {}

    df['name_standardized'] = df['name_raw'].str.lower().str.strip()
    df['name_normalized'] = df['name_standardized'].map(name_map).fillna(df['name_raw'].str.title())
    df['brand_category'] = df['name_normalized'].map(category_map).fillna('unknown')
    
    # Exclude non-business entities
    df = df[~df['brand_category'].isin(['destination', 'IGNORE'])]

    df['recommendation_rank'] = pd.to_numeric(df['recommendation_rank'], errors='coerce')
    
    df_export = df.drop(columns=['name_standardized', 'brand_category'], errors='ignore')
    os.makedirs(os.path.dirname(NORMALIZED_OUTPUT), exist_ok=True)
    df_export.to_csv(NORMALIZED_OUTPUT, index=False)
    
    return df_export

def generate_demo_snapshot(df_geo: pd.DataFrame, df_seo: pd.DataFrame, total_runs: int) -> str:
    """Exports a unified JSON state for offline demo reliability."""
    snapshot_payload = {
        "metadata": {
            "version": "1.0",
            "timestamp_utc": pd.Timestamp.utcnow().isoformat(),
            "status": "Production Final",
            "total_raw_runs": total_runs
        },
        "geo_data": df_geo.to_dict(orient="records"),
        "seo_data": df_seo.to_dict(orient="records")
    }
    
    os.makedirs(os.path.dirname(SNAPSHOT_OUTPUT), exist_ok=True)
    with open(SNAPSHOT_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(snapshot_payload, f, indent=4, ensure_ascii=False)
    
    return SNAPSHOT_OUTPUT

# --- 3. DATA INGESTION ENGINE ---
@st.cache_data(ttl=60)
def load_operational_datasets() -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Loads JSONL inputs, calculates true run count, flattens arrays, and merges SEO baseline."""
    if not os.path.exists(PARSED_INPUT):
        return pd.DataFrame(), pd.DataFrame(), 0

    records = []
    with open(PARSED_INPUT, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    
    unique_run_ids = set([r.get('run_id') for r in records if r.get('run_id')])
    total_runs = len(unique_run_ids)
    
    if records:
        df_geo = pd.json_normalize(
            records, 
            record_path=['brands_extracted'], 
            meta=['run_id', 'model_source', 'timestamp_utc', 'query_family'],
            errors='ignore'
        )
    else:
        df_geo = pd.DataFrame()

    if not df_geo.empty:
        df_geo = execute_normalization_pipeline(df_geo)
        if not df_geo.empty:
            df_geo['model_label'] = df_geo['model_source'].map(MODEL_DISPLAY_MAP).fillna(df_geo['model_source'])
        
    df_seo = pd.read_csv(SEO_INPUT) if os.path.exists(SEO_INPUT) else pd.DataFrame()
    
    return df_geo, df_seo, total_runs

# --- 4. ANALYTICAL INTERFACE ---
def main():
    st.title("GEO Observability Layer")
    st.caption("B2B Generative Search Visibility Auditing Platform")
    
    # --- FAILSAFE TOGGLE ---
    use_panic_mode = st.sidebar.toggle("Load Offline Snapshot", value=False)
    
    if use_panic_mode:
        if os.path.exists(SNAPSHOT_OUTPUT):
            with open(SNAPSHOT_OUTPUT, "r", encoding="utf-8") as f:
                snap_data = json.load(f)
            df_geo = pd.DataFrame(snap_data["geo_data"])
            df_seo = pd.DataFrame(snap_data["seo_data"])
            total_runs = snap_data["metadata"].get("total_raw_runs", df_geo['run_id'].nunique() if not df_geo.empty else 0)
            st.sidebar.warning("Running on Offline Snapshot. Live data ignored.")
        else:
            st.sidebar.error("Snapshot not found. Generate one first.")
            return
    else:
        df_geo, df_seo, total_runs = load_operational_datasets()
    
    if df_geo.empty or total_runs == 0:
        st.info("System Ready. Awaiting data input in /data/parsed/...")
        return

# --- UI CONTROLS ---
    st.sidebar.markdown("### System Controls")
    
    brand_options = sorted(df_geo['name_normalized'].dropna().unique().tolist())
    
    default_brand_index = 0
    if "Booking" in brand_options:
        default_brand_index = brand_options.index("Booking")
        
    target_brand = st.sidebar.selectbox("Brand Scope Selection", brand_options, index=default_brand_index)
    
    query_families = ["All"] + sorted(df_geo['query_family'].dropna().unique().tolist())
    target_family = st.sidebar.selectbox("Query Family Filter", query_families)
    
    model_options = ["All Models"] + sorted(df_geo['model_label'].dropna().unique().tolist())
    target_model = st.sidebar.selectbox("Model Filter", model_options)
    
    if not use_panic_mode and st.sidebar.button("Export Demo Snapshot"):
        generate_demo_snapshot(df_geo, df_seo, total_runs)
        st.sidebar.success("Snapshot verified and saved.")

    # --- DATA FILTERING ---
    filtered_df = df_geo.copy()
    if target_family != "All":
        filtered_df = filtered_df[filtered_df['query_family'] == target_family]
    if target_model != "All Models":
        filtered_df = filtered_df[filtered_df['model_label'] == target_model]

    brand_focus_df = filtered_df[filtered_df['name_normalized'] == target_brand]
    
    # Adjust denominator based on active filters
    if target_family == "All" and target_model == "All Models":
        active_total_runs = total_runs
    else:
        active_total_runs = filtered_df['run_id'].nunique()

    # --- KPI CALCULATIONS ---
    brand_runs = brand_focus_df['run_id'].nunique()
    sov = (brand_runs / active_total_runs) * 100 if active_total_runs > 0 else 0
    
    win_runs = brand_focus_df[brand_focus_df['recommendation_rank'] == 1]['run_id'].nunique()
    win_rate = (win_runs / brand_runs * 100) if brand_runs > 0 else 0
    
    seo_metrics = df_seo[df_seo['marca'] == target_brand]
    seo_baseline = seo_metrics['seo_share_of_clicks'].sum() if not seo_metrics.empty else 0
    performance_delta = sov - seo_baseline

    k_col1, k_col2, k_col3 = st.columns(3)
    k_col1.metric("Share of Model Voice", f"{sov:.1f}%", help="Percentage of responses containing the brand.")
    k_col2.metric("Recommendation Win Rate", f"{win_rate:.1f}%", help="Percentage of appearances where brand is Rank 1.")
    k_col3.metric("GEO-to-SEO Delta", f"{performance_delta:.1f} pts", delta=f"{performance_delta:.1f} vs GSC Baseline")

    st.markdown("---")

    if filtered_df.empty:
        st.warning("No data available for the selected filters.")
        return

    col_v1, col_v2 = st.columns(2)
    
    with col_v1:
        st.subheader("Model Visibility Distribution")
        visibility_df = filtered_df.groupby(['model_label', 'name_normalized'])['run_id'].nunique().reset_index(name='unique_runs')
        
        color_scheme = {target_brand: PRIMARY_COLOR}
        for brand in brand_options:
            if brand != target_brand: color_scheme[brand] = NEUTRAL_COLOR
            
        fig_bar = px.bar(
            visibility_df, x="model_label", y="unique_runs", color="name_normalized", 
            color_discrete_map=color_scheme, barmode='relative'
        )
        fig_bar.update_layout(xaxis_title="", yaxis_title="Unique Run Mentions", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_bar, use_container_width=True)

    with col_v2:
        st.subheader("Statistical Sentiment Profile")
        if not brand_focus_df.empty:
            sentiment_weights = {"positive": 1.0, "neutral": 0.5, "negative": 0.1, "mixed": 0.5}
            brand_focus_df_copy = brand_focus_df.copy()
            brand_focus_df_copy['s_score'] = brand_focus_df_copy['sentiment'].map(sentiment_weights).fillna(0.5)
            radar_stats = brand_focus_df_copy.groupby('model_label')['s_score'].mean().reset_index()
            
            if not radar_stats.empty:
                r_axis = radar_stats['s_score'].tolist() + [radar_stats['s_score'].iloc[0]]
                theta_axis = radar_stats['model_label'].tolist() + [radar_stats['model_label'].iloc[0]]

                fig_radar = go.Figure(data=go.Scatterpolar(r=r_axis, theta=theta_axis, fill='toself', line_color=PRIMARY_COLOR, fillcolor='rgba(138, 43, 226, 0.4)'))
                fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 1], showticklabels=False)), showlegend=False, margin=dict(t=40, b=40))
                st.plotly_chart(fig_radar, use_container_width=True)
            else:
                st.info("Insufficient sentiment data.")
        else:
             st.info("No sentiment data available for the current selection.")

    st.markdown("<br>", unsafe_allow_html=True)
    col_v3, col_v4 = st.columns(2)

    with col_v3:
        st.subheader("Cross-Model Consistency")
        consistency_matrix = filtered_df.groupby(['model_label', 'name_normalized'])['run_id'].nunique().unstack(fill_value=0)
        if not consistency_matrix.empty:
            fig_heat = px.imshow(consistency_matrix, text_auto=True, color_continuous_scale=["#FFFFFF", PRIMARY_COLOR])
            fig_heat.update_layout(plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_heat, use_container_width=True)
        else:
            st.info("Insufficient data for consistency matrix.")

    with col_v4:
        st.subheader("Citation Source Mix")
        if not brand_focus_df.empty:
            citations = brand_focus_df['citation_type'].value_counts().reset_index()
            fig_pie = px.pie(citations, values='count', names='citation_type', hole=0.6, color_discrete_sequence=["#4B0082", "#8A2BE2", "#D8BFD8", "#E6E6FA"])
            fig_pie.update_layout(plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("No citation data available.")

    with st.expander("System Integrity Log (Entity Normalization Trace)"):
        audit_view = filtered_df[['run_id', 'query_family', 'model_source', 'name_raw', 'name_normalized', 'sentiment']].tail(15)
        st.dataframe(audit_view, use_container_width=True)

if __name__ == "__main__":
    main()