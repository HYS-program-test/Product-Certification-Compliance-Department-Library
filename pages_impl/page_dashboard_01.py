import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from pages_impl._shared import render_page_header, render_kpi_row
from pages_impl._data import load_full_table, render_filter_bar

CATEGORY_ORDER = ["MA", "RA", "SA", "VRV"]

LEGEND_TOP = dict(orientation="h", y=1.22, x=0, font=dict(size=9))
MARGIN = dict(t=6, b=6, l=6, r=6)


def render():
    render_page_header("01")

    df_all = load_full_table()
    if df_all.empty:
        st.warning("目前讀不到資料，請確認 Secrets 設定（gcp_service_account）是否正確。")
        return

    df = render_filter_bar(df_all, key_prefix="p01")

    # ── 去重後的證書表：一張證書（同一個證書編號）只算一次，符合「張數」的字面意義 ──
    df_cert_unique = df[df["商品驗證有效"]].drop_duplicates("商品驗證證書編號")
    df_badge_unique = df[df["標章覆蓋狀態"] == "標章有效"].drop_duplicates("節能標章證書編號")

    cert_valid = len(df_cert_unique)
    badge_valid = len(df_badge_unique)
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

    st.markdown('<div style="height:.2rem"></div>', unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)

    # ── 區塊 1：各類別 商品驗證／節能標章 有效張數（去重後）──
    with col1, st.container(key="chart_card_01_1"):
        st.markdown('<div class="block-card-title">1　各類別 商品驗證／節能標章 有效張數</div>', unsafe_allow_html=True)
        g1 = df_cert_unique.groupby("類別").size().reindex(CATEGORY_ORDER, fill_value=0)
        g2 = df_badge_unique.groupby("類別").size().reindex(CATEGORY_ORDER, fill_value=0)
        fig = go.Figure()
        fig.add_bar(name="商品驗證有效張數", x=CATEGORY_ORDER, y=g1.values, marker_color="#4472C4")
        fig.add_bar(name="節能標章有效張數", x=CATEGORY_ORDER, y=g2.values, marker_color="#82BE7E")
        fig.update_layout(barmode="group", height=188, margin=MARGIN, legend=LEGEND_TOP,
                           plot_bgcolor="white", paper_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ── 區塊 2：節能標章有效張數（原能效分級數量統計，去重後依能效分級分層）──
    with col2, st.container(key="chart_card_01_2"):
        st.markdown('<div class="block-card-title">2　節能標章有效張數</div>', unsafe_allow_html=True)
        pivot = df_badge_unique.groupby(["類別", "能源效率分級"]).size().unstack(fill_value=0).reindex(CATEGORY_ORDER, fill_value=0)
        fig = go.Figure()
        colors = {"1": "#4472C4", "2": "#82BE7E", "3": "#ED9E4B"}
        for grade in sorted(pivot.columns):
            if str(grade).strip() == "":
                continue
            fig.add_bar(name=f"能效分級 {grade}", y=CATEGORY_ORDER, x=pivot[grade].values,
                        orientation="h", marker_color=colors.get(str(grade), "#4472C4"))
        fig.update_layout(barmode="stack", height=188, margin=MARGIN, legend=LEGEND_TOP,
                           plot_bgcolor="white", paper_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ── 區塊 3：各類別 標章取得百分比（型號覆蓋率，不去重，維持原邏輯）──
    with col3, st.container(key="chart_card_01_3"):
        st.markdown('<div class="block-card-title">3　各類別 標章取得百分比</div>', unsafe_allow_html=True)
        badge_cnt = df[df["標章覆蓋狀態"] == "標章有效"].groupby("類別")["室外機型號"].nunique().reindex(CATEGORY_ORDER, fill_value=0)
        valid_cnt = df.groupby("類別")["室外機型號"].nunique().reindex(CATEGORY_ORDER, fill_value=0)
        fig = go.Figure()
        fig.add_bar(name="已取得標章型號數", x=CATEGORY_ORDER, y=badge_cnt.values, marker_color="#4472C4")
        fig.add_bar(name="有效商品型號數", x=CATEGORY_ORDER, y=valid_cnt.values, marker_color="#82BE7E")
        fig.update_layout(barmode="group", height=188, margin=MARGIN, legend=LEGEND_TOP,
                           plot_bgcolor="white", paper_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    col4, col5, col6 = st.columns(3)

    # ── 區塊 4：90天內到期的商品驗證登錄證書清單（只列商品驗證，去重）──
    with col4, st.container(key="chart_card_01_4"):
        st.markdown('<div class="block-card-title">4　90天內到期的商品驗證登錄證書清單</div>', unsafe_allow_html=True)
        cert_due = df[df["商品驗證風險狀態"] == "90天內"].copy()
        cert_due = cert_due.drop_duplicates(subset=["商品驗證證書編號"], keep="first")
        cert_due = cert_due.sort_values("商品驗證剩餘天數")
        if not cert_due.empty:
            cert_due_df = cert_due[["商品驗證證書編號", "室外機型號", "商品驗證有效期限"]].rename(columns={
                "商品驗證證書編號": "證書編號", "室外機型號": "型號", "商品驗證有效期限": "有效日期",
            })
        else:
            cert_due_df = pd.DataFrame(columns=["證書編號", "型號", "有效日期"])
        st.dataframe(cert_due_df, use_container_width=True, hide_index=True, height=188)

    # ── 區塊 5：90天內即將到期清單（商品驗證＋節能標章混合，去重）──
    with col5, st.container(key="chart_card_01_5"):
        st.markdown('<div class="block-card-title">5　90天內即將到期清單</div>', unsafe_allow_html=True)
        due = df[(df["商品驗證風險狀態"] == "90天內") | (df["節能標章風險狀態"] == "90天內")].copy()
        rows = []
        for _, r in due.iterrows():
            if r["商品驗證風險狀態"] == "90天內":
                rows.append({
                    "證書類型": "商品驗證", "證書編號": r["商品驗證證書編號"],
                    "型號": r["室外機型號"], "有效日期": r["商品驗證有效期限"],
                    "剩餘天數": int(r["商品驗證剩餘天數"]) if pd.notna(r["商品驗證剩餘天數"]) else None,
                })
            if r["節能標章風險狀態"] == "90天內":
                rows.append({
                    "證書類型": "節能標章", "證書編號": r["節能標章證書編號"],
                    "型號": r["室外機型號"], "有效日期": r["節能標章有效日期"],
                    "剩餘天數": int(r["節能標章剩餘天數"]) if pd.notna(r["節能標章剩餘天數"]) else None,
                })
        due_df = pd.DataFrame(rows).sort_values("剩餘天數") if rows else pd.DataFrame(
            columns=["證書類型", "證書編號", "型號", "有效日期", "剩餘天數"])
        due_df = due_df.drop_duplicates(subset=["證書編號"], keep="first")
        due_df = due_df.drop(columns=["剩餘天數"])
        st.dataframe(due_df, use_container_width=True, hide_index=True, height=188)

    # ── 區塊 6：未來半年每月到期張數統計（橫軸改月份，去重後計算）──
    with col6, st.container(key="chart_card_01_6"):
        st.markdown('<div class="block-card-title">6　未來半年每月到期張數統計</div>', unsafe_allow_html=True)
        today = pd.Timestamp.now().normalize()
        month_starts = [today.replace(day=1) + pd.DateOffset(months=i) for i in range(6)]
        month_labels = [m.strftime("%Y/%m") for m in month_starts]

        def _month_label(dt):
            if pd.isna(dt):
                return None
            label = dt.strftime("%Y/%m")
            return label if label in month_labels else None

        cert_future = df_cert_unique[df_cert_unique["商品驗證有效期限_dt"] >= today].copy()
        badge_future = df_badge_unique[df_badge_unique["節能標章有效日期_dt"] >= today].copy()
        cert_future["月份"] = cert_future["商品驗證有效期限_dt"].apply(_month_label)
        badge_future["月份"] = badge_future["節能標章有效日期_dt"].apply(_month_label)

        c1 = cert_future.groupby("月份").size().reindex(month_labels, fill_value=0)
        c2 = badge_future.groupby("月份").size().reindex(month_labels, fill_value=0)

        fig = go.Figure()
        fig.add_bar(name="商品驗證到期張數", x=month_labels, y=c1.values, marker_color="#4472C4")
        fig.add_bar(name="節能標章到期張數", x=month_labels, y=c2.values, marker_color="#82BE7E")
        fig.update_layout(barmode="group", height=188, margin=MARGIN, legend=LEGEND_TOP,
                           plot_bgcolor="white", paper_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
