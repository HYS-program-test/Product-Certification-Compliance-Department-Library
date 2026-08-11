import streamlit as st
import pandas as pd

from pages_impl._shared import render_page_header, render_kpi_row
from pages_impl._data import load_full_table, apply_filters


def render():
    render_page_header("03")

    df_all = load_full_table()
    if df_all.empty:
        st.warning("目前讀不到資料，請確認 Secrets 設定（gcp_service_account）是否正確。")
        return

    categories = ["全部"] + sorted([c for c in df_all["類別"].dropna().unique() if str(c).strip() != ""])
    labs = ["全部"] + sorted([c for c in df_all["實驗室"].dropna().unique() if str(c).strip() != ""])
    grades = ["全部"] + sorted([c for c in df_all["能源效率分級"].dropna().unique() if str(c).strip() != ""])
    badges = ["全部", "標章有效", "標章已到期", "未取得標章"]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        category = st.selectbox("類別", categories, key="p03_cat")
    with c2:
        lab = st.selectbox("實驗室", labs, key="p03_lab")
    with c3:
        grade = st.selectbox("能效分級", grades, key="p03_grade")
    with c4:
        badge = st.selectbox("標章狀態", badges, key="p03_badge")

    df = apply_filters(df_all, category, lab, grade, badge)

    total_rows = len(df)
    valid_models = int(df["室外機型號"].nunique())
    cert_valid = int(df["商品驗證有效"].sum())
    badge_valid = int((df["標章覆蓋狀態"] == "標章有效").sum())
    badge_models = int(df.loc[df["標章覆蓋狀態"] == "標章有效", "室外機型號"].nunique())
    coverage_rate = f"{badge_models / valid_models * 100:.1f}%" if valid_models else "—"
    avg_ratio = df["CSPF實測標示比_num"].dropna()
    avg_ratio_str = f"{avg_ratio.mean() * 100:.1f}%" if len(avg_ratio) else "—"

    render_kpi_row([
        ("資料明細筆數", total_rows),
        ("有效商品型號數", valid_models),
        ("商品驗證有效張數", cert_valid),
        ("節能標章有效張數", badge_valid),
        ("標章有效覆蓋率", coverage_rate),
        ("平均CSPF實測標示比", avg_ratio_str),
    ])

    st.markdown("<br>", unsafe_allow_html=True)
    show_cols = [
        "類別", "室外機型號", "商品驗證證書編號", "商品驗證有效期限", "商品驗證剩餘天數",
        "節能標章證書編號", "節能標章有效日期", "節能標章剩餘天數",
        "能源效率分級", "CSPF_實測", "CSPF_標示", "登錄編號",
    ]
    display_df = df[show_cols].rename(columns={
        "商品驗證證書編號": "商品驗證證書編號_繼承",
        "商品驗證有效期限": "商品驗證有效期限_繼承",
        "商品驗證剩餘天數": "商品驗證剩餘天數",
        "節能標章證書編號": "節能標章證書編號",
        "節能標章有效日期": "節能標章有效日期",
        "節能標章剩餘天數": "節能標章剩餘天數",
        "CSPF_實測": "CSPF_實測",
        "CSPF_標示": "CSPF_標示",
    })
    st.dataframe(display_df, use_container_width=True, hide_index=True, height=560)
