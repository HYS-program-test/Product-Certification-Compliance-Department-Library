import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pages_impl._data import load_full_table, render_filter_bar
from pages_impl._shared import render_kpi_row, render_page_header

CATEGORY_ORDER = ["MA", "RA", "SA", "VRV"]

# 調整圖表全域設定：加大 top margin 避免圖例蓋到內容，高度適度放寬
LEGEND_TOP = dict(
    orientation="h",
    y=1.18,
    x=0,
    xanchor="left",
    yanchor="bottom",
    font=dict(size=10),
)
CHART_MARGIN = dict(t=28, b=10, l=10, r=10)
CHART_HEIGHT = 180


def _half_year_bucket(dt):
    if pd.isna(dt):
        return None
    year, month = dt.year, dt.month
    half = "上半" if month <= 6 else "下半"
    return f"{year}{half}"


def _inject_custom_css():
    """注入統一的圖卡樣式，強化視覺層次感"""
    st.markdown(
        """
        <style>
        .block-card-title {
            font-size: 0.9rem;
            font-weight: 600;
            color: #1F2937;
            margin-bottom: 8px;
            border-left: 3px solid #4472C4;
            padding-left: 8px;
        }
        div[data-element-id^="chart_card"] {
            background-color: #FFFFFF;
            border: 1px solid #E5E7EB;
            border-radius: 8px;
            padding: 12px;
            box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
        }
        </style>
    """,
        unsafe_allow_html=True,
    )


def render():
    _inject_custom_css()
    render_page_header("01")

    df_all = load_full_table()
    if df_all.empty:
        st.warning(
            "目前讀不到資料，請確認 Secrets 設定（gcp_service_account）是否正確。"
        )
        return

    df = render_filter_bar(df_all, key_prefix="p01")

    # KPI 數據計算
    cert_valid = int((df["商品驗證有效"]).sum())
    badge_valid = int((df["標章覆蓋狀態"] == "標章有效").sum())
    due_90 = int(
        (
            (df["商品驗證風險狀態"] == "90天內")
            | (df["節能標章風險狀態"] == "90天內")
        ).sum()
    )
    valid_models = int(df["室外機型號"].nunique())
    badge_models = int(
        df.loc[df["標章覆蓋狀態"] == "標章有效", "室外機型號"].nunique()
    )
    coverage_rate = (
        f"{badge_models / valid_models * 100:.1f}%" if valid_models else "—"
    )

    render_kpi_row([
        ("商品驗證有效張數", cert_valid),
        ("節能標章有效張數", badge_valid),
        ("90天內到期張數", due_90),
        ("有效商品型號數", valid_models),
        ("已取得標章型號數", badge_models),
        ("整體標章取得率", coverage_rate),
    ])

    st.markdown('<div style="height:.5rem"></div>', unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # 第一排圖表 (1, 2, 3)
    # ------------------------------------------------------------------
    col1, col2, col3 = st.columns(3)

    with col1, st.container(key="chart_card_01_1"):
        st.markdown(
            '<div class="block-card-title">1 各類別 商品驗證／節能標章'
            ' 有效張數</div>',
            unsafe_allow_html=True,
        )
        g1 = (
            df[df["商品驗證有效"]]
            .groupby("類別")
            .size()
            .reindex(CATEGORY_ORDER, fill_value=0)
        )
        g2 = (
            df[df["標章覆蓋狀態"] == "標章有效"]
            .groupby("類別")
            .size()
            .reindex(CATEGORY_ORDER, fill_value=0)
        )

        fig = go.Figure()
        fig.add_bar(
            name="商品驗證有效",
            x=CATEGORY_ORDER,
            y=g1.values,
            marker_color="#4472C4",
            text=g1.values,
            textposition="auto",
        )
        fig.add_bar(
            name="節能標章有效",
            x=CATEGORY_ORDER,
            y=g2.values,
            marker_color="#82BE7E",
            text=g2.values,
            textposition="auto",
        )
        fig.update_layout(
            barmode="group",
            height=CHART_HEIGHT,
            margin=CHART_MARGIN,
            legend=LEGEND_TOP,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(
            fig, use_container_width=True, config={"displayModeBar": False}
        )

    with col2, st.container(key="chart_card_01_2"):
        st.markdown(
            '<div class="block-card-title">2 各類別 標章取得百分比</div>',
            unsafe_allow_html=True,
        )
        badge_cnt = (
            df[df["標章覆蓋狀態"] == "標章有效"]
            .groupby("類別")["室外機型號"]
            .nunique()
            .reindex(CATEGORY_ORDER, fill_value=0)
        )
        valid_cnt = (
            df.groupby("類別")["室外機型號"]
            .nunique()
            .reindex(CATEGORY_ORDER, fill_value=0)
        )

        fig = go.Figure()
        fig.add_bar(
            name="已取得標章型號",
            x=CATEGORY_ORDER,
            y=badge_cnt.values,
            marker_color="#4472C4",
            text=badge_cnt.values,
            textposition="auto",
        )
        fig.add_bar(
            name="有效商品型號",
            x=CATEGORY_ORDER,
            y=valid_cnt.values,
            marker_color="#82BE7E",
            text=valid_cnt.values,
            textposition="auto",
        )
        fig.update_layout(
            barmode="group",
            height=CHART_HEIGHT,
            margin=CHART_MARGIN,
            legend=LEGEND_TOP,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(
            fig, use_container_width=True, config={"displayModeBar": False}
        )

    with col3, st.container(key="chart_card_01_3"):
        st.markdown(
            '<div class="block-card-title">3 後續半年到期張數統計</div>',
            unsafe_allow_html=True,
        )
        today = pd.Timestamp.now().normalize()
        cert_future = df[df["商品驗證有效期限_dt"] >= today].assign(
            區間=lambda x: x["商品驗證有效期限_dt"].apply(_half_year_bucket)
        )
        badge_future = df[df["節能標章有效日期_dt"] >= today].assign(
            區間=lambda x: x["節能標章有效日期_dt"].apply(_half_year_bucket)
        )

        buckets = sorted(
            set(cert_future["區間"].dropna())
            | set(badge_future["區間"].dropna())
        )[:6]
        c1 = cert_future.groupby("區間").size().reindex(buckets, fill_value=0)
        c2 = badge_future.groupby("區間").size().reindex(buckets, fill_value=0)

        fig = go.Figure()
        fig.add_bar(
            name="商品驗證到期",
            x=buckets,
            y=c1.values,
            marker_color="#4472C4",
        )
        fig.add_bar(
            name="節能標章到期",
            x=buckets,
            y=c2.values,
            marker_color="#82BE7E",
        )
        fig.update_layout(
            barmode="group",
            height=CHART_HEIGHT,
            margin=CHART_MARGIN,
            legend=LEGEND_TOP,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(
            fig, use_container_width=True, config={"displayModeBar": False}
        )

    st.markdown('<div style="height:.5rem"></div>', unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # 第二排圖表 (4, 5, 6)
    # ------------------------------------------------------------------
    col4, col5, col6 = st.columns(3)

    with col4, st.container(key="chart_card_01_4"):
        st.markdown(
            '<div class="block-card-title">4 各類別 能效分級數量統計</div>',
            unsafe_allow_html=True,
        )
        sub = df[df["標章覆蓋狀態"] == "標章有效"]
        pivot = (
            sub.groupby(["類別", "能源效率分級"])
            .size()
            .unstack(fill_value=0)
            .reindex(CATEGORY_ORDER, fill_value=0)
        )

        fig = go.Figure()
        colors = {"1": "#4472C4", "2": "#82BE7E", "3": "#ED9E4B"}
        for grade in sorted(pivot.columns):
            if str(grade).strip() == "":
                continue
            fig.add_bar(
                name=f"{grade} 級",
                y=CATEGORY_ORDER,
                x=pivot[grade].values,
                orientation="h",
                marker_color=colors.get(str(grade), "#A5D6A7"),
            )
        fig.update_layout(
            barmode="stack",
            height=CHART_HEIGHT,
            margin=CHART_MARGIN,
            legend=LEGEND_TOP,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(
            fig, use_container_width=True, config={"displayModeBar": False}
        )

    with col5, st.container(key="chart_card_01_5"):
        st.markdown(
            '<div class="block-card-title">5 各類別 CSPF'
            ' 實測/標示分布</div>',
            unsafe_allow_html=True,
        )
        sub = df[df["CSPF風險區間"].notna()]
        pivot = (
            sub.groupby(["類別", "CSPF風險區間"])
            .size()
            .unstack(fill_value=0)
            .reindex(CATEGORY_ORDER, fill_value=0)
        )

        order = ["<100%", "100-102.9%", "103-105.9%", "≥106%"]
        colors = {
            "<100%": "#C0504D",
            "100-102.9%": "#4472C4",
            "103-105.9%": "#82BE7E",
            "≥106%": "#8064A2",
        }

        fig = go.Figure()
        for bucket in order:
            if bucket in pivot.columns:
                fig.add_bar(
                    name=bucket,
                    y=CATEGORY_ORDER,
                    x=pivot[bucket].values,
                    orientation="h",
                    marker_color=colors[bucket],
                )
        fig.update_layout(
            barmode="stack",
            height=CHART_HEIGHT,
            margin=CHART_MARGIN,
            legend=dict(
                orientation="h",
                y=1.18,
                x=0,
                xanchor="left",
                font=dict(size=9),
                traceorder="reversed",
            ),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(
            fig, use_container_width=True, config={"displayModeBar": False}
        )

    with col6, st.container(key="chart_card_01_6"):
        st.markdown(
            '<div class="block-card-title">6 90天內即將到期清單</div>',
            unsafe_allow_html=True,
        )
        due = df[
            (df["商品驗證風險狀態"] == "90天內")
            | (df["節能標章風險狀態"] == "90天內")
        ].copy()

        rows = []
        for _, r in due.iterrows():
            if r["商品驗證風險狀態"] == "90天內":
                rows.append({
                    "證書類型": "商品驗證",
                    "證書編號": r["商品驗證證書編號"],
                    "型號": r["室外機型號"],
                    "有效日期": r["商品驗證有效期限"],
                    "剩餘天數": (
                        int(r["商品驗證剩餘天數"])
                        if pd.notna(r["商品驗證剩餘天數"])
                        else None
                    ),
                })
            if r["節能標章風險狀態"] == "90天內":
                rows.append({
                    "證書類型": "節能標章",
                    "證書編號": r["節能標章證書編號"],
                    "型號": r["室外機型號"],
                    "有效日期": r["節能標章有效日期"],
                    "剩餘天數": (
                        int(r["節能標章剩餘天數"])
                        if pd.notna(r["節能標章剩餘天數"])
                        else None
                    ),
                })

        if rows:
            due_df = pd.DataFrame(rows).sort_values("剩餘天數")
            due_df = due_df.drop_duplicates(subset=["證書編號"], keep="first")
            due_df = due_df.drop(columns=["剩餘天數"])
        else:
            due_df = pd.DataFrame(
                columns=["證書類型", "證書編號", "型號", "有效日期"]
            )

        # 調整表格呈現，避免佔用太大空間
        st.dataframe(
            due_df, use_container_width=True, hide_index=True, height=180
        )
