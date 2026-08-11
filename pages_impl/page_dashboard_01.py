import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pages_impl._data import load_full_table, render_filter_bar
from pages_impl._shared import render_kpi_row, render_page_header

CATEGORY_ORDER = ["MA", "RA", "SA", "VRV"]

# 6. 淡色系色彩配置 (馬卡龍 / 低飽和色)
COLOR_PASTEL_BLUE = "#60A5FA"      # 淡藍
COLOR_PASTEL_GREEN = "#34D399"     # 柔綠
COLOR_PASTEL_ORANGE = "#FDBA74"    # 淡橘 (警示/CSPF <100%)
COLOR_PASTEL_PURPLE = "#C084FC"    # 淡紫
COLOR_PASTEL_BLUE_DARK = "#93C5FD" # 淺天藍

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
    """1. 取消外框 & 7. 調整表格字體大小與標題一致且不粗體"""
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
        /* 1. 取消 1~6 區塊外框 (border: none, box-shadow: none) */
        div[data-testid="stVerticalBlock"] > div:has(div.block-card-title) {
            background-color: #FFFFFF !important;
            border: none !important;
            border-radius: 8px !important;
            padding: 12px !important;
            box-shadow: none !important;
        }
        
        /* 7. 90天內即將到期清單 表格文字樣式 (同標題大小 0.9rem、不粗體) */
        div[data-testid="stDataFrame"] div[data-testid="stTable"] {
            font-size: 0.9rem !important;
            font-weight: 400 !important;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
        }
        div[data-testid="stDataFrame"] table {
            font-size: 0.9rem !important;
            font-weight: 400 !important;
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

    # 4. 計算數量時以證書編號為主，去掉重複計算
    df_cert_unique = df[df["商品驗證有效"]].drop_duplicates("商品驗證證書編號") if "商品驗證證書編號" in df.columns else df[df["商品驗證有效"]]
    df_badge_unique = df[df["標章覆蓋狀態"] == "標章有效"].drop_duplicates("節能標章證書編號") if "節能標章證書編號" in df.columns else df[df["標章覆蓋狀態"] == "標章有效"]

    cert_valid = len(df_cert_unique)
    badge_valid = len(df_badge_unique)
    
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
    # 第一列：區塊 1, 2, 3
    # ==================================================================
    col1, col2, col3 = st.columns(3)

    # --- 區塊 1: 商品驗證登錄證書有效張數 ---
    with col1:
        st.markdown(
            '<div class="block-card-title">1 商品驗證登錄證書有效張數</div>',
            unsafe_allow_html=True,
        )
        # 4. 以證書編號去重後統計各類別張數
        g1 = (
            df_cert_unique.groupby("類別")
            .size()
            .reindex(CATEGORY_ORDER, fill_value=0)
        )

        labels1 = [f"{k}, {v}" for k, v in g1.items()]
        fig1 = go.Figure(
            data=[
                go.Pie(
                    labels=labels1,
                    values=g1.values,
                    hole=0.72,
                    textinfo="label",
                    textposition="inside",
                    insidetextorientation="horizontal",
                    marker=dict(
                        colors=["#9EE0F5"] * len(g1),
                        line=dict(color="#FFFFFF", width=3),
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

    # --- 區塊 2: 節能標章取得百分比 ---
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
        # 2. 調整各圈層厚度為 0.08，hole 放寬至 0.58，確保不擋到中央數字
        ring_cfgs = [
            {"cat": "MA", "color": "#E1BEE7", "hole": 0.84, "radius": 1.00},
            {"cat": "VRV", "color": "#90CAF9", "hole": 0.75, "radius": 0.83},
            {"cat": "SA", "color": "#FFCC80", "hole": 0.66, "radius": 0.74},
            {"cat": "RA", "color": "#C5E1A5", "hole": 0.58, "radius": 0.65},
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
            font=dict(size=28, color="#1E293B"),
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

    # --- 5. 修正標題: 3 各類別能效分級數量統計 ---
    with col3:
        st.markdown(
            '<div class="block-card-title">3 各類別能效分級數量統計</div>',
            unsafe_allow_html=True,
        )
        # 4. 以證書編號去重後統計
        sub_eff = df[df["標章覆蓋狀態"] == "標章有效"]
        if "節能標章證書編號" in sub_eff.columns:
            sub_eff = sub_eff.drop_duplicates("節能標章證書編號")
            
        # 3. 統計各類別與所有能效分級 (不限1級)
        cat_grade_df = sub_eff.groupby(["類別", "能源效率分級"]).size().reset_index(name="張數")
        
        ids, labels, parents, values = [], [], [], []
        total_badge_certs = sub_eff.shape[0]

        for cat in CATEGORY_ORDER:
            c_tot = cat_grade_df[cat_grade_df["類別"] == cat]["張數"].sum()
            if c_tot > 0:
                ids.append(cat)
                labels.append(cat)
                parents.append("")
                values.append(c_tot)
        
        for _, r in cat_grade_df.iterrows():
            cat = r["類別"]
            grade = str(r["能源效率分級"]).strip()
            cnt = r["張數"]
            if grade != "" and cnt > 0:
                ids.append(f"{cat}_{grade}")
                labels.append(f"{grade}級: {cnt}張")
                parents.append(cat)
                values.append(cnt)

        # 3. 中間留白 Sunburst 圖形
        fig3_sun = go.Figure(
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
        # 3. 在中央放置總張數標示
        fig3_sun.add_annotation(
            text=f"<b>{total_badge_certs}</b> <span style='font-size:12px;'>張</span>",
            x=0.5, y=0.5,
            font=dict(size=18, color="#1E293B"),
            showarrow=False
        )
        fig3_sun.update_layout(
            height=220,
            margin=dict(t=10, b=10, l=10, r=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(
            fig3_sun, use_container_width=True, config={"displayModeBar": False}
        )

    st.markdown('<div style="height:.3rem"></div>', unsafe_allow_html=True)

    # ==================================================================
    # 第二列：區塊 4, 5, 6
    # ==================================================================
    col4, col5, col6 = st.columns(3)

    # --- 5. 修正標題: 4 後續半年到期張數統計 ---
    with col4:
        st.markdown(
            '<div class="block-card-title">4 後續半年到期張數統計</div>',
            unsafe_allow_html=True,
        )
        today = pd.Timestamp.now().normalize()
        # 4. 去重後計算到期統計
        cert_future = df_cert_unique[df_cert_unique["商品驗證有效期限_dt"] >= today].copy()
        badge_future = df_badge_unique[df_badge_unique["節能標章有效日期_dt"] >= today].copy()

        cert_future["區間"] = cert_future["商品驗證有效期限_dt"].apply(_half_year_bucket)
        badge_future["區間"] = badge_future["節能標章有效日期_dt"].apply(_half_year_bucket)

        buckets = sorted(
            set(cert_future["區間"].dropna())
            | set(badge_future["區間"].dropna())
        )[:6]
        c1 = cert_future.groupby("區間").size().reindex(buckets, fill_value=0)
        c2 = badge_future.groupby("區間").size().reindex(buckets, fill_value=0)

        fig4 = go.Figure()
        # 6. 淡化長條圖顏色 (COLOR_PASTEL_BLUE, COLOR_PASTEL_GREEN)
        fig4.add_bar(
            name="商品驗證到期",
            x=buckets,
            y=c1.values,
            marker_color=COLOR_PASTEL_BLUE,
            text=c1.values,
            textposition="outside",
        )
        fig4.add_bar(
            name="節能標章到期",
            x=buckets,
            y=c2.values,
            marker_color=COLOR_PASTEL_GREEN,
            text=c2.values,
            textposition="outside",
        )
        fig4.update_layout(
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
            fig4, use_container_width=True, config={"displayModeBar": False}
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
        # 6. 淡化橫向長條圖顏色
        colors5 = {
            "<100%": COLOR_PASTEL_ORANGE,
            "100-102.9%": COLOR_PASTEL_BLUE,
            "103-105.9%": COLOR_PASTEL_GREEN,
            "≥106%": COLOR_PASTEL_PURPLE,
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
