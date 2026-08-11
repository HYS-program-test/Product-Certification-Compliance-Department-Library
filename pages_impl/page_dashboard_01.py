import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ==========================================
# 1. 第一種：多層同心圓環圖 (節能標章取得百分比)
# ==========================================
def create_multi_ring_chart(rates_dict, total_avg_rate):
    """
    rates_dict: 各類別百分比，例如 {'MA': 100.0, 'VRV': 62.2, 'SA': 70.0, 'RA': 78.6}
    total_avg_rate: 中央顯示的整體百分比 (例如 72)
    """
    fig = go.Figure()

    # 設定各圈層由外到內的半徑 (hole, radius) 與顏色
    ring_configs = [
        {"name": "MA", "color": "#E1BEE7", "hole": 0.82, "radius": 0.98},   # 紫色 (最外層)
        {"name": "VRV", "color": "#90CAF9", "hole": 0.68, "radius": 0.80},  # 藍色
        {"name": "SA", "color": "#FFCC80", "hole": 0.54, "radius": 0.66},   # 橘色
        {"name": "RA", "color": "#C5E1A5", "hole": 0.40, "radius": 0.52},   # 綠色 (最內層)
    ]

    for cfg in ring_configs:
        cat = cfg["name"]
        val = rates_dict.get(cat, 0)
        rest = max(0, 100 - val)

        # 繪製單一圓環
        fig.add_trace(go.Pie(
            values=[val, rest],
            labels=[f"{cat}, {val:.1f}%", ""],
            hole=cfg["hole"],
            sort=False,
            direction="clockwise",
            rotation=90,  # 垂直向上為起點
            marker=dict(colors=[cfg["color"], "#F0F0F0"]), # 完成部分用指定色，剩餘部分用淺灰
            textinfo="none", # 自訂標籤顯示
            hoverinfo="label",
            domain=dict(x=[0.5 - cfg["radius"]/2, 0.5 + cfg["radius"]/2],
                        y=[0.5 - cfg["radius"]/2, 0.5 + cfg["radius"]/2]),
            showlegend=False
        ))

        # 加入文字標籤 (放置在圓環上方)
        # 可根據需求以 add_annotation 自訂文字位置

    # 中央 KPI 數字
    fig.add_annotation(
        text=f"<b>{total_avg_rate}%</b>",
        x=0.5, y=0.5,
        font=dict(size=36, color="#000000", family="Arial"),
        showarrow=False
    )

    fig.update_layout(
        title=dict(text="節能標章取得百分比", x=0.5, xanchor="center", font=dict(size=18, color="#555555")),
        height=320,
        margin=dict(t=50, b=20, l=20, r=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )
    return fig


# ==========================================
# 2. 第二種：單層甜甜圈圖 + 中央大字 (商品驗證有效張數)
# ==========================================
def create_donut_chart(data_dict, total_count):
    """
    data_dict: 各類別數量，例如 {'VRV': 30, 'RA': 17, 'SA': 11, 'MA': 5}
    total_count: 中央顯示的總張數 (例如 63)
    """
    labels = [f"{k}, {v}" for k, v in data_dict.items()]
    values = list(data_dict.values())
    
    # 圖二為統一的淺藍色系，中間以白色邊線分隔
    colors = ["#9EE0F5"] * len(values)

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.72, # 環狀寬度
        textinfo="label",
        textposition="inside",
        insidetextorientation="horizontal",
        marker=dict(colors=colors, line=dict(color="#FFFFFF", width=3)),
        showlegend=False,
        sort=False
    )])

    # 中央數字與單位
    fig.add_annotation(
        text=f"<b>{total_count}</b> <span style='font-size:20px; color:#333;'>張</span>",
        x=0.5, y=0.5,
        font=dict(size=42, color="#000000"),
        showarrow=False
    )

    fig.update_layout(
        title=dict(text="商品驗證登錄證書有效張數", x=0.5, xanchor="center", font=dict(size=18, color="#555555")),
        height=320,
        margin=dict(t=50, b=20, l=20, r=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )
    return fig


# ==========================================
# Streamlit 展示測試
# ==========================================
st.set_page_config(layout="wide")

col1, col2 = st.columns(2)

with col1:
    rates = {'MA': 100.0, 'VRV': 62.2, 'SA': 70.0, 'RA': 78.6}
    fig1 = create_multi_ring_chart(rates_dict=rates, total_avg_rate=72)
    st.plotly_chart(fig1, use_container_width=True)

with col2:
    counts = {'VRV': 30, 'RA': 17, 'SA': 11, 'MA': 5}
    fig2 = create_donut_chart(data_dict=counts, total_count=63)
    st.plotly_chart(fig2, use_container_width=True)
