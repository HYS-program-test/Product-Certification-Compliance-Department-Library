import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from pages_impl._shared import render_page_header, render_kpi_row
from pages_impl._data import load_full_table, render_filter_bar

CATEGORY_ORDER = ["MA", "RA", "SA", "VRV"]


def _half_year_bucket(dt):
    if pd.isna(dt):
        return None
    year, month = dt.year, dt.month
    half = "上半" if month <= 6 else "下半"
    return f"{year}{half}"


def render():
    render_page_header("01")

    df_all = load_full_table()
    if df_all.empty:
        st.warning("目前讀不到資料，請確認 Secrets 設定（gcp_service_account）是否正確。")
        return

    df = render_filter_bar(df_all, key_prefix="p01")

    # ── KPI 卡片 ──
    cert_valid = int((df["商品驗證有效"]).sum())
    badge_valid = int((df["標章覆蓋狀態"] == "標章有效").sum())
    due_90 = int(
        ((df["商品驗證風險狀態"] == "90天內") | (df["節能標章風險狀態"] == "90天內")).sum()
    )
    valid_models = int(df["室外機型號"].nunique())
    badge_models = int(df.loc[df["標章覆蓋狀態"] == "標章有效", "室外機型號"].nunique())
    coverage_rate = f"{badge_models / valid_models * 100:.1f}%" if valid_models else "—"

    render_kpi_row([
        ("商品驗證有效張數", cert_valid),
        ("節能標章有效張數", badge_valid),
        ("90天內到期張數", due_90),
        ("有效商品型號數", valid_models),
        ("已取得標章型號數", badge_models),
        ("整體標章取得率", coverage_rate),
    ])

    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown('<div class="block-card-title">1　各類別 商品驗證／節能標章 有效張數</div>', unsafe_allow_html=True)
        g1 = df[df["商品驗證有效"]].groupby("類別").size().reindex(CATEGORY_ORDER, fill_value=0)
        g2 = df[df["標章覆蓋狀態"] == "標章有效"].groupby("類別").size().reindex(CATEGORY_ORDER, fill_value=0)
        fig = go.Figure()
        fig.add_bar(name="商品驗證有效張數", x=CATEGORY_ORDER, y=g1.values, marker_color="#3A7CA5")
        fig.add_bar(name="節能標章有效張數", x=CATEGORY_ORDER, y=g2.values, marker_color="#7FB77E")
        fig.update_layout(barmode="group", height=280, margin=dict(t=10, b=10, l=10, r=10),
                           legend=dict(orientation="h", y=1.15))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown('<div class="block-card-title">2　各類別 標章取得百分比</div>', unsafe_allow_html=True)
        badge_cnt = df[df["標章覆蓋狀態"] == "標章有效"].groupby("類別")["室外機型號"].nunique().reindex(CATEGORY_ORDER, fill_value=0)
        valid_cnt = df.groupby("類別")["室外機型號"].nunique().reindex(CATEGORY_ORDER, fill_value=0)
        fig = go.Figure()
        fig.add_bar(name="已取得標章型號數", x=CATEGORY_ORDER, y=badge_cnt.values, marker_color="#3A7CA5")
        fig.add_bar(name="有效商品型號數", x=CATEGORY_ORDER, y=valid_cnt.values, marker_color="#7FB77E")
        fig.update_layout(barmode="group", height=280, margin=dict(t=10, b=10, l=10, r=10),
                           legend=dict(orientation="h", y=1.15))
        st.plotly_chart(fig, use_container_width=True)

    with col3:
        st.markdown('<div class="block-card-title">3　後續半年到期張數統計</div>', unsafe_allow_html=True)
        today = pd.Timestamp.now().normalize()
        cert_future = df[df["商品驗證有效期限_dt"] >= today].copy()
        badge_future = df[df["節能標章有效日期_dt"] >= today].copy()
        cert_future["區間"] = cert_future["商品驗證有效期限_dt"].apply(_half_year_bucket)
        badge_future["區間"] = badge_future["節能標章有效日期_dt"].apply(_half_year_bucket)
        buckets = sorted(set(cert_future["區間"].dropna()) | set(badge_future["區間"].dropna()))[:6]
        c1 = cert_future.groupby("區間").size().reindex(buckets, fill_value=0)
        c2 = badge_future.groupby("區間").size().reindex(buckets, fill_value=0)
        fig = go.Figure()
        fig.add_bar(name="商品驗證到期張數", x=buckets, y=c1.values, marker_color="#3A7CA5")
        fig.add_bar(name="節能標章到期張數", x=buckets, y=c2.values, marker_color="#7FB77E")
        fig.update_layout(barmode="group", height=280, margin=dict(t=10, b=10, l=10, r=10),
                           legend=dict(orientation="h", y=1.15))
        st.plotly_chart(fig, use_container_width=True)

    col4, col5 = st.columns(2)

    with col4:
        st.markdown('<div class="block-card-title">4　各類別 能效分級數量統計（節能標章）</div>', unsafe_allow_html=True)
        sub = df[df["標章覆蓋狀態"] == "標章有效"]
        pivot = sub.groupby(["類別", "能源效率分級"]).size().unstack(fill_value=0).reindex(CATEGORY_ORDER, fill_value=0)
        fig = go.Figure()
        colors = ["#3A7CA5", "#7FB77E", "#E0A458", "#B3453B"]
        for i, grade in enumerate(sorted(pivot.columns)):
            if str(grade).strip() == "":
                continue
            fig.add_bar(name=f"能源效率分級 {grade}", y=CATEGORY_ORDER, x=pivot[grade].values,
                        orientation="h", marker_color=colors[i % len(colors)])
        fig.update_layout(barmode="stack", height=280, margin=dict(t=10, b=10, l=10, r=10),
                           legend=dict(orientation="h", y=1.15))
        st.plotly_chart(fig, use_container_width=True)

    with col5:
        st.markdown('<div class="block-card-title">5　各類別 CSPF 實測/標示 百分比分布</div>', unsafe_allow_html=True)
        sub = df[df["CSPF風險區間"].notna()]
        pivot = sub.groupby(["類別", "CSPF風險區間"]).size().unstack(fill_value=0).reindex(CATEGORY_ORDER, fill_value=0)
        order = ["<100%", "100-102.9%", "103-105.9%", "≥106%"]
        colors = {"<100%": "#B3453B", "100-102.9%": "#3A7CA5", "103-105.9%": "#7FB77E", "≥106%": "#8B6FB3"}
        fig = go.Figure()
        for bucket in order:
            if bucket not in pivot.columns:
                continue
            fig.add_bar(name=bucket, y=CATEGORY_ORDER, x=pivot[bucket].values,
                        orientation="h", marker_color=colors[bucket])
        fig.update_layout(barmode="stack", height=280, margin=dict(t=10, b=10, l=10, r=10),
                           legend=dict(orientation="h", y=1.15))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown('<div class="block-card-title">6　90天內即將到期清單</div>', unsafe_allow_html=True)
    due = df[(df["商品驗證風險狀態"] == "90天內") | (df["節能標章風險狀態"] == "90天內")].copy()
    rows = []
    for _, r in due.iterrows():
        if r["商品驗證風險狀態"] == "90天內":
            rows.append({
                "證書類型": "商品驗證", "證書編號": r["商品驗證證書編號"], "類別": r["類別"],
                "型號": r["室外機型號"], "有效日期": r["商品驗證有效期限"],
                "剩餘天數": int(r["商品驗證剩餘天數"]) if pd.notna(r["商品驗證剩餘天數"]) else None,
            })
        if r["節能標章風險狀態"] == "90天內":
            rows.append({
                "證書類型": "節能標章", "證書編號": r["節能標章證書編號"], "類別": r["類別"],
                "型號": r["室外機型號"], "有效日期": r["節能標章有效日期"],
                "剩餘天數": int(r["節能標章剩餘天數"]) if pd.notna(r["節能標章剩餘天數"]) else None,
            })
    due_df = pd.DataFrame(rows).sort_values("剩餘天數") if rows else pd.DataFrame(
        columns=["證書類型", "證書編號", "類別", "型號", "有效日期", "剩餘天數"])
    st.dataframe(due_df, use_container_width=True, hide_index=True)
