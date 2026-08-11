import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pages_impl._data import load_full_table, render_filter_bar
from pages_impl._shared import render_kpi_row, render_page_header

CATEGORY_ORDER = ["MA", "RA", "SA", "VRV"]

# 色彩配置
COLOR_BLUE = "#3B82F6"
COLOR_GREEN = "#10B981"
COLOR_LIGHT_ORANGE = "#FB923C"
COLOR_ORANGE = "#F59E0B"
COLOR_PURPLE = "#A855F7"

MARGIN = dict(t=35, b=10, l=10, r=10)


def _half_year_bucket(dt):
    if pd.isna(dt):
        return None
    try:
        year, month = dt.year, dt.month
        half = "上半" if month <= 6 else "下半"
        return f"{year}{half}"
    except AttributeError:
        return None


def inject_custom_style():
    st.markdown(
        """
        <style>
        .stApp {
            background-color: #EBF3FA;
        }
        .block-card-title {
            color: #1E3A8A;
            font-size: 0.9rem;
            font-weight: 700;
            margin-bottom: 6px;
        }
        div[data-testid="stVerticalBlock"] > div:has(div.block-card-title) {
            background-color: #FFFFFF !important;
            border: 1.5px solid #CBD5E1 !important;
            border-radius: 8px !important;
            padding: 12px !important;
            box-shadow: 0px 2px 4px rgba(0, 0, 0, 0.03);
        }
        </style>
    """,
        unsafe_allow_html=True,
    )


def render():
    inject_custom_style()
    render_page_header("01")

    df_all = load_full_table()
    if df_all.empty:
        st.warning(
            "目前讀不到資料，請確認 Secrets 設定（gcp_service_account）是否正確。"
        )
        return

    df = render_filter_bar(df_all, key_prefix="p01")

    if "商品驗證有效期限_dt" in df.columns:
        df["商品驗證有效期限_dt"] = pd.to_datetime(
            df["商品驗證有效期限_dt"], errors="coerce"
        )
    if "節能標章有效日期_dt" in df.columns:
        df["節能標章有效日期_dt"] = pd.to_datetime(
            df["節能標章有效日期_dt"], errors="coerce"
        )

    cert_valid = int((df["商品驗證有效"]).sum()) if "商品驗證有效" in df.columns else 0
    badge_valid = (
        int((df["標章覆蓋狀態"] == "標章有效").sum())
        if "標章覆蓋狀態" in df.columns
        else 0
    )
    due_90 = int(
        (
            (df["商品驗證風險狀態"] == "90天內")
            | (df["節能標章風險狀態"] == "90天內")
        ).sum()
    )
    valid_models = int(df["室外機型號"].nunique()) if "室外機型號" in df.columns else 0
    badge_models = (
        int(df.loc[df["標章覆蓋狀態"] == "標章有效", "室外機型號"].nunique())
        if "標章覆蓋狀態" in df.columns
        else 0
    )
    coverage_rate_num = (
        (badge_models / valid_models * 100) if valid_models else 0
    )
    coverage_rate_str = (
        f"{coverage_rate_num:.1f}%" if valid_models else "—"
    )

    render_kpi_row([
        ("商品驗證有效張數", cert_valid),
        ("節能標章有效張數", badge_valid),
        ("90天內到期張數", due_90),
        ("有效商品型號數", valid_models),
        ("已取得標章型號數", badge_models),
        ("整體標章取得率", coverage_rate_str),
    ])

    st.markdown('<div style="height:.2rem"></div>', unsafe_allow_html=True)

    # ==================================================================
    # 第一列：區塊 1, 2, 4
    # ==================================================================
    col1, col2, col4 = st.columns(3)

    # --- 區塊 1: 商品驗證登錄證書有效張數 (單層甜甜圈圖) ---
    with col1:
        st.markdown(
            '<div class="block-card-title">1 商品驗證登錄證書有效張數</div>',
            unsafe_allow_html=True,
        )
        g1 = (
            df[df["商品驗證有效"]]
            .groupby("類別")
            .size()
            .reindex(CATEGORY_ORDER, fill_value=0)
        )

        labels1 = [f"{k}, {v}" for k, v in g1.items()]
        fig1 = go.Figure(
            data=[
                go.Pie(
                    labels=labels1,
                    values=g1.values,
                    hole=0.70,
                    textinfo="label",
                    textposition="inside",
                    insidetextorientation="horizontal",
                    marker=dict(
                        colors=["#9EE0F5"] * len(g1),
                        line=dict(color="#FFFFFF", width=3),  # 加粗白線邊框
                    ),
                    showlegend=False,
                    sort=False,
                )
            ]
        )
        fig1.add_annotation(
            text=f"<b>{cert_valid}</b> <span style='font-size:16px;'>張</span>",
            x=0.5,
            y=0.5,
            font=dict(size=32, color="#1E293B"),
            showarrow=False,
        )
        fig1.update_layout(
            height=220,
            margin=dict(t=10, b=10, l=10, r=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(
            fig1, use_container_width=True, config={"displayModeBar": False}
        )

    # --- 區塊 2: 節能標章取得百分比 (多層同心圓環圖 + 白線分隔) ---
    with col2:
        st.markdown(
            '<div class="block-card-title">2 節能標章取得百分比</div>',
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

        rates = {}
        for cat in CATEGORY_ORDER:
            tot = valid_cnt.get(cat, 0)
            rates[cat] = (badge_cnt.get(cat, 0) / tot * 100) if tot > 0 else 0

        fig2 = go.Figure()
        ring_cfgs = [
            {"cat": "MA", "color": "#E1BEE7", "hole": 0.82, "radius": 0.98},
            {"cat": "VRV", "color": "#90CAF9", "hole": 0.68, "radius": 0.80},
            {"cat": "SA", "color": "#FFCC80", "hole": 0.54, "radius": 0.66},
            {"cat": "RA", "color": "#C5E1A5", "hole": 0.40, "radius": 0.52},
        ]

        for cfg in ring_cfgs:
            c_name = cfg["cat"]
            val = rates.get(c_name, 0)
            fig2.add_trace(
                go.Pie(
                    values=[val, max(0, 100 - val)],
                    labels=[f"{c_name}, {val:.1f}%", ""],
                    hole=cfg["hole"],
                    sort=False,
                    direction="clockwise",
                    rotation=90,
                    # 加入白線邊框 (line width=3) 達到與區塊 1 相同的白線間格效果
                    marker=dict(
                        colors=[cfg["color"], "#F1F5F9"],
                        line=dict(color="#FFFFFF", width=3),
                    ),
                    textinfo="none",
                    hoverinfo="label",
                    domain=dict(
                        x=[0.5 - cfg["radius"] / 2, 0.5 + cfg["radius"] / 2],
                        y=[0.5 - cfg["radius"] / 2, 0.5 + cfg["radius"] / 2],
                    ),
                    showlegend=False,
                )
            )

        fig2.add_annotation(
            text=f"<b>{coverage_rate_num:.0f}%</b>",
            x=0.5,
            y=0.5,
            font=dict(size=30, color="#1E293B"),
            showarrow=False,
        )
        fig2.update_layout(
            height=220,
            margin=dict(t=10, b=10, l=10, r=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(
            fig2, use_container_width=True, config={"displayModeBar": False}
        )

    # --- 區塊 4: 各類別 能效分級數量統計 (Sunburst / 多層圓環圖展現各類別) ---
    with col4:
        st.markdown(
            '<div class="block-card-title">4 各類別 能效分級數量統計</div>',
            unsafe_allow_html=True,
        )
        sub_eff = df[df["標章覆蓋狀態"] == "標章有效"]
        
        # 建立類別 (內環) -> 能效分級 (外環) 的多層級資料
        cat_grade_df = sub_eff.groupby(["類別", "能源效率分級"]).size().reset_index(name="張數")
        
        ids = []
        labels = []
        parents = []
        values = []
        
        # 內層：各類別總數
        for cat in CATEGORY_ORDER:
            c_tot = cat_grade_df[cat_grade_df["類別"] == cat]["張數"].sum()
            if c_tot > 0:
                ids.append(cat)
                labels.append(cat)
                parents.append("")
                values.append(c_tot)
        
        # 外層：各類別下的能效分級細項
        for _, r in cat_grade_df.iterrows():
            cat = r["類別"]
            grade = str(r["能源效率分級"]).strip()
            cnt = r["張數"]
            if grade != "" and cnt > 0:
                ids.append(f"{cat}_{grade}")
                labels.append(f"{grade}級: {cnt}張")
                parents.append(cat)
                values.append(cnt)

        fig4 = go.Figure(
            go.Sunburst(
                ids=ids,
                labels=labels,
                parents=parents,
                values=values,
                branchvalues="total",
                insidetextorientation="horizontal",
                marker=dict(
                    colorscale="Blues",
                    line=dict(color="#FFFFFF", width=2)
                )
            )
        )
        fig4.update_layout(
            height=220,
            margin=dict(t=10, b=10, l=10, r=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(
            fig4, use_container_width=True, config={"displayModeBar": False}
        )

    st.markdown('<div style="height:.3rem"></div>', unsafe_allow_html=True)

    # ==================================================================
    # 第二列：區塊 3, 5, 6
    # ==================================================================
    col3, col5, col6 = st.columns(3)

    # --- 區塊 3: 後續半年到期張數統計 ---
    with col3:
        st.markdown(
            '<div class="block-card-title">3 後續半年到期張數統計</div>',
            unsafe_allow_html=True,
        )
        today = pd.Timestamp.now().normalize()
        cert_future = df[df["商品驗證有效期限_dt"] >= today].copy()
        badge_future = df[df["節能標章有效日期_dt"] >= today].copy()

        cert_future["區間"] = cert_future["商品驗證有效期限_dt"].apply(
            _half_year_bucket
        )
        badge_future["區間"] = badge_future["節能標章有效日期_dt"].apply(
            _half_year_bucket
        )

        buckets = sorted(
            set(cert_future["區間"].dropna())
            | set(badge_future["區間"].dropna())
        )[:6]
        c1 = cert_future.groupby("區間").size().reindex(buckets, fill_value=0)
        c2 = badge_future.groupby("區間").size().reindex(buckets, fill_value=0)

        fig3 = go.Figure()
        fig3.add_bar(
            name="商品驗證到期",
            x=buckets,
            y=c1.values,
            marker_color=COLOR_BLUE,
            text=c1.values,
            textposition="outside",
        )
        fig3.add_bar(
            name="節能標章到期",
            x=buckets,
            y=c2.values,
            marker_color=COLOR_GREEN,
            text=c2.values,
            textposition="outside",
        )
        fig3.update_layout(
            barmode="group",
            height=220,
            margin=MARGIN,
            legend=dict(
                orientation="h",
                y=1.25,
                x=0,
                font=dict(size=9, color="#4B5563"),
            ),
            plot_bgcolor="white",
            paper_bgcolor="white",
            yaxis=dict(
                showgrid=True, gridcolor="#F1F5F9", title=None, zeroline=False
            ),
            xaxis=dict(showgrid=False, tickangle=-25),
        )
        st.plotly_chart(
            fig3, use_container_width=True, config={"displayModeBar": False}
        )

    # --- 區塊 5: 各類別 CSPF 實測/標示分布 ---
    with col5:
        st.markdown(
            '<div class="block-card-title">5 各類別 CSPF 實測/標示 百分比分布</div>',
            unsafe_allow_html=True,
        )
        sub_cspf = df[df["CSPF風險區間"].notna()]
        pivot = (
            sub_cspf.groupby(["類別", "CSPF風險區間"])
            .size()
            .unstack(fill_value=0)
            .reindex(CATEGORY_ORDER, fill_value=0)
        )

        order = ["<100%", "100-102.9%", "103-105.9%", "≥106%"]
        colors5 = {
            "<100%": COLOR_LIGHT_ORANGE,
            "100-102.9%": COLOR_BLUE,
            "103-105.9%": COLOR_GREEN,
            "≥106%": COLOR_PURPLE,
        }

        fig5 = go.Figure()
        for bucket in order:
            if bucket in pivot.columns:
                fig5.add_bar(
                    name=bucket,
                    y=CATEGORY_ORDER,
                    x=pivot[bucket].values,
                    orientation="h",
                    marker_color=colors5[bucket],
                    text=pivot[bucket].values,
                    textposition="inside",
                )
        fig5.update_layout(
            barmode="stack",
            height=220,
            margin=MARGIN,
            legend=dict(
                orientation="h",
                y=1.25,
                x=0,
                font=dict(size=8, color="#4B5563"),
                traceorder="reversed",
            ),
            plot_bgcolor="white",
            paper_bgcolor="white",
            xaxis=dict(
                showgrid=True, gridcolor="#F1F5F9", title=None, zeroline=False
            ),
        )
        st.plotly_chart(
            fig5, use_container_width=True, config={"displayModeBar": False}
        )

    # --- 區塊 6: 90天內即將到期清單 ---
    with col6:
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
            if r.get("商品驗證風險狀態") == "90天內":
                rows.append({
                    "證書類型": "商品驗證",
                    "證書編號": r.get("商品驗證證書編號"),
                    "型號": r.get("室外機型號"),
                    "有效日期": r.get("商品驗證有效期限"),
                    "剩餘天數": (
                        int(r["商品驗證剩餘天數"])
                        if pd.notna(r.get("商品驗證剩餘天數"))
                        else None
                    ),
                })
            if r.get("節能標章風險狀態") == "90天內":
                rows.append({
                    "證書類型": "節能標章",
                    "證書編號": r.get("節能標章證書編號"),
                    "型號": r.get("室外機型號"),
                    "有效日期": r.get("節能標章有效日期"),
                    "剩餘天數": (
                        int(r["節能標章剩餘天數"])
                        if pd.notna(r.get("節能標章剩餘天數"))
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

        st.dataframe(
            due_df, use_container_width=True, hide_index=True, height=220
        )
