import streamlit as st
import plotly.graph_objects as go

from pages_impl._shared import render_page_header, render_kpi_row
from pages_impl._data import load_full_table, render_filter_bar

CATEGORY_ORDER = ["MA", "RA", "SA", "VRV"]
RISK_ORDER = ["已到期", "90天內", "91-180天", "180天以上"]
RISK_COLORS = {"已到期": "#C0504D", "90天內": "#ED9E4B", "91-180天": "#4472C4", "180天以上": "#82BE7E"}
BADGE_ORDER = ["未取得標章", "標章已到期", "標章有效"]
BADGE_COLORS = {"未取得標章": "#C0504D", "標章已到期": "#ED9E4B", "標章有效": "#82BE7E"}
CSPF_ORDER = ["<100%", "100-102.9%", "103-105.9%", "≥106%"]
CSPF_COLORS = {"<100%": "#C0504D", "100-102.9%": "#4472C4", "103-105.9%": "#82BE7E", "≥106%": "#8064A2"}
MARGIN = dict(t=10, b=10, l=10, r=10)


def _stacked_bar_card(df, key, title, value_col, order, colors, height=260):
    with st.container(key=key):
        st.markdown(f'<div class="block-card-title">{title}</div>', unsafe_allow_html=True)
        sub = df[df[value_col].notna()]
        pivot = sub.groupby(["類別", value_col]).size().unstack(fill_value=0).reindex(CATEGORY_ORDER, fill_value=0)
        fig = go.Figure()
        for bucket in order:
            if bucket not in pivot.columns:
                continue
            fig.add_bar(name=bucket, y=CATEGORY_ORDER, x=pivot[bucket].values,
                        orientation="h", marker_color=colors[bucket])
        fig.update_layout(barmode="stack", height=height, margin=MARGIN,
                           legend=dict(orientation="h", y=1.18, x=0, font=dict(size=11)),
                           plot_bgcolor="white", paper_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render():
    render_page_header("02")

    df_all = load_full_table()
    if df_all.empty:
        st.warning("目前讀不到資料，請確認 Secrets 設定（gcp_service_account）是否正確。")
        return

    df = render_filter_bar(df_all, key_prefix="p02")

    cert_expired = int((df["商品驗證風險狀態"] == "已到期").sum())
    cert_due180 = int((df["商品驗證風險狀態"].isin(["90天內", "91-180天"])).sum())
    badge_expired = int((df["節能標章風險狀態"] == "已到期").sum())
    badge_due180 = int((df["節能標章風險狀態"].isin(["90天內", "91-180天"])).sum())
    valid_models = int(df["室外機型號"].nunique())
    badge_models = int(df.loc[df["標章覆蓋狀態"] == "標章有效", "室外機型號"].nunique())
    coverage_rate = f"{badge_models / valid_models * 100:.1f}%" if valid_models else "—"
    cspf_low = int(df["CSPF低於標示"].sum())

    render_kpi_row([
        ("商品驗證已到期", cert_expired),
        ("商品驗證180天內", cert_due180),
        ("節能標章已到期", badge_expired),
        ("節能標章180天內", badge_due180),
        ("標章有效覆蓋率", coverage_rate),
        ("CSPF低於標示型號數", cspf_low),
    ])

    st.markdown("<br>", unsafe_allow_html=True)
    col_a, col_b = st.columns(2)
    with col_a:
        _stacked_bar_card(df, "chart_card_02_a", "A　證書到期風險分層（商品驗證）", "商品驗證風險狀態", RISK_ORDER, RISK_COLORS)
    with col_b:
        _stacked_bar_card(df, "chart_card_02_b", "B　節能標章覆蓋缺口", "標章覆蓋狀態", BADGE_ORDER, BADGE_COLORS)

    col_c, col_d = st.columns(2)
    with col_c:
        _stacked_bar_card(df, "chart_card_02_c", "C　CSPF 實測風險", "CSPF風險區間", CSPF_ORDER, CSPF_COLORS)
    with col_d, st.container(key="chart_card_02_d"):
        st.markdown('<div class="block-card-title">D　資料品質異常明細</div>', unsafe_allow_html=True)
        bad = df[df["資料品質異常"]][["類別", "室外機型號", "登錄編號", "能源效率分級", "資料品質異常原因"]]
        st.dataframe(bad, use_container_width=True, hide_index=True, height=260)
