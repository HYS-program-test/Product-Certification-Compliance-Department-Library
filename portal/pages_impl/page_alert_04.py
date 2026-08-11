import streamlit as st
import pandas as pd

from pages_impl._shared import render_page_header, render_kpi_row
from pages_impl._data import load_full_table, render_filter_bar


def render():
    render_page_header("04")

    df_all = load_full_table()
    if df_all.empty:
        st.warning("目前讀不到資料，請確認 Secrets 設定（gcp_service_account）是否正確。")
        return

    df = render_filter_bar(df_all, key_prefix="p04")

    cert_due90 = int((df["商品驗證風險狀態"] == "90天內").sum())
    badge_due90 = int((df["節能標章風險狀態"] == "90天內").sum())
    cert_expired = int((df["商品驗證風險狀態"] == "已到期").sum())
    badge_expired = int((df["節能標章風險狀態"] == "已到期").sum())
    badge_gap = int((df["標章覆蓋狀態"] != "標章有效").sum())
    quality_issue = int(df["資料品質異常"].sum())

    render_kpi_row([
        ("商品驗證90天內", cert_due90),
        ("節能標章90天內", badge_due90),
        ("商品驗證已到期", cert_expired),
        ("節能標章已到期", badge_expired),
        ("標章缺口型號數", badge_gap),
        ("資料品質異常筆數", quality_issue),
    ])

    st.markdown('<div style="height:.2rem"></div>', unsafe_allow_html=True)
    col_a, col_b = st.columns(2)

    with col_a, st.container(key="chart_card_04_a"):
        st.markdown('<div class="block-card-title">A　90天內即將到期</div>', unsafe_allow_html=True)
        rows = []
        due = df[(df["商品驗證風險狀態"] == "90天內") | (df["節能標章風險狀態"] == "90天內")]
        for _, r in due.iterrows():
            if r["商品驗證風險狀態"] == "90天內":
                rows.append({"證書類型": "商品驗證", "證書編號": r["商品驗證證書編號"], "類別": r["類別"],
                             "型號": r["室外機型號"], "有效日期": r["商品驗證有效期限"],
                             "剩餘天數": int(r["商品驗證剩餘天數"])})
            if r["節能標章風險狀態"] == "90天內":
                rows.append({"證書類型": "節能標章", "證書編號": r["節能標章證書編號"], "類別": r["類別"],
                             "型號": r["室外機型號"], "有效日期": r["節能標章有效日期"],
                             "剩餘天數": int(r["節能標章剩餘天數"])})
        due_df = pd.DataFrame(rows).sort_values("剩餘天數") if rows else pd.DataFrame(
            columns=["證書類型", "證書編號", "類別", "型號", "有效日期", "剩餘天數"])
        st.dataframe(due_df, use_container_width=True, hide_index=True, height=160)

    with col_b, st.container(key="chart_card_04_b"):
        st.markdown('<div class="block-card-title">B　標章覆蓋缺口</div>', unsafe_allow_html=True)
        gap = df[df["標章覆蓋狀態"] != "標章有效"][
            ["類別", "室外機型號", "標章覆蓋狀態", "商品驗證有效期限", "節能標章有效日期"]]
        st.dataframe(gap, use_container_width=True, hide_index=True, height=160)

    col_c, col_d = st.columns(2)
    with col_c, st.container(key="chart_card_04_c"):
        st.markdown('<div class="block-card-title">C　CSPF 低於標示值</div>', unsafe_allow_html=True)
        low = df[df["CSPF低於標示"]].copy()
        low["CSPF實測標示比"] = (low["CSPF實測標示比_num"] * 100).round(1).astype(str) + "%"
        st.dataframe(
            low[["類別", "室外機型號", "CSPF_實測", "CSPF_標示", "CSPF實測標示比", "能源效率分級"]],
            use_container_width=True, hide_index=True, height=260,
        )

    with col_d, st.container(key="chart_card_04_d"):
        st.markdown('<div class="block-card-title">D　資料品質異常</div>', unsafe_allow_html=True)
        bad = df[df["資料品質異常"]][["類別", "室外機型號", "登錄編號", "能源效率分級", "資料品質異常原因"]]
        st.dataframe(bad, use_container_width=True, hide_index=True, height=160)

    st.info("這一頁目前是照 PBI 邏輯獨立算出來的版本。跟 08（生命週期審核）到期清單串接、把 A 區塊換成 08 那套帶展延決策互動功能的版本，還沒做，是下一步。")
