"""
01-04 頁共用資料模組。
從「Total Certificate Management／工作表1」讀取原始資料，
並套用從 PBIP 專案 DAX 量值挖出來的門檻邏輯，算出跟原本 Power BI 報表一致的衍生欄位。

欄位對應（跟 07 商品證書查詢頁使用同一份資料來源，已與使用者核對過）：
  A  實驗室          B  類別            C  室外機型號
  F  商品驗證登錄證書編號  G  商品驗證有效期限
  N  安規測試報告編號
  X  CSPF實測值        Y  CSPF標示值      Z  CSPF實測/標示比
  AC 節能標章證書編號    AD 節能標章有效日期
  AG 能源效率分級       AI 登錄編號
"""
import streamlit as st
import pandas as pd
from datetime import datetime

DATA_SHEET_ID = "1hEt4uxBABBicxIMJuR57lMiigQYF02CQHZfB-Nc6vjo"  # Total Certificate Management
DATA_WORKSHEET_NAME = "工作表1"

COL_LETTERS = ["A", "B", "C", "F", "G", "N", "X", "Y", "Z", "AC", "AD", "AG", "AI"]
COL_NAMES = [
    "實驗室", "類別", "室外機型號", "商品驗證證書編號", "商品驗證有效期限",
    "安規測試報告編號", "CSPF_實測", "CSPF_標示", "CSPF實測標示比",
    "節能標章證書編號", "節能標章有效日期", "能源效率分級", "登錄編號",
]


def _col_letter_to_index(letter: str) -> int:
    idx = 0
    for ch in letter:
        idx = idx * 26 + (ord(ch.upper()) - ord("A") + 1)
    return idx - 1


@st.cache_resource
def _get_gsheet_client():
    import gspread
    from google.oauth2.service_account import Credentials
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)


@st.cache_data(show_spinner=False, ttl=300)
def _get_raw_values():
    gc = _get_gsheet_client()
    sh = gc.open_by_key(DATA_SHEET_ID)
    ws = sh.worksheet(DATA_WORKSHEET_NAME)
    return ws.get_all_values()


def _pct_to_float(text):
    """把 '99.23%' 或 '0.9923' 這種字串轉成 0~1 之間的浮點數；空值回傳 None"""
    text = str(text).strip()
    if text in ("", "nan", "None"):
        return None
    try:
        if text.endswith("%"):
            return float(text[:-1]) / 100.0
        v = float(text)
        return v / 100.0 if v > 1.5 else v  # 保險：如果是 99.2 這種百分比數字也校正
    except ValueError:
        return None


def _to_float(text):
    text = str(text).strip()
    if text in ("", "nan", "None"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


@st.cache_data(show_spinner=False, ttl=300)
def load_full_table() -> pd.DataFrame:
    """讀取完整欄位，並套用 DAX 挖出來的門檻邏輯算出衍生欄位"""
    try:
        values = _get_raw_values()
        col_idxs = [_col_letter_to_index(c) for c in COL_LETTERS]
        rows = values[2:]  # 跳過雙層表頭
        data = []
        for row in rows:
            data.append([row[i] if i < len(row) else "" for i in col_idxs])
        df = pd.DataFrame(data, columns=COL_NAMES)
        df = df[df["室外機型號"].astype(str).str.strip() != ""].reset_index(drop=True)

        today = pd.Timestamp(datetime.now().date())

        # ── 商品驗證證書 ──
        df["商品驗證有效期限_dt"] = pd.to_datetime(df["商品驗證有效期限"], errors="coerce")
        df["商品驗證剩餘天數"] = (df["商品驗證有效期限_dt"] - today).dt.days
        df["商品驗證有效"] = df["商品驗證證書編號"].astype(str).str.strip() != ""

        def cert_risk(days, has_cert):
            if not has_cert or pd.isna(days):
                return None
            if days < 0:
                return "已到期"
            if days <= 90:
                return "90天內"
            if days <= 180:
                return "91-180天"
            return "180天以上"

        df["商品驗證風險狀態"] = [
            cert_risk(d, h) for d, h in zip(df["商品驗證剩餘天數"], df["商品驗證有效"])
        ]

        # ── 節能標章 ──
        df["節能標章有效日期_dt"] = pd.to_datetime(df["節能標章有效日期"], errors="coerce")
        df["節能標章剩餘天數"] = (df["節能標章有效日期_dt"] - today).dt.days
        df["有節能標章"] = df["節能標章證書編號"].astype(str).str.strip() != ""

        def badge_status(has_badge, days):
            if not has_badge:
                return "未取得標章"
            if pd.isna(days):
                return "未取得標章"
            if days < 0:
                return "標章已到期"
            return "標章有效"

        df["標章覆蓋狀態"] = [
            badge_status(h, d) for h, d in zip(df["有節能標章"], df["節能標章剩餘天數"])
        ]

        def badge_risk(days, has_badge):
            if not has_badge or pd.isna(days):
                return None
            if days < 0:
                return "已到期"
            if days <= 90:
                return "90天內"
            if days <= 180:
                return "91-180天"
            return "180天以上"

        df["節能標章風險狀態"] = [
            badge_risk(d, h) for d, h in zip(df["節能標章剩餘天數"], df["有節能標章"])
        ]

        # ── CSPF ──
        df["CSPF_實測_num"] = df["CSPF_實測"].apply(_to_float)
        df["CSPF_標示_num"] = df["CSPF_標示"].apply(_to_float)
        ratio_from_col = df["CSPF實測標示比"].apply(_pct_to_float)
        ratio_computed = df["CSPF_實測_num"] / df["CSPF_標示_num"]
        df["CSPF實測標示比_num"] = ratio_from_col.combine_first(ratio_computed)

        def cspf_bucket(ratio):
            if pd.isna(ratio):
                return None
            if ratio < 1.0:
                return "<100%"
            if ratio < 1.03:
                return "100-102.9%"
            if ratio < 1.06:
                return "103-105.9%"
            return "≥106%"

        df["CSPF風險區間"] = df["CSPF實測標示比_num"].apply(cspf_bucket)
        df["CSPF低於標示"] = df["CSPF實測標示比_num"].apply(
            lambda r: bool(r is not None and not pd.isna(r) and r < 1.0)
        )

        # ── 資料品質 ──
        def quality_reasons(row):
            reasons = []
            if str(row["登錄編號"]).strip() == "":
                reasons.append("缺登錄編號")
            if str(row["能源效率分級"]).strip() == "":
                reasons.append("缺能效分級")
            if not row["商品驗證有效"] and not row["有節能標章"]:
                reasons.append("未配對室內機")
            return "；".join(reasons)

        df["資料品質異常原因"] = df.apply(quality_reasons, axis=1)
        df["資料品質異常"] = df["資料品質異常原因"] != ""

        return df
    except Exception as e:
        st.error(f"❌ 無法載入 Total Certificate Management 資料：{e}")
        return pd.DataFrame()


def apply_filters(df: pd.DataFrame, category=None, lab=None, energy_grade=None, badge_status=None) -> pd.DataFrame:
    """套用畫面上的篩選器（類別／實驗室／能效分級／標章狀態）"""
    out = df
    if category and category != "全部":
        out = out[out["類別"] == category]
    if lab and lab != "全部":
        out = out[out["實驗室"] == lab]
    if energy_grade and energy_grade != "全部":
        out = out[out["能源效率分級"] == energy_grade]
    if badge_status and badge_status != "全部":
        out = out[out["標章覆蓋狀態"] == badge_status]
    return out


def render_filter_bar(df: pd.DataFrame, key_prefix: str, show_badge=False):
    """畫出篩選器列，回傳篩選後的 DataFrame"""
    categories = ["全部"] + sorted([c for c in df["類別"].dropna().unique() if str(c).strip() != ""])
    labs = ["全部"] + sorted([c for c in df["實驗室"].dropna().unique() if str(c).strip() != ""])
    grades = ["全部"] + sorted([c for c in df["能源效率分級"].dropna().unique() if str(c).strip() != ""])

    n_cols = 4 if show_badge else 3
    cols = st.columns(n_cols)
    with cols[0]:
        category = st.selectbox("類別", categories, key=f"{key_prefix}_cat")
    with cols[1]:
        lab = st.selectbox("實驗室", labs, key=f"{key_prefix}_lab")
    with cols[2]:
        grade = st.selectbox("能效分級", grades, key=f"{key_prefix}_grade")
    badge = None
    if show_badge:
        badges = ["全部", "標章有效", "標章已到期", "未取得標章"]
        with cols[3]:
            badge = st.selectbox("標章狀態", badges, key=f"{key_prefix}_badge")

    return apply_filters(df, category, lab, grade, badge)
