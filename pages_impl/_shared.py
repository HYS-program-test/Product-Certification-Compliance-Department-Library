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

_STYLE = """
<style>
  .page-header {
    display: flex; align-items: center; gap: 14px;
    background: #FFFFFF; border: 1px solid #E5E9EB; border-radius: 12px;
    padding: 1rem 1.25rem; margin-bottom: 1rem;
  }
  .page-header .ph-icon {
    width: 42px; height: 42px; min-width: 42px; border-radius: 10px;
    background: #EEF2F4; color: #16324F;
    display: flex; align-items: center; justify-content: center; font-size: 1.3rem;
  }
  .page-header .ph-title {
    font-size: 1.15rem; font-weight: 700; color: #16324F; line-height: 1.3;
  }
  .page-header .ph-sub {
    font-size: .8rem; color: #8A9AA3; margin-top: 2px;
  }
</style>
"""


def render_page_header(page_id: str, sub_override: str = None):
    meta = PAGE_META.get(page_id, {"icon": "📄", "title": page_id, "sub": ""})
    sub = sub_override if sub_override is not None else meta["sub"]
    st.markdown(f"""
    {_STYLE}
    <div class="page-header">
      <div class="ph-icon">{meta['icon']}</div>
      <div>
        <div class="ph-title">{page_id}　{meta['title']}</div>
        <div class="ph-sub">{sub}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)
