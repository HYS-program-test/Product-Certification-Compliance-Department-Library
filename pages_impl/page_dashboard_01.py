import streamlit as st
from pages_impl._shared import render_page_header


def render():
    render_page_header("01")
    st.info("這一頁正在建置中，會依 Power BI 報表的欄位對應與 DAX 邏輯，改成讀取「Total Certificate Management」即時資料的版本。")
