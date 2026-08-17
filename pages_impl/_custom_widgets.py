"""
01 頁區塊 4/5/6「組2」自訂內容（圖片／便條紙）的存取層。
每個登入帳號的內容各自獨立，互不影響。

- 便條紙文字 + 每格顯示模式 + 圖片尺寸設定：存 Google Sheets（Library tool 08 這份，新分頁「01自訂設定」）
- 圖片：存 S3（沿用 07/08 頁同一個 bucket，開新路徑 dashboard01-custom/）
"""
import streamlit as st
import boto3
import base64
from io import BytesIO
from datetime import datetime

OPS_SHEET_ID = "1DpsBjUnt45boxkN1LeZuELC0v2mqszn2PBB_TL1OqDQ"  # Library tool 08
SETTINGS_TAB = "01自訂設定"

S3_BUCKET = "cert-query-pdf"
CUSTOM_PREFIX = "dashboard01-custom"

NOTE_MAX_CHARS = 200
SLOTS = ["4", "5", "6", "wide"]
SETTINGS_HEADER = (
    ["帳號", "顯示模式"]
    + [f"{prefix}{slot}" for slot in ["4", "5", "6"] for prefix in ["區塊", "便條"]]
    + [f"圖片{slot}尺寸" for slot in SLOTS]
    + ["更新時間"]
)
# 展開後實際欄位順序：帳號, 顯示模式, 區塊4, 便條4, 區塊5, 便條5, 區塊6, 便條6,
#                     圖片4尺寸, 圖片5尺寸, 圖片6尺寸, 圖片wide尺寸, 更新時間


def _get_gspread_client(readonly=True):
    import gspread
    from google.oauth2.service_account import Credentials
    sa_info = dict(st.secrets["gcp_service_account"])
    scope = "spreadsheets.readonly" if readonly else "spreadsheets"
    creds = Credentials.from_service_account_info(
        sa_info, scopes=[f"https://www.googleapis.com/auth/{scope}"]
    )
    return gspread.authorize(creds)


def _get_or_create_ws(sh, title, rows=200, cols=15):
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
    "區塊4": "note", "便條4": "",
    "區塊5": "note", "便條5": "",
    "區塊6": "note", "便條6": "",
    "圖片4尺寸": "", "圖片5尺寸": "", "圖片6尺寸": "", "圖片wide尺寸": "",
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
                    "區塊4": row[2] or "note", "便條4": row[3],
                    "區塊5": row[4] or "note", "便條5": row[5],
                    "區塊6": row[6] or "note", "便條6": row[7],
                    "圖片4尺寸": row[8], "圖片5尺寸": row[9],
                    "圖片6尺寸": row[10], "圖片wide尺寸": row[11],
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
        settings.get("區塊4", "note"), settings.get("便條4", ""),
        settings.get("區塊5", "note"), settings.get("便條5", ""),
        settings.get("區塊6", "note"), settings.get("便條6", ""),
        settings.get("圖片4尺寸", ""), settings.get("圖片5尺寸", ""),
        settings.get("圖片6尺寸", ""), settings.get("圖片wide尺寸", ""),
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


def get_image_size(username: str, slot: str):
    """回傳 (寬, 高) 的 tuple（像素整數），沒設定就回傳 (None, None) 代表維持原始大小"""
    settings = load_user_settings(username)
    raw = settings.get(f"圖片{slot}尺寸", "")
    if not raw or "x" not in raw:
        return (None, None)
    try:
        w, h = raw.split("x")
        return (int(w), int(h))
    except (ValueError, TypeError):
        return (None, None)


def save_image_size(username: str, slot: str, width, height):
    settings = load_user_settings(username)
    settings[f"圖片{slot}尺寸"] = f"{int(width)}x{int(height)}" if width and height else ""
    save_user_settings(username, settings)


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
    load_custom_image_b64.clear()


@st.cache_data(ttl=3600, show_spinner=False)
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


@st.cache_data(ttl=3600, show_spinner=False)
def load_custom_image_b64(username: str, slot: str):
    """把圖片預先編碼成 base64 字串並快取住，避免每次重新整理都要重新編碼，
    是造成畫面閃爍的主因之一（每次都產生新字串，瀏覽器會整張圖重新載入）"""
    raw = load_custom_image(username, slot)
    if raw is None:
        return None
    return base64.b64encode(raw).decode()
