import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from pages_impl._shared import render_page_header, render_kpi_row
from pages_impl._data import load_full_table, render_filter_bar

CATEGORY_ORDER = ["MA", "RA", "SA", "VRV"]

# 色彩配置：清楚飽和、避免同張圖撞色系
COLOR_CORAL = "#E8735C"
COLOR_AMBER = "#E9A23B"
COLOR_BLUE = "#3B82C4"
COLOR_TEAL = "#2A9D8F"
COLOR_PURPLE = "#7C6BA8"
COLOR_DEEPTEAL = "#1B6B65"

# 區塊 A：證書有效期限（商品驗證，不含已到期）
RISK_ORDER_A = ["90天內", "91-180天", "181-365天", "366天以上"]
RISK_COLORS_A = {"90天內": COLOR_CORAL, "91-180天": COLOR_AMBER, "181-365天": COLOR_BLUE, "366天以上": COLOR_TEAL}

# 區塊 B：節能標章覆蓋缺口（不列「未取得標章」）
BADGE_ORDER_B = ["標章快到期", "標章有效"]
BADGE_COLORS_B = {"標章快到期": COLOR_AMBER, "標章有效": COLOR_TEAL}

# 區塊 C：CSPF 實測/標示
CSPF_ORDER = ["<100%", "100-102.9%", "103-105.9%", "≥106%"]
CSPF_COLORS = {"<100%": COLOR_CORAL, "100-102.9%": COLOR_BLUE, "103-105.9%": COLOR_TEAL, "≥106%": COLOR_PURPLE}

MARGIN = dict(t=6, b=6, l=6, r=6)
BLOCK_H = 145  # 同 01 頁六格塞一屏的壓縮高度


def _cert_bucket_a(days):
    if pd.isna(days) or days < 0:
        return None
    if days <= 90:
        return "90天內"
    if days <= 180:
        return "91-180天"
    if days <= 365:
        return "181-365天"
    return "366天以上"


def _badge_bucket_b(has_badge, days):
    """未取得標章的列直接回傳 None，不列入這個圖表統計"""
    if not has_badge or pd.isna(days) or days < 0:
        return None
    if days <= 90:
        return "標章快到期"
    return "標章有效"


def _stacked_bar_card(df, value_col, order, colors, height=BLOCK_H):
    sub = df[df[value_col].notna()]
    pivot = sub.groupby(["類別", value_col]).size().unstack(fill_value=0).reindex(CATEGORY_ORDER, fill_value=0)
    fig = go.Figure()
    for bucket in order:
        if bucket not in pivot.columns:
            continue
        fig.add_bar(name=bucket, y=CATEGORY_ORDER, x=pivot[bucket].values,
                    orientation="h", marker_color=colors[bucket])
    fig.update_layout(barmode="stack", height=height, margin=MARGIN,
                       legend=dict(orientation="h", y=1.22, x=0, font=dict(size=9)),
                       plot_bgcolor="white", paper_bgcolor="white")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _half_year_bucket(dt):
    if pd.isna(dt):
        return None
    year, month = dt.year, dt.month
    half = "上半" if month <= 6 else "下半"
    return f"{year}{half}"


def render():
    render_page_header("02")

    df_all = load_full_table()
    if df_all.empty:
        st.warning("目前讀不到資料，請確認 Secrets 設定（gcp_service_account）是否正確。")
        return

    df = render_filter_bar(df_all, key_prefix="p02")

    cert_due180 = int((df["商品驗證風險狀態"].isin(["90天內", "91-180天"])).sum())
    badge_due180 = int((df["節能標章風險狀態"].isin(["90天內", "91-180天"])).sum())
    no_badge = int((~df["有節能標章"]).sum())
    cspf_low = int(df["CSPF低於標示"].sum())

    render_kpi_row([
        ("商品驗證180天內", cert_due180),
        ("節能標章180天內", badge_due180),
        ("未取得標章", no_badge),
        ("CSPF低於標示型號數", cspf_low),
    ])

    st.markdown('<div style="height:.2rem"></div>', unsafe_allow_html=True)

    df = df.copy()
    df["_A風險分級"] = df["商品驗證剩餘天數"].apply(_cert_bucket_a)
    df["_B標章分級"] = [
        _badge_bucket_b(h, d) for h, d in zip(df["有節能標章"], df["節能標章剩餘天數"])
    ]

    col1, col2, col3 = st.columns(3)
    with col1, st.container(key="chart_card_02_a"):
        st.markdown('<div class="block-card-title">A　證書有效期限</div>', unsafe_allow_html=True)
        _stacked_bar_card(df, "_A風險分級", RISK_ORDER_A, RISK_COLORS_A)
    with col2, st.container(key="chart_card_02_b"):
        st.markdown('<div class="block-card-title">B　節能標章覆蓋缺口</div>', unsafe_allow_html=True)
        _stacked_bar_card(df, "_B標章分級", BADGE_ORDER_B, BADGE_COLORS_B)
    with col3, st.container(key="chart_card_02_c"):
        st.markdown('<div class="block-card-title">C　CSPF 實測/標示</div>', unsafe_allow_html=True)
        _stacked_bar_card(df, "CSPF風險區間", CSPF_ORDER, CSPF_COLORS)

    col4, col5, col6 = st.columns(3)

    with col4, st.container(key="chart_card_02_d"):
        st.markdown('<div class="block-card-title">D　資料品質異常明細</div>', unsafe_allow_html=True)
        bad = df[df["資料品質異常"]][["類別", "室外機型號", "登錄編號", "能源效率分級", "資料品質異常原因"]]
        st.dataframe(bad, use_container_width=True, hide_index=True, height=BLOCK_H)

    with col5, st.container(key="chart_card_02_e"):
        st.markdown('<div class="block-card-title">E　各類別能效分級數量</div>', unsafe_allow_html=True)
        sub = df[df["能源效率分級"].astype(str).str.strip() != ""]
        pivot = sub.groupby(["類別", "能源效率分級"]).size().unstack(fill_value=0).reindex(CATEGORY_ORDER, fill_value=0)
        fig = go.Figure()
        grade_colors = {"1": COLOR_DEEPTEAL, "2": COLOR_AMBER, "3": COLOR_PURPLE}
        for grade in sorted(pivot.columns):
            if str(grade).strip() == "":
                continue
            vals = pivot[grade].values
            fig.add_bar(name=f"{grade}級", x=CATEGORY_ORDER, y=vals,
                        marker_color=grade_colors.get(str(grade), COLOR_BLUE),
                        text=vals, textposition="outside")
        fig.update_layout(barmode="group", height=BLOCK_H, margin=dict(t=20, b=6, l=6, r=6),
                           legend=dict(orientation="h", y=1.2, x=0, font=dict(size=9)),
                           plot_bgcolor="white", paper_bgcolor="white",
                           yaxis=dict(showgrid=True, gridcolor="#F1F5F9"))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with col6, st.container(key="chart_card_02_f"):
        st.markdown('<div class="block-card-title">F　後續到期張數</div>', unsafe_allow_html=True)
        today = pd.Timestamp.now().normalize()
        cert_future = df[(df["商品驗證有效"]) & (df["商品驗證有效期限_dt"] >= today)].copy()
        badge_future = df[(df["有節能標章"]) & (df["節能標章有效日期_dt"] >= today)].copy()
        cert_future["區間"] = cert_future["商品驗證有效期限_dt"].apply(_half_year_bucket)
        badge_future["區間"] = badge_future["節能標章有效日期_dt"].apply(_half_year_bucket)
        buckets = sorted(set(cert_future["區間"].dropna()) | set(badge_future["區間"].dropna()))[:6]
        c1 = cert_future.groupby("區間").size().reindex(buckets, fill_value=0)
        c2 = badge_future.groupby("區間").size().reindex(buckets, fill_value=0)
        fig = go.Figure()
        fig.add_bar(name="商品驗證", x=buckets, y=c1.values, marker_color=COLOR_BLUE)
        fig.add_bar(name="節能標章", x=buckets, y=c2.values, marker_color=COLOR_DEEPTEAL)
        fig.update_layout(barmode="group", height=BLOCK_H, margin=MARGIN,
                           legend=dict(orientation="h", y=1.2, x=0, font=dict(size=9)),
                           plot_bgcolor="white", paper_bgcolor="white",
                           yaxis=dict(showgrid=True, gridcolor="#F1F5F9"))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
