import streamlit as st

PAGE_META = {
    "01": {"icon": "📊", "title": "原儀表板",   "sub": "商品證書管理總覽"},
    "02": {"icon": "📈", "title": "新增分析",   "sub": "到期風險分層／標章覆蓋缺口／CSPF實測風險／資料品質異常"},
    "03": {"icon": "🔍", "title": "明細查詢",   "sub": "型號／證書／能效完整明細"},
    "04": {"icon": "⚠️", "title": "管理預警",   "sub": "90天內到期／標章覆蓋缺口／CSPF低於標示值／資料品質異常"},
    "05": {"icon": "🗂️", "title": "PDF掃描歸檔", "sub": "掃描檔上傳 → OCR辨識 → 寫入 Total Certificate Management"},
    "06": {"icon": "✂️", "title": "PDF切割工具", "sub": "多份文件掃描檔 → 自動偵測標題 → 拆分下載"},
    "07": {"icon": "📇", "title": "商品證書查詢", "sub": "商品驗證登錄證書 & 能效分級標示 查詢系統"},
    "08": {"icon": "🔁", "title": "生命週期審核", "sub": "到期清單 → 展延決策 → 排程寄信"},
}


def render_page_header(page_id: str, sub_override: str = None):
    meta = PAGE_META.get(page_id, {"icon": "📄", "title": page_id, "sub": ""})
    sub = sub_override if sub_override is not None else meta["sub"]
    html = (
        '<div class="page-header">'
        f'<div class="ph-icon">{meta["icon"]}</div>'
        '<div>'
        f'<div class="ph-title">{page_id}　{meta["title"]}</div>'
        f'<div class="ph-sub">{sub}</div>'
        '</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def render_kpi_row(items):
    """items: list of (label, value) tuples，畫一排 KPI 卡片（白底、莫蘭迪藍數字）"""
    cols = st.columns(len(items))
    for col, (label, value) in zip(cols, items):
        with col:
            html = (
                '<div class="kpi-card">'
                f'<div class="kpi-label">{label}</div>'
                f'<div class="kpi-value">{value}</div>'
                '</div>'
            )
            st.markdown(html, unsafe_allow_html=True)
