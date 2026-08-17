"""
01 頁區塊 4/5/6「組2」自訂內容（圖片／便條紙）的存取層。
每個登入帳號的內容各自獨立，互不影響。

- 便條紙文字 + 每格顯示模式 + 整列/個別切換：存 Google Sheets（Library tool 08 這份，新分頁「01自訂設定」）
- 圖片：存 S3（沿用 07/08 頁同一個 bucket，開新路徑 dashboard01-custom/）
"""
import streamlit as st
import boto3
from io import BytesIO
from datetime import datetime

OPS_SHEET_ID = "1DpsBjUnt45boxkN1LeZuELC0v2mqszn2PBB_TL1OqDQ"  # Library tool 08
SETTINGS_TAB = "01自訂設定"

S3_BUCKET = "cert-query-pdf"
CUSTOM_PREFIX = "dashboard01-custom"

NOTE_MAX_CHARS = 200
SETTINGS_HEADER = [
    "帳號", "顯示模式",
    "區塊4類型", "便條4內容",
    "區塊5類型", "便條5內容",
    "區塊6類型", "便條6內容",
    "更新時間",
]


def _get_gspread_client(readonly=True):
    import gspread
    from google.oauth2.service_account import Credentials
    sa_info = dict(st.secrets["gcp_service_account"])
    scope = "spreadsheets.readonly" if readonly else "spreadsheets"
    creds = Credentials.from_service_account_info(
        sa_info, scopes=[f"https://www.googleapis.com/auth/{scope}"]
    )
    return gspread.authorize(creds)


def _get_or_create_ws(sh, title, rows=200, cols=10):
    try:
        return sh.worksheet(title)
    except Exception:
        return sh.add_worksheet(title=title, rows=rows, cols=cols)


def get_s3_client():
    return boto3.client(
        "s3", region_name="ap-east-2",
        aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"],
    )


DEFAULT_SETTINGS = {
    "顯示模式": "individual",
    "區塊4類型": "note", "便條4內容": "",
    "區塊5類型": "note", "便條5內容": "",
    "區塊6類型": "note", "便條6內容": "",
}


@st.cache_data(ttl=20, show_spinner=False)
def load_user_settings(username: str) -> dict:
    try:
        gc = _get_gspread_client(readonly=True)
        sh = gc.open_by_key(OPS_SHEET_ID)
        ws = sh.worksheet(SETTINGS_TAB)
        values = ws.get_all_values()
        for row in values[1:]:
            if len(row) >= 1 and row[0] == username:
                row = row + [""] * (len(SETTINGS_HEADER) - len(row))
                return {
                    "顯示模式": row[1] or "individual",
                    "區塊4類型": row[2] or "note", "便條4內容": row[3],
                    "區塊5類型": row[4] or "note", "便條5內容": row[5],
                    "區塊6類型": row[6] or "note", "便條6內容": row[7],
                }
    except Exception:
        pass
    return dict(DEFAULT_SETTINGS)


def save_user_settings(username: str, settings: dict):
    gc = _get_gspread_client(readonly=False)
    sh = gc.open_by_key(OPS_SHEET_ID)
    ws = _get_or_create_ws(sh, SETTINGS_TAB, rows=50, cols=len(SETTINGS_HEADER))
    values = ws.get_all_values()
    rows = values[1:] if len(values) > 1 else []

    new_row = [
        username, settings.get("顯示模式", "individual"),
        settings.get("區塊4類型", "note"), settings.get("便條4內容", ""),
        settings.get("區塊5類型", "note"), settings.get("便條5內容", ""),
        settings.get("區塊6類型", "note"), settings.get("便條6內容", ""),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    ]
    found = False
    for i, row in enumerate(rows):
        if row and row[0] == username:
            rows[i] = new_row
            found = True
            break
    if not found:
        rows.append(new_row)

    ws.clear()
    ws.update([SETTINGS_HEADER] + rows)
    load_user_settings.clear()


def upload_custom_image(username: str, slot: str, file_bytes: bytes):
    """圖片統一轉存成 PNG，S3 key 固定是 {帳號}/{slot}.png，不用另外追蹤副檔名"""
    from PIL import Image
    img = Image.open(BytesIO(file_bytes)).convert("RGBA")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    s3 = get_s3_client()
    key = f"{CUSTOM_PREFIX}/{username}/{slot}.png"
    s3.upload_fileobj(buf, S3_BUCKET, key)
    load_custom_image.clear()


@st.cache_data(ttl=300, show_spinner=False)
def load_custom_image(username: str, slot: str):
    try:
        s3 = get_s3_client()
        buf = BytesIO()
        key = f"{CUSTOM_PREFIX}/{username}/{slot}.png"
        s3.download_fileobj(S3_BUCKET, key, buf)
        buf.seek(0)
        return buf.read()
    except Exception:
        return None
