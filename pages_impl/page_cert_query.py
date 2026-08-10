import streamlit as st
import pandas as pd
import os
import hashlib
import boto3
import anthropic
import json
import random
import string
from io import BytesIO
from datetime import date, datetime
import urllib.request
import gspread
from google.oauth2.service_account import Credentials
from docx import Document as DocxDocument
from docx.oxml.ns import qn as docx_qn
from lxml import etree as docx_etree
from copy import deepcopy

from results_list import results_list


# ─────────────────────────────────────────────
# 固定驗證碼帳號（預留，填入信箱和驗證碼）
# ─────────────────────────────────────────────
FIXED_CODE_ACCOUNTS = {
    "hungys@hotaidev.com.tw": "123456",
    "lozbutt@hotaidev.com.tw": "071071",
}

COMPANY_DOMAIN = "hotaidev.com.tw"

# AI 查詢助理開關：預設開啟。要暫時關閉，去 Streamlit Cloud → Settings → Secrets
# 新增一行 ENABLE_AI_CHAT = "false"（不需改程式碼、不需重新上傳 GitHub）
# AI 查詢助理開關：改成 False 會讓對話框整個消失（含「申請送審文件」功能）
# 改成 True 則正常顯示，改完存檔、上傳 GitHub 後即生效
AI_CHAT_ENABLED = False

# ─────────────────────────────────────────────
# Session state 初始化
# ─────────────────────────────────────────────
def init_session():
    defaults = {
        "logged_in":        False,
        "username":         "",
        "search_result":    None,
        "search_query_type": "商品驗證登錄證書",
        "search_result_subtype": "aircon",
        "ai_messages":      None,
        "ai_input_key":     0,
        "login_step":       "email",
        "login_email":      "",
        "otp_code":         "",
        "otp_expiry":       None,
        "app_mode":         False,
        "app_step":         0,
        "app_data":         {},
        "app_confirmed":    False,
        "download_cart":    [],
        "login_error":      None,
        "last_login_nonce": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    if st.session_state["ai_messages"] is None:
        st.session_state["ai_messages"] = [
            {"role": "assistant", "content": (
                "你好！請問想查什麼？\n\n"
                "例如：\n"
                "・查 RXQ8AYLT 的證書\n"
                "・今年內到期的設備\n"
                "・所有一級能效的型號\n"
                "・VRV 類別的節能標章\n\n"
                "或輸入「申請送審文件」申請各項證書副本"
            )}
        ]

# ─────────────────────────────────────────────
# 路徑設定
# ─────────────────────────────────────────────
_HERE         = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DOCX = os.path.join(_HERE, "申請表範本.docx")
WATERMARK_FONT_PATH = os.path.join(_HERE, "NotoSansTC-Regular.ttf")

S3_CERT_FOLDER        = "I.Product verification login certifcate"
S3_ENERGY_SAVE_FOLDER = "III.Energy-saving label certificate"
S3_ENERGY_FOLDER      = "IV.Energy efficiency logo"
S3_AIR_PURIFIER_FOLDER = "IV.Energy efficiency logo/除濕機&除加濕空氣清淨機"  # 與除濕機共用同一個 S3 資料夾
S3_DEHUMIDIFIER_FOLDER = "IV.Energy efficiency logo/除濕機&除加濕空氣清淨機"  # 實際 S3 資料夾名稱（2026-07 確認，內有 8 個檔案）
S3_BUCKET             = "cert-query-pdf"

# ─────────────────────────────────────────────
# Google Sheets - 資料來源設定
# claude_dashboard_final.xlsx 已改由「Total Certificate Management」
# 這份 Google Sheet 取代，商品驗證登錄 / 節能標章 / 能效分級
# 三組資料全部整合在同一個工作表內，僅欄位位置不同。
# ─────────────────────────────────────────────
DATA_SHEET_ID       = "1hEt4uxBABBicxIMJuR57lMiigQYF02CQHZfB-Nc6vjo"  # Total Certificate Management
DATA_WORKSHEET_NAME = "工作表1"
DATA_WORKSHEET2_NAME = "工作表2"  # 空氣清淨機／除濕機能效分級標示

# ─────────────────────────────────────────────
# Google Sheets
# ─────────────────────────────────────────────
@st.cache_resource
def get_gsheet_client():
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

def log_login(email: str, success: bool):
    try:
        gc = get_gsheet_client()
        sh = gc.open_by_key(st.secrets["GOOGLE_SHEETS_ID"])
        ws = sh.worksheet("登入紀錄")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result = "成功" if success else "失敗"
        ws.append_row([email, now, result])
    except Exception as e:
        print(f"log_login error: {e}")

def log_download(email: str, filename: str, category: str, case_name: str = ""):
    try:
        gc = get_gsheet_client()
        sh = gc.open_by_key(st.secrets["GOOGLE_SHEETS_ID"])
        ws = sh.worksheet("下載紀錄")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ws.append_row([email, now, filename, category, case_name])
    except Exception as e:
        print(f"log_download error: {e}")

def log_application(applicant_email: str, fields: dict):
    """記錄送審文件申請到 Google Sheets「申請紀錄」工作表"""
    try:
        gc = get_gsheet_client()
        sh = gc.open_by_key(st.secrets["GOOGLE_SHEETS_ID"])
        try:
            ws = sh.worksheet("申請紀錄")
        except Exception:
            # 工作表不存在時自動建立並加上表頭
            ws = sh.add_worksheet(title="申請紀錄", rows=1000, cols=10)
            ws.append_row(["申請時間", "申請人信箱", "申請單位", "申請人姓名",
                           "案件名稱", "客戶名稱", "需求機型", "需要資料"])

        type_names = {1: "商品驗證登錄證書", 2: "安規測試報告書",
                      3: "節能標章證書", 4: "能效分級標示圖示"}
        selected_types = "、".join(type_names[n] for n in sorted(fields.get("doc_types", [])))
        if fields.get("doc_other"):
            selected_types += f"、其他（{fields['doc_other']}）"
        models_str = "、".join(fields.get("models", []))

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ws.append_row([
            now,
            applicant_email,
            fields.get("apply_unit", ""),
            fields.get("apply_person", ""),
            fields.get("apply_purpose", ""),
            fields.get("customer", ""),
            models_str,
            selected_types,
        ])
    except Exception as e:
        print(f"log_application error: {e}")

# ─────────────────────────────────────────────
# Gmail SMTP 寄驗證碼
# ─────────────────────────────────────────────
def send_otp(email: str, code: str) -> bool:
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    try:
        gmail_user     = st.secrets["GMAIL_USER"]
        gmail_password = st.secrets["GMAIL_APP_PASSWORD"]

        html_body = f"""
        <html><body style="font-family:Arial,sans-serif;font-size:14px;color:#333;">
        <h2 style="color:#5C7A8A;">【證書查詢系統】登入驗證碼</h2>
        <p>您的驗證碼為：</p>
        <h1 style="letter-spacing:8px;color:#7B98A8;font-size:36px;">{code}</h1>
        <p>驗證碼有效時間為 <strong>5 分鐘</strong>，請盡快輸入。</p>
        <p style="color:#888;font-size:12px;">此為系統自動發送，請勿回覆。</p>
        </body></html>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "【證書查詢系統】登入驗證碼"
        msg["From"]    = f"證書查詢系統通知 <{gmail_user}>"
        msg["To"]      = email
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, email, msg.as_string())

        return True
    except Exception as e:
        st.error(f"寄信錯誤：{e}")
        print(f"send_otp error: {e}")
        return False

# ─────────────────────────────────────────────
# AWS S3
# ─────────────────────────────────────────────
def get_s3_client():
    return boto3.client(
        "s3",
        region_name           = "ap-east-2",
        aws_access_key_id     = st.secrets["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key = st.secrets["AWS_SECRET_ACCESS_KEY"],
    )

@st.cache_data(show_spinner=False, ttl=300)
def find_and_download_s3(folder_prefix, keyword):
    try:
        s3 = get_s3_client()
        paginator = s3.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=S3_BUCKET, Prefix=folder_prefix + "/")
        for page in pages:
            for obj in page.get("Contents", []):
                key = obj["Key"]
                filename = key.split("/")[-1]
                if keyword.lower() in filename.lower() and filename:
                    buf = BytesIO()
                    s3.download_fileobj(S3_BUCKET, key, buf)
                    buf.seek(0)
                    return buf.read(), filename
    except Exception:
        pass
    return None, None

@st.cache_resource
def _ensure_watermark_font():
    """註冊內嵌的繁體中文 TTF 字型（Noto Sans TC）。
    改用真正內嵌字型而非 reportlab 內建的非內嵌 CID 字型（如 MSung-Light），
    因為非內嵌 CID 字型仰賴 PDF 閱讀器本身要有對應的中文字型才能正確顯示，
    在不同瀏覽器/PDF 閱讀器上可能顯示錯誤字元或亂碼；改用內嵌 TTF 後，
    字型輪廓直接包進 PDF 檔案，任何裝置開啟都會顯示一致。"""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    try:
        pdfmetrics.getFont("NotoSansTC")
    except Exception:
        pdfmetrics.registerFont(TTFont("NotoSansTC", WATERMARK_FONT_PATH))
    return True

def add_watermark_to_pdf(pdf_bytes: bytes, watermark_text: str) -> bytes:
    """在 PDF 每一頁加上指定的浮水印文字（單一置中、字體較大、半透明，支援中文自動換行）"""
    if not watermark_text:
        return pdf_bytes
    try:
        _ensure_watermark_font()
        from pypdf import PdfReader, PdfWriter
        from reportlab.pdfgen import canvas
        from reportlab.lib.colors import Color

        reader = PdfReader(BytesIO(pdf_bytes))
        writer = PdfWriter()
        for page in reader.pages:
            # 官方建議做法：合併前先把 /Rotate 旋轉標記「烘焙」進頁面內容本身，
            # 避免手動算角度補償在部分掃描檔案上出現文字顛倒/鏡射的問題
            if (page.rotation or 0) != 0:
                page.transfer_rotation_to_content()

            page_width = float(page.mediabox.width)
            page_height = float(page.mediabox.height)

            # 單一置中顯示、字體依頁面寬度自動放大，太長會自動換行（中文字約略正方形，
            # 用字體大小估算每行可放幾個字），不同大小的證書視覺呈現方式一致
            font_size = max(20, min(48, int(page_width / 14)))
            max_chars = max(4, int((page_width * 0.75) / font_size))
            lines = [watermark_text[i:i + max_chars] for i in range(0, len(watermark_text), max_chars)] or [watermark_text]
            line_height = font_size * 1.4

            wm_buf = BytesIO()
            c = canvas.Canvas(wm_buf, pagesize=(page_width, page_height))
            c.saveState()
            c.setFillColor(Color(0.5, 0.5, 0.5, alpha=0.35))
            c.setFont("NotoSansTC", font_size)
            c.translate(page_width / 2, page_height / 2)
            c.rotate(45)
            start_y = (len(lines) - 1) * line_height / 2
            for i, line in enumerate(lines):
                c.drawCentredString(0, start_y - i * line_height, line)
            c.restoreState()
            c.save()
            wm_buf.seek(0)

            wm_page = PdfReader(wm_buf).pages[0]
            page.merge_page(wm_page)
            writer.add_page(page)

        out_buf = BytesIO()
        writer.write(out_buf)
        out_buf.seek(0)
        return out_buf.read()
    except Exception as e:
        print(f"add_watermark_to_pdf error: {e}")
        return pdf_bytes  # 加浮水印失敗時，退回原始檔案，避免下載功能整個掛掉

def build_merged_download(cart: list, wm_middle: str) -> bytes:
    """合併下載清單中所有 PDF；「能效分級」類的資料不加浮水印，其餘依需要加上浮水印；已依 dedup_key 去重"""
    from pypdf import PdfReader, PdfWriter

    watermark_full_text = f"本文件僅供{wm_middle}送審使用" if wm_middle else ""
    writer = PdfWriter()
    seen = set()
    for item in cart:
        if item["dedup_key"] in seen:
            continue
        seen.add(item["dedup_key"])

        data, _ = find_and_download_s3(item["folder"], item["keyword"])
        if not data:
            continue

        needs_wm = ("能效分級" not in item["doc_type"]) and bool(watermark_full_text)
        if needs_wm:
            data = add_watermark_to_pdf(data, watermark_full_text)

        try:
            reader = PdfReader(BytesIO(data))
            for page in reader.pages:
                writer.add_page(page)
        except Exception as e:
            print(f"build_merged_download read error ({item.get('dedup_key')}): {e}")
            continue

    out_buf = BytesIO()
    writer.write(out_buf)
    out_buf.seek(0)
    return out_buf.read()

def render_apply_purpose_field():
    """左欄用：「申請用途：」標籤與「本文件僅供 [輸入框] 送審使用」全部放同一列，回傳處理過的 wm_middle 字串"""
    label_col, wm_col1, wm_col2, wm_col3 = st.columns([1.1, 0.9, 3.2, 0.9])
    with label_col:
        st.markdown("<div class='field-label' style='padding-top:9px'>申請用途：</div>", unsafe_allow_html=True)
    with wm_col1:
        st.markdown("<div style='text-align:left;padding-top:10px;font-size:.9rem;white-space:nowrap'>本文件僅供</div>", unsafe_allow_html=True)
    with wm_col2:
        wm_middle = st.text_input(
            "浮水印文字", placeholder="請輸入案件名稱",
            key="watermark_middle_text", label_visibility="collapsed",
        )
    with wm_col3:
        st.markdown("<div style='text-align:left;padding-top:10px;font-size:.9rem;white-space:nowrap'>送審使用</div>", unsafe_allow_html=True)
    return (wm_middle or "").strip()


def render_download_data_panel(wm_middle: str, cart_height: int = 176):
    """右欄用：下載清單顯示＋清空/下載按鈕；cart_height 用來跟左欄的總高度視覺對齊
    （Streamlit 的 columns 不會自動同步左右兩欄高度，這個數字是估算值，
    如果跟左欄對不太齊，之後可以再微調這個數字）"""
    cart = st.session_state.get("download_cart", [])

    st.markdown("<div class='field-label'>下載資料：</div>", unsafe_allow_html=True)
    disp_col, clear_col, dl_col = st.columns([2.2, 0.8, 0.8])

    with disp_col:
        with st.container(height=cart_height, border=True, key="cart_items_container"):
            if not cart:
                st.caption("（尚未加入任何資料）")
            else:
                for i, item in enumerate(cart):
                    item_col, del_col = st.columns([5, 1])
                    with item_col:
                        st.markdown(
                            f"<div style='font-size:.78rem;padding-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>{i+1}. {item['label']}</div>",
                            unsafe_allow_html=True,
                        )
                    with del_col:
                        if st.button("✕", key=f"del_cart_{i}_{item['dedup_key']}", help="移除這筆"):
                            cart.pop(i)
                            st.session_state["download_cart"] = cart
                            st.rerun()

    all_energy_label = len(cart) > 0 and all("能效分級" in item["doc_type"] for item in cart)
    can_download = len(cart) > 0 and (all_energy_label or wm_middle != "")
    needs_case_name = len(cart) > 0 and not all_energy_label and wm_middle == ""

    with clear_col:
        if st.button("🗑️ 清空", use_container_width=True, disabled=(len(cart) == 0), key="clear_cart_btn"):
            st.session_state["download_cart"] = []
            st.rerun()
    with dl_col:
        # key 依「清單內容＋浮水印文字」變化，避免瀏覽器沿用舊的下載內容
        cart_sig = "|".join(item["dedup_key"] for item in cart)
        merge_sig = (cart_sig, wm_middle)

        if can_download:
            if st.session_state.get("merged_download_sig") != merge_sig:
                # 只有購物車內容或案件名稱真的變了才重新合併＋加浮水印；
                # 其他跟下載清單無關的頁面重新整理（例如移除某一筆、搜尋結果逐筆確認）
                # 都不會再重複跑這個很花時間的動作
                with st.spinner("正在合併並加上浮水印…"):
                    merged_bytes = build_merged_download(cart, wm_middle)
                st.session_state["merged_download_bytes"] = merged_bytes
                st.session_state["merged_download_sig"] = merge_sig
            else:
                merged_bytes = st.session_state["merged_download_bytes"]
            fname = f"送審資料-{wm_middle}.pdf" if wm_middle else "送審資料.pdf"
        else:
            merged_bytes = b""
            fname = "送審資料.pdf"

        dl_key = f"cart_download_btn_{abs(hash(merge_sig))}"

        # 獨立容器＋專屬 CSS，避免被搜尋結果列小型下載按鈕的樣式覆蓋，看不出是否可點擊
        with st.container(key="cart_download_container"):
            if st.download_button(
                "⬇ 下載",
                data=merged_bytes,
                file_name=fname,
                mime="application/pdf",
                disabled=not can_download,
                use_container_width=True,
                key=dl_key,
            ):
                operator = st.session_state.get("username", "")
                for item in cart:
                    log_download(operator, item["dedup_key"], item["doc_type"], wm_middle)

    if all_energy_label and cart:
        st.caption("目前清單全部是「能效分級標示」類資料，不需加浮水印即可下載。")
    elif needs_case_name:
        st.caption("⚠️ 清單中含有非「能效分級標示」的資料，請先輸入「案件名稱」才能下載。")

# ─────────────────────────────────────────────
# 載入資料（Google Sheets：Total Certificate Management）
# ─────────────────────────────────────────────
def _col_letter_to_index(letter: str) -> int:
    """A -> 0, B -> 1, ..., Z -> 25, AA -> 26, AH -> 33 ..."""
    idx = 0
    for ch in letter:
        idx = idx * 26 + (ord(ch.upper()) - ord("A") + 1)
    return idx - 1

@st.cache_data(show_spinner=False, ttl=300)
def _get_total_cert_raw_values():
    """讀取 Total Certificate Management／工作表1 全部原始資料（含前兩列）"""
    gc = get_gsheet_client()
    sh = gc.open_by_key(DATA_SHEET_ID)
    ws = sh.worksheet(DATA_WORKSHEET_NAME)
    return ws.get_all_values()

@st.cache_data(show_spinner=False, ttl=300)
def _get_sheet2_raw_values():
    """讀取 Total Certificate Management／工作表2 全部原始資料（空氣清淨機／除濕機，含前兩列）"""
    gc = get_gsheet_client()
    sh = gc.open_by_key(DATA_SHEET_ID)
    ws = sh.worksheet(DATA_WORKSHEET2_NAME)
    return ws.get_all_values()

def _extract_columns(values, col_letters, skiprows=2):
    """依欄位字母（如 'A','B','AH'...）從原始 values 取出指定欄位，
    並跳過前 skiprows 列（對應原本 Excel 的 header=None, skiprows=N）"""
    col_idxs = [_col_letter_to_index(c) for c in col_letters]
    rows = values[skiprows:]
    result = []
    for row in rows:
        result.append([row[i] if i < len(row) else "" for i in col_idxs])
    return result

@st.cache_data(show_spinner=False, ttl=300)
def load_cert_data():
    try:
        values = _get_total_cert_raw_values()
        rows = _extract_columns(values, ["A", "B", "C", "F", "G"], skiprows=2)
        df = pd.DataFrame(rows, columns=["實驗室", "類別", "室外機型號", "商品驗證登錄書編號", "證書有效期限"])
        df = df.dropna(subset=["室外機型號"])
        df = df[df["室外機型號"].astype(str).str.strip() != ""].reset_index(drop=True)
        df["證書有效期限_dt"] = pd.to_datetime(df["證書有效期限"], errors="coerce")
        df["證書有效期限"] = df["證書有效期限_dt"].dt.strftime("%Y-%m-%d").fillna("")
        return df
    except Exception as e:
        st.error(f"❌ 無法載入商品驗證登錄證書資料：{e}")
        return pd.DataFrame()

def _format_decimal(value, decimals):
    """把數字格式化成固定小數位數；非數字或空值就原樣保留（不強制塞格式）"""
    text = str(value).strip()
    if text in ("", "nan", "None"):
        return ""
    try:
        return f"{float(text):.{decimals}f}"
    except ValueError:
        return text


@st.cache_data(show_spinner=False, ttl=300)
def load_energy_data():
    try:
        values = _get_total_cert_raw_values()
        # 類別=B, 室外機型號=AH, CSPF=Y, 能源效率等級=AG, 額定冷氣能力值=Q
        rows = _extract_columns(values, ["B", "AH", "Y", "AG", "Q"], skiprows=2)
        df = pd.DataFrame(rows, columns=["類別", "室外機型號", "冷氣季節性能因數CSPF", "能源效率等級", "額定冷氣能力標示"])
        df = df.dropna(subset=["室外機型號"])
        df = df[df["室外機型號"].astype(str).str.strip() != ""]
        df = df[["類別", "室外機型號", "冷氣季節性能因數CSPF", "能源效率等級", "額定冷氣能力標示"]].reset_index(drop=True)
        # CSPF 固定小數點後兩位、額定冷氣能力固定小數點後一位
        df["冷氣季節性能因數CSPF"] = df["冷氣季節性能因數CSPF"].apply(lambda v: _format_decimal(v, 2))
        df["額定冷氣能力標示"] = df["額定冷氣能力標示"].apply(lambda v: _format_decimal(v, 1))
        return df
    except Exception as e:
        st.error(f"❌ 無法載入能效分級標示資料：{e}")
        return pd.DataFrame()

@st.cache_data(show_spinner=False, ttl=300)
def load_energy_save_data():
    try:
        values = _get_total_cert_raw_values()
        rows = _extract_columns(values, ["B", "C", "AC", "AD", "AE"], skiprows=2)
        df = pd.DataFrame(rows, columns=["類別", "室外機型號", "節能標章證書編號", "節能標章有效日期", "節能室外機型號"])
        df = df.dropna(subset=["節能標章證書編號"])
        df = df[df["節能標章證書編號"].astype(str).str.strip() != ""].reset_index(drop=True)
        df["節能標章有效日期_dt"] = pd.to_datetime(df["節能標章有效日期"], errors="coerce")
        df["節能標章有效日期"] = df["節能標章有效日期_dt"].dt.strftime("%Y-%m-%d").fillna("")
        df["顯示型號"] = df["節能室外機型號"].astype(str).str.strip()
        df.loc[df["顯示型號"] == "", "顯示型號"] = df["室外機型號"].astype(str).str.strip()
        df.loc[df["顯示型號"] == "nan", "顯示型號"] = df["室外機型號"].astype(str).str.strip()
        return df
    except Exception as e:
        st.error(f"❌ 無法載入節能標章證書資料：{e}")
        return pd.DataFrame()

@st.cache_data(show_spinner=False, ttl=300)
def load_air_purifier_data():
    """空氣清淨機能效分級標示（工作表2：G=型號, H=能源效率分級, J=CASR值 用來判斷是否為空氣清淨機列）"""
    try:
        values = _get_sheet2_raw_values()
        rows = _extract_columns(values, ["G", "H", "J"], skiprows=2)
        df = pd.DataFrame(rows, columns=["型號", "能源效率分級", "_casr"])
        df = df.dropna(subset=["型號"])
        df = df[df["型號"].astype(str).str.strip() != ""]
        # J欄（CASR值）有值才是空氣清淨機那一列；除濕機列的 J 欄是空的
        df = df[df["_casr"].astype(str).str.strip() != ""]
        df = df[["型號", "能源效率分級"]].reset_index(drop=True)
        return df
    except Exception as e:
        st.error(f"❌ 無法載入空氣清淨機能效分級資料：{e}")
        return pd.DataFrame()

@st.cache_data(show_spinner=False, ttl=300)
def load_dehumidifier_data():
    """除濕機能效分級標示（工作表2：G=型號, H=能源效率分級, M=除濕能力 用來判斷是否為除濕機列）"""
    try:
        values = _get_sheet2_raw_values()
        rows = _extract_columns(values, ["G", "H", "M"], skiprows=2)
        df = pd.DataFrame(rows, columns=["型號", "能源效率分級", "_capacity"])
        df = df.dropna(subset=["型號"])
        df = df[df["型號"].astype(str).str.strip() != ""]
        # M欄（除濕能力）有值才是除濕機那一列；空氣清淨機列的 M 欄是空的
        df = df[df["_capacity"].astype(str).str.strip() != ""]
        df = df[["型號", "能源效率分級"]].reset_index(drop=True)
        return df
    except Exception as e:
        st.error(f"❌ 無法載入除濕機能效分級資料：{e}")
        return pd.DataFrame()

def search_energy_label(model_kw: str, category: str):
    """
    統一的「能效分級標示」搜尋邏輯，回傳 (result_df, subtype)。
    類別＝空氣清淨機／除濕機 → 直接查工作表2。
    類別＝全部／RA／MA／SA／VRV → 查工作表1（冷氣機）；
    若類別＝全部、有輸入型號關鍵字、但冷氣機查無資料，會自動改查空氣清淨機、
    再改查除濕機，抓到第一個有比對到型號的資料來源。
    """
    cat_filter = None if category in ("", "（全部）") else category

    if category == "空氣清淨機":
        df = load_air_purifier_data()
        result = df.copy()
        if model_kw:
            result = result[result["型號"].astype(str).str.contains(model_kw, case=False, na=False)]
        return result.reset_index(drop=True), "air_purifier"

    if category == "除濕機":
        df = load_dehumidifier_data()
        result = df.copy()
        if model_kw:
            result = result[result["型號"].astype(str).str.contains(model_kw, case=False, na=False)]
        return result.reset_index(drop=True), "dehumidifier"

    df = load_energy_data()
    result = df.copy()
    if model_kw:
        result = result[result["室外機型號"].astype(str).str.contains(model_kw, case=False, na=False)]
    if cat_filter:
        result = result[result["類別"].astype(str).str.contains(cat_filter, case=False, na=False)]

    if cat_filter is None and model_kw and len(result) == 0:
        df_ap = load_air_purifier_data()
        result_ap = df_ap[df_ap["型號"].astype(str).str.contains(model_kw, case=False, na=False)]
        if len(result_ap) > 0:
            return result_ap.reset_index(drop=True), "air_purifier"

        df_dh = load_dehumidifier_data()
        result_dh = df_dh[df_dh["型號"].astype(str).str.contains(model_kw, case=False, na=False)]
        if len(result_dh) > 0:
            return result_dh.reset_index(drop=True), "dehumidifier"

    return result.reset_index(drop=True), "aircon"

# ─────────────────────────────────────────────
# AI 查詢解析
# ─────────────────────────────────────────────
def parse_query_with_ai(user_message: str) -> dict:
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    this_year = today.year

    system_prompt = f"""你是一個冷氣設備證書查詢助理。今天是 {today_str}。

資料庫有三種資料：
1. 商品驗證登錄證書（欄位：實驗室、類別、室外機型號、商品驗證登錄書編號、證書有效期限）
2. 能效分級標示（欄位：類別、室外機型號、冷氣季節性能因數CSPF、能源效率等級、額定冷氣能力標示）
   - 「類別」除了 RA/MA/SA/VRV 這幾種冷氣分類外，也可能是「空氣清淨機」或「除濕機」（這兩種只有型號、能源效率等級，沒有 CSPF 等其他欄位）
3. 節能標章證書（欄位：類別、室外機型號、節能標章證書編號、節能標章有效日期）

類別：RA（住宅用）、MA（多聯機）、SA（商用）、VRV，能效分級標示還可另外指定「空氣清淨機」「除濕機」這兩種類別。能源效率等級 1~5，1 最省電。

日期篩選說明：
- 「今年到期」= 有效期限在 {this_year}-01-01 到 {this_year}-12-31 之間
- 「今年內到期」= 有效期限在 {today_str} 到 {this_year}-12-31 之間
- 「已到期」= 有效期限早於 {today_str}

只回傳 JSON，不要其他文字：
{{
  "query_type": "商品驗證登錄證書" 或 "能效分級標示" 或 "節能標章證書",
  "model_kw": "型號關鍵字或空字串",
  "category": "類別或空字串（能效分級標示可填 RA/MA/SA/VRV/空氣清淨機/除濕機）",
  "energy_level": "能效等級數字或空字串",
  "expire_year": "到期年份數字或空字串",
  "expire_before": "到期日早於此日期 YYYY-MM-DD 或空字串",
  "expire_after": "到期日晚於此日期 YYYY-MM-DD 或空字串",
  "reply": "給用戶的一句話說明，要包含正確的年份（今年是{this_year}年）"
}}"""

    try:
        client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}]
        )
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        return {
            "query_type": "商品驗證登錄證書",
            "model_kw": "", "category": "", "energy_level": "",
            "expire_year": "", "expire_before": "", "expire_after": "",
            "reply": f"抱歉，解析失敗：{e}"
        }

def execute_ai_query(parsed: dict):
    query_type    = parsed.get("query_type", "商品驗證登錄證書")
    model_kw      = parsed.get("model_kw", "").strip()
    category      = parsed.get("category", "").strip()
    energy_level  = parsed.get("energy_level", "").strip()
    expire_year   = parsed.get("expire_year", "").strip()
    expire_before = parsed.get("expire_before", "").strip()
    expire_after  = parsed.get("expire_after", "").strip()
    result_subtype = "aircon"

    if query_type == "商品驗證登錄證書":
        df = load_cert_data()
        result = df.copy()
        if model_kw:
            result = result[result["室外機型號"].astype(str).str.contains(model_kw, case=False, na=False)]
        if category:
            result = result[result["類別"].astype(str).str.contains(category, case=False, na=False)]
        if expire_year and "證書有效期限_dt" in result.columns:
            result = result[result["證書有效期限_dt"].dt.year == int(expire_year)]
        if expire_before and "證書有效期限_dt" in result.columns:
            result = result[result["證書有效期限_dt"] < pd.Timestamp(expire_before)]
        if expire_after and "證書有效期限_dt" in result.columns:
            result = result[result["證書有效期限_dt"] >= pd.Timestamp(expire_after)]

    elif query_type == "能效分級標示":
        result, result_subtype = search_energy_label(model_kw, category)
        if energy_level:
            level_col = "能源效率等級" if result_subtype == "aircon" else "能源效率分級"
            result = result[result[level_col].astype(str).str.strip() == energy_level]

    else:
        df = load_energy_save_data()
        result = df.copy()
        if model_kw:
            result = result[
                result["顯示型號"].astype(str).str.contains(model_kw, case=False, na=False) |
                result["室外機型號"].astype(str).str.contains(model_kw, case=False, na=False)
            ]
        if category:
            result = result[result["類別"].astype(str).str.contains(category, case=False, na=False)]
        if expire_year and "節能標章有效日期_dt" in result.columns:
            result = result[result["節能標章有效日期_dt"].dt.year == int(expire_year)]
        if expire_before and "節能標章有效日期_dt" in result.columns:
            result = result[result["節能標章有效日期_dt"] < pd.Timestamp(expire_before)]
        if expire_after and "節能標章有效日期_dt" in result.columns:
            result = result[result["節能標章有效日期_dt"] >= pd.Timestamp(expire_after)]

    st.session_state["search_result"]         = result.reset_index(drop=True)
    st.session_state["search_query_type"]     = query_type
    st.session_state["search_result_subtype"] = result_subtype

# ─────────────────────────────────────────────
# CSS（白底莫蘭迪藍風格）
# ─────────────────────────────────────────────
def inject_css():
    st.markdown("""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@300;400;500;700&display=swap');
      html, body, [class*="css"] { font-family: 'Noto Sans TC', sans-serif; }
      #MainMenu, footer, header,
      [data-testid="stHeader"], [data-testid="stToolbar"],
      [data-testid="stDecoration"] {
        display: none !important; visibility: hidden !important;
      }
      [data-testid="stStatusWidget"] {
        opacity: 0 !important; pointer-events: none !important;
      }
      [data-testid="collapsedControl"] {
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
      }
      .block-container { padding-top: 0 !important; margin-top: 0 !important; }
      .stApp { background-color: #FFFFFF; }
      .main-header {
        background: #FFFFFF; border: 1px solid #EBEEF0;
        color: #33414A; padding: 1.5rem 2.5rem 1.2rem;
        border-radius: 0 0 16px 16px; margin-bottom: 1rem;
      }
      .main-header h1 { font-size: 1.5rem; font-weight: 700; margin: 0; color: #5C7A8A; }
      .badge { display: inline-block; padding: .2rem .6rem; border-radius: 20px; font-size: .88rem; font-weight: 600; }
      .badge-cert       { background: #EEF2F4; color: #5C7A8A; }
      .badge-energy     { background: #EEF2F4; color: #5C7A8A; }
      .badge-energysave { background: #EEF2F4; color: #5C7A8A; }
      .stat-bar { display: flex; gap: 1rem; margin-bottom: 1rem; }
      .stat-card { background: #fff; border: 1px solid #EBEEF0; border-radius: 10px; padding: .75rem 1.2rem; flex: 1; text-align: center; }
      .stat-card .num { font-size: 1.6rem; font-weight: 700; color: #5C7A8A; }
      .stat-card .lbl { font-size: .75rem; color: #8A9AA3; margin-top: .1rem; }
      div[data-testid="stButton"] button {
        border-radius: 999px !important;
      }
      .field-label {
        font-size: .85rem; font-weight: 700; color: #4a6080; margin-bottom: 2px;
      }
      /* 左欄（查詢類型／型號＋類別＋搜尋／申請用途）三個區塊之間的垂直間距，
         強制統一，不用 Streamlit 預設對不同元件類型不一致的間距 */
      .st-key-search_left_col [data-testid="stVerticalBlock"] {
        gap: 14px !important;
      }
      /* 查詢類型／室外機型號／類別 這幾個 Streamlit 原生輸入元件的標籤，
         字體改成跟「申請用途」「下載資料」這種自訂 HTML 標籤一致 */
      [data-testid="stWidgetLabel"] p {
        font-size: .85rem !important; font-weight: 700 !important; color: #4a6080 !important;
      }
      div[data-testid="stDownloadButton"] button {
        background: #e8e8e8 !important; color: #444 !important;
        border: 1px solid #ccc !important; border-radius: 6px !important;
        padding: .25rem .6rem !important; font-size: .72rem !important;
      }
      /* 下載清單面板的「下載」鈕：獨立樣式，蓋過上面搜尋結果列小按鈕的樣式，
         可點擊＝莫蘭迪藍實心，反白＝灰色，兩者要能明顯區分 */
      .st-key-cart_download_container div[data-testid="stDownloadButton"] button {
        background: #7B98A8 !important; color: #fff !important;
        border: none !important; border-radius: 8px !important;
        padding: .5rem .8rem !important; font-size: .88rem !important; font-weight: 600 !important;
      }
      .st-key-cart_download_container div[data-testid="stDownloadButton"] button:hover:not(:disabled) {
        background: #5C7A8A !important;
      }
      .st-key-cart_download_container div[data-testid="stDownloadButton"] button:disabled {
        background: #d5dce6 !important; color: #98a6b8 !important; cursor: not-allowed !important;
      }
      .st-key-cart_items_container button {
        min-height: 1.6rem !important; height: 1.6rem !important; padding: 0 !important;
        font-size: .72rem !important; line-height: 1 !important;
      }
      /* stVerticalBlockBorderWrapper 是外層「有邊框的容器」，是 cart_items_container 的
         父層（不是子層），要用 :has() 從外往內找，才抓得到 */
      div[data-testid="stVerticalBlockBorderWrapper"]:has(.st-key-cart_items_container) {
        padding: 2px 4px !important;
      }
      /* 縮短清單每一列（型號項目＋刪除鈕）之間的垂直間距，不動水平對齊方式
         st-key-cart_items_container 這個 class 直接掛在 stVerticalBlock 本人身上（用瀏覽器
         檢查工具確認過），不需要再往下找一層 */
      .st-key-cart_items_container {
        gap: 0.1rem !important;
      }
      .st-key-cart_items_container div[data-testid="element-container"] {
        margin-bottom: 0 !important; margin-top: 0 !important;
      }
      .st-key-cart_items_container div[data-testid="stMarkdownContainer"] p {
        margin-bottom: 0 !important;
      }
      div[data-testid="stDownloadButton"] button:hover { background: #d0d0d0 !important; color: #222 !important; }
      hr { margin-top: 0.25rem !important; margin-bottom: 0.25rem !important; }
      .user-info { font-size: .88rem !important; color: #5C7A8A; line-height: 38px; text-align: right; }
      [data-testid="stSidebar"] { background: #F7F8F9 !important; }
    </style>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────
# 申請送審文件功能
# ─────────────────────────────────────────────

APPLICATION_FIELDS = [
    ("apply_unit",   "請問申請單位是？\n（例：*部分公司**部）"),
    ("apply_person", "申請人姓名是？"),
    ("apply_purpose","案件名稱 / 申請用途是？\n（例：*****新建工程）"),
    ("customer",     "資料需求的經銷商或客戶名稱是？"),
    ("models",       "需求機型是哪些？\n（多個型號請換行）"),
    ("doc_types",    "需要哪些文件？（可多選）\n1. 商品驗證登錄證書\n2. 安規測試報告書\n3. 節能標章證書\n4. 能效分級標示圖示\n5. 其他（請說明）\n\n請輸入編號，例：1, 2 或 1, 2, 5"),
]

CONFIRM_STEP   = "confirm"
SEND_STEP      = "send"

def is_application_trigger(text: str) -> bool:
    keywords = ["申請送審文件", "送審資料", "申請文件", "申請各項", "申請報告", "申請證書副本"]
    return any(kw in text for kw in keywords)

def parse_doc_types(user_input: str):
    import re
    doc_types = []
    doc_other = ""
    nums = re.findall(r"[1-5]", user_input)
    for n in nums:
        n = int(n)
        if n in [1, 2, 3, 4]:
            doc_types.append(n)
        elif n == 5:
            match = re.search(r"5[\s,、]*([^1-4\n,、]+)", user_input)
            doc_other = match.group(1).strip() if match else "其他"
    return sorted(set(doc_types)), doc_other

def fill_application_docx(fields: dict) -> bytes:
    qn = docx_qn
    etree = docx_etree

    CHECKED   = "■"
    UNCHECKED = "□"
    FONT_KAI  = "標楷體"

    def ensure_rpr(run_el):
        rpr = run_el.find(qn("w:rPr"))
        if rpr is None:
            rpr = etree.Element(qn("w:rPr"))
            run_el.insert(0, rpr)
        return rpr

    def set_run_font(rpr_el, font_name):
        fonts_el = rpr_el.find(qn("w:rFonts"))
        if fonts_el is None:
            fonts_el = etree.SubElement(rpr_el, qn("w:rFonts"))
            rpr_el.insert(0, fonts_el)
        for attr in [qn("w:ascii"), qn("w:eastAsia"), qn("w:hAnsi"), qn("w:cs")]:
            fonts_el.set(attr, font_name)
        hint_attr = qn("w:hint")
        if hint_attr in fonts_el.attrib:
            del fonts_el.attrib[hint_attr]

    def set_single_run_cell(tc, text):
        paras = tc.findall(qn("w:p"))
        for p in paras[1:]:
            tc.remove(p)
        first_p = paras[0]
        for r in first_p.findall(qn("w:r")):
            first_p.remove(r)
        new_r = etree.SubElement(first_p, qn("w:r"))
        rpr = etree.SubElement(new_r, qn("w:rPr"))
        new_r.insert(0, rpr)
        set_run_font(rpr, FONT_KAI)
        new_t = etree.SubElement(new_r, qn("w:t"))
        new_t.text = text
        if text.startswith(" ") or text.endswith(" "):
            new_t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")

    doc = DocxDocument(TEMPLATE_DOCX)
    tbl = doc.tables[0]

    def get_tcs(row_idx):
        return tbl.rows[row_idx]._tr.findall(qn("w:tc"))

    today = date.today()
    tw_year = today.year - 1911
    apply_date = f"{tw_year}年 {today.month} 月 {today.day} 日"
    set_single_run_cell(get_tcs(0)[0], f"申請日期： {apply_date}")

    r1 = get_tcs(1)
    set_single_run_cell(r1[1], fields.get("apply_unit", ""))
    set_single_run_cell(r1[3], fields.get("apply_person", ""))

    r2 = get_tcs(2)
    set_single_run_cell(r2[1], fields.get("apply_purpose", ""))
    set_single_run_cell(r2[3], fields.get("customer", ""))

    tc3 = get_tcs(3)[1]
    paras3 = tc3.findall(qn("w:p"))
    template_pPr = paras3[0].find(qn("w:pPr"))
    for p in paras3:
        tc3.remove(p)
    for model in fields.get("models", []):
        new_p = etree.SubElement(tc3, qn("w:p"))
        if template_pPr is not None:
            new_p.insert(0, deepcopy(template_pPr))
        new_r = etree.SubElement(new_p, qn("w:r"))
        rpr = etree.SubElement(new_r, qn("w:rPr"))
        new_r.insert(0, rpr)
        set_run_font(rpr, FONT_KAI)
        new_t = etree.SubElement(new_r, qn("w:t"))
        new_t.text = model.strip()
    if not fields.get("models"):
        etree.SubElement(tc3, qn("w:p"))

    tc4 = get_tcs(4)[1]
    paras4 = tc4.findall(qn("w:p"))
    doc_types = set(fields.get("doc_types", []))
    doc_other = fields.get("doc_other", "").strip()

    for para_idx, type_num in {1: 1, 2: 2, 3: 3, 4: 4}.items():
        runs = paras4[para_idx].findall(qn("w:r"))
        if runs:
            t_el = runs[0].find(qn("w:t"))
            if t_el is not None:
                t_el.text = CHECKED if type_num in doc_types else UNCHECKED
            rpr = ensure_rpr(runs[0])
            set_run_font(rpr, FONT_KAI)
            for tag in [qn("w:color"), qn("w:shd"), qn("w:spacing")]:
                el = rpr.find(tag)
                if el is not None:
                    rpr.remove(el)

    runs8 = paras4[8].findall(qn("w:r"))
    if runs8:
        t0 = runs8[0].find(qn("w:t"))
        if t0 is not None:
            t0.text = CHECKED if doc_other else UNCHECKED
        rpr0 = ensure_rpr(runs8[0])
        set_run_font(rpr0, FONT_KAI)
        for tag in [qn("w:color"), qn("w:shd"), qn("w:spacing")]:
            el = rpr0.find(tag)
            if el is not None:
                rpr0.remove(el)
        if len(runs8) >= 4:
            t3 = runs8[3].find(qn("w:t"))
            if t3 is not None:
                t3.text = ""

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()

def send_application_email(fields: dict, docx_bytes: bytes, applicant_email: str) -> bool:
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email import encoders

    try:
        gmail_user     = st.secrets["GMAIL_USER"]
        gmail_password = st.secrets["GMAIL_APP_PASSWORD"]
        recipient      = "hungys@hotaidev.com.tw"

        today = date.today()
        tw_year = today.year - 1911
        apply_date = f"{tw_year}年{today.month}月{today.day}日"

        type_names = {1: "商品驗證登錄證書", 2: "安規測試報告書", 3: "節能標章證書", 4: "能效分級標示圖示"}
        selected_types_html = "、".join(type_names[n] for n in sorted(fields.get("doc_types", [])))
        if fields.get("doc_other"):
            selected_types_html += f"、其他（{fields['doc_other']}）"
        models_html = "<br>".join(fields.get("models", []))

        html_body = f"""
        <html><body style="font-family:Arial,sans-serif;font-size:14px;color:#333;">
        <h2 style="color:#5C7A8A;">【證書查詢系統】送審文件申請</h2>
        <table style="border-collapse:collapse;width:100%;max-width:600px;">
          <tr><td style="padding:6px 12px;background:#EEF2F4;font-weight:bold;width:140px;">申請日期</td>
              <td style="padding:6px 12px;border-bottom:1px solid #eee;">{apply_date}</td></tr>
          <tr><td style="padding:6px 12px;background:#EEF2F4;font-weight:bold;">申請單位</td>
              <td style="padding:6px 12px;border-bottom:1px solid #eee;">{fields.get("apply_unit","")}</td></tr>
          <tr><td style="padding:6px 12px;background:#EEF2F4;font-weight:bold;">申請人</td>
              <td style="padding:6px 12px;border-bottom:1px solid #eee;">{fields.get("apply_person","")}</td></tr>
          <tr><td style="padding:6px 12px;background:#EEF2F4;font-weight:bold;">案件名稱</td>
              <td style="padding:6px 12px;border-bottom:1px solid #eee;">{fields.get("apply_purpose","")}</td></tr>
          <tr><td style="padding:6px 12px;background:#EEF2F4;font-weight:bold;">客戶名稱</td>
              <td style="padding:6px 12px;border-bottom:1px solid #eee;">{fields.get("customer","")}</td></tr>
          <tr><td style="padding:6px 12px;background:#EEF2F4;font-weight:bold;">需求機型</td>
              <td style="padding:6px 12px;border-bottom:1px solid #eee;">{models_html}</td></tr>
          <tr><td style="padding:6px 12px;background:#EEF2F4;font-weight:bold;">需要資料</td>
              <td style="padding:6px 12px;border-bottom:1px solid #eee;">{selected_types_html}</td></tr>
          <tr><td style="padding:6px 12px;background:#EEF2F4;font-weight:bold;">申請人信箱</td>
              <td style="padding:6px 12px;">{applicant_email}</td></tr>
        </table>
        <p style="color:#888;font-size:12px;margin-top:16px;">申請表 Word 檔已附件，請查收。</p>
        </body></html>
        """

        msg = MIMEMultipart("mixed")
        msg["Subject"] = f"【送審文件申請】{fields.get('apply_person','')} - {fields.get('customer','')}"
        msg["From"]    = f"證書查詢系統 <{gmail_user}>"
        msg["To"]      = recipient
        msg["Reply-To"] = applicant_email
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        part = MIMEBase("application", "vnd.openxmlformats-officedocument.wordprocessingml.document")
        part.set_payload(docx_bytes)
        encoders.encode_base64(part)
        filename = f"送審文件申請表_{fields.get('apply_person','')}_{today.strftime('%Y%m%d')}.docx"
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, [recipient], msg.as_string())
        return True
    except Exception as e:
        print(f"send_application_email error: {e}")
        return False

def build_confirm_message(app_data: dict) -> str:
    """產生確認摘要訊息"""
    type_names = {1: "商品驗證登錄證書", 2: "安規測試報告書", 3: "節能標章證書", 4: "能效分級標示圖示"}
    selected_types = "、".join(type_names[n] for n in sorted(app_data.get("doc_types", [])))
    if app_data.get("doc_other"):
        selected_types += f"、其他（{app_data['doc_other']}）"
    models_preview = "\n".join(f"  {m}" for m in app_data.get("models", []))
    return (
        "請確認以下申請資料是否正確：\n\n"
        f"・申請單位：{app_data.get('apply_unit','')}\n"
        f"・申請人：{app_data.get('apply_person','')}\n"
        f"・案件名稱：{app_data.get('apply_purpose','')}\n"
        f"・客戶名稱：{app_data.get('customer','')}\n"
        f"・需求機型：\n{models_preview}\n"
        f"・需要資料：{selected_types}\n\n"
        "以上資料是否有需要修改的地方？\n（回答「沒有」或「正確」將寄出申請表）"
    )

def handle_application_chat(user_input: str):
    """回傳 (reply: str, done: bool)"""
    step     = st.session_state["app_step"]
    app_data = st.session_state["app_data"]

    # 取消指令（任何階段都可取消）
    if any(kw in user_input for kw in ["取消", "cancel", "算了", "不申請"]):
        st.session_state["app_mode"]     = False
        st.session_state["app_step"]     = 0
        st.session_state["app_data"]     = {}
        st.session_state["app_confirmed"] = False
        return "好的，已取消申請。如需查詢證書請直接輸入型號或問題。", False

    # ── 確認階段 ─────────────────────────────────────────────────
    if step == CONFIRM_STEP:
        yes_kw = ["沒有", "正確", "是", "ok", "OK", "對", "寄出", "確認", "no", "沒"]
        if any(kw in user_input for kw in yes_kw):
            # 寄出
            try:
                docx_bytes = fill_application_docx(app_data)
                applicant_email = st.session_state.get("username", "")
                ok = send_application_email(app_data, docx_bytes, applicant_email)
                if ok:
                    log_application(applicant_email, app_data)
                st.session_state["app_mode"]      = False
                st.session_state["app_step"]      = 0
                st.session_state["app_data"]      = {}
                st.session_state["app_confirmed"] = False
                if ok:
                    return (
                        "✅ 申請表已寄出！\n\n"
                        f"已寄至 hungys@hotaidev.com.tw，"
                        f"回覆將發送至 {applicant_email}。"
                    ), True
                else:
                    return "⚠️ 申請表已填妥，但寄信時發生錯誤，請聯繫系統管理員。", True
            except Exception as e:
                st.session_state["app_mode"]      = False
                st.session_state["app_step"]      = 0
                st.session_state["app_data"]      = {}
                st.session_state["app_confirmed"] = False
                return f"⚠️ 產生申請表時發生錯誤：{e}", True
        else:
            # 有需要修改，重新從頭開始
            st.session_state["app_step"] = 0
            st.session_state["app_data"] = {}
            st.session_state["app_confirmed"] = False
            _, first_q = APPLICATION_FIELDS[0]
            return f"好的，我們重新填寫。\n\n{first_q}", False

    # ── 問答收集階段 ─────────────────────────────────────────────
    field_key = APPLICATION_FIELDS[step][0]

    if field_key == "models":
        import re as _re
        # 先嘗試換行分割，若整個輸入只有一行則改用空白分割
        lines = [m.strip() for m in user_input.strip().splitlines() if m.strip()]
        if len(lines) == 1:
            # 一行用空白或逗號分割
            lines = [m.strip() for m in _re.split(r"[\s,]+", lines[0]) if m.strip()]
        # 去除每個項目開頭的序號（如 "1." "10." "1、" 等）
        cleaned = []
        for m in lines:
            m = _re.sub(r"^\d+[\.、]\s*", "", m).strip()
            if m:
                cleaned.append(m)
        app_data["models"] = cleaned
    elif field_key == "doc_types":
        doc_types, doc_other = parse_doc_types(user_input)
        app_data["doc_types"] = doc_types
        app_data["doc_other"] = doc_other
    else:
        app_data[field_key] = user_input.strip()

    st.session_state["app_data"] = app_data
    st.session_state["app_step"] = step + 1
    next_step = step + 1

    if next_step < len(APPLICATION_FIELDS):
        _, next_question = APPLICATION_FIELDS[next_step]
        return next_question, False

    # 所有欄位收集完畢 → 進入確認階段
    st.session_state["app_step"] = CONFIRM_STEP
    return build_confirm_message(app_data), False

# ─────────────────────────────────────────────
# AI 對話 Sidebar
# ─────────────────────────────────────────────
def render_ai_chat():
    with st.expander("🤖 AI 查詢助理　點此展開 / 收合", expanded=False):
        st.caption("用自然語言查詢，或輸入「申請送審文件」申請各項證書副本")

        chat_area = st.container(height=300)
        with chat_area:
            for msg in st.session_state["ai_messages"]:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

        user_input = st.chat_input("輸入查詢問題…", key="ai_chat_input")

        if user_input and user_input.strip():
            q = user_input.strip()
            st.session_state["ai_messages"].append({"role": "user", "content": q})

            # 申請送審文件模式（包含確認階段）
            if st.session_state["app_mode"]:
                with st.spinner("處理中…"):
                    reply, done = handle_application_chat(q)
                st.session_state["ai_messages"].append({"role": "assistant", "content": reply})
                st.rerun()

            # 偵測申請觸發關鍵字
            elif is_application_trigger(q):
                st.session_state["app_mode"]      = True
                st.session_state["app_step"]      = 0
                st.session_state["app_data"]      = {}
                st.session_state["app_confirmed"] = False
                _, first_q = APPLICATION_FIELDS[0]
                intro = (
                    "好的，我來協助您填寫送審文件申請表。\n"
                    "填寫過程中隨時輸入「取消」可以中止。\n\n"
                    f"{first_q}"
                )
                st.session_state["ai_messages"].append({"role": "assistant", "content": intro})
                st.rerun()

            # 一般查詢模式
            else:
                with st.spinner("查詢中…"):
                    parsed = parse_query_with_ai(q)
                    execute_ai_query(parsed)
                    reply = parsed.get("reply", "已完成查詢。")
                    df_result = st.session_state.get("search_result")
                    total = len(df_result) if df_result is not None else 0
                    full_reply = f"{reply}\n\n共找到 **{total}** 筆資料。"

                st.session_state["ai_messages"].append({"role": "assistant", "content": full_reply})
                st.rerun()

# ─────────────────────────────────────────────
# 搜尋結果清單（白底莫蘭迪藍自訂元件）
# ─────────────────────────────────────────────
MORANDI_BLUE  = "#7B98A8"
MORANDI_PINK  = "#C79FA0"
MORANDI_GREEN = "#93A88C"

def render_results_list(result_df, title_field, meta_fields, s3_folder, keyword_field, doc_type_label, badge_text, widget_key, badge_color=MORANDI_BLUE):
    """
    統一的搜尋結果清單渲染：標題／分類／副資訊立刻全部顯示；右側「加入下載」欄位
    一筆一筆確認 S3 檔案是否存在，確認完就更新那一列的狀態——「無檔案」也會留在
    清單裡顯示，不是隱藏或延後到點擊才知道。

    （原本用 st.fragment 做局部重新整理，但在正式環境的 Streamlit 版本上
    st.rerun(scope="fragment") 會丟例外，所以改用一般的整頁重新整理，
    一次只查一筆再刷新，效果上一樣是逐筆補上結果，只是技術上更保守穩定。）

    meta_fields: [(label, field_name), ...]，顯示在標題下方的次要資訊
    """
    row_meta = []
    for i, (idx, row) in enumerate(result_df.iterrows()):
        keyword = str(row[keyword_field])
        meta_str = "　".join(f"{label}：{row[field]}" for label, field in meta_fields)
        row_meta.append({
            "row_id": i,
            "title": str(row[title_field]),
            "meta": meta_str,
            "keyword": keyword,
        })

    # 搜尋條件變了（同一個 widget_key 但資料列不同）就重置逐筆檢查的進度
    sig_key = f"row_sig_{widget_key}"
    status_key = f"row_status_{widget_key}"
    sig = tuple(r["keyword"] for r in row_meta)
    if st.session_state.get(sig_key) != sig:
        st.session_state[sig_key] = sig
        st.session_state[status_key] = {}
    statuses = st.session_state[status_key]  # {row_id: ("checking"/"available"/"unavailable", filename)}

    cart = st.session_state.get("download_cart", [])
    cart_keys = {item["dedup_key"] for item in cart}

    rows_payload = []
    for r in row_meta:
        i = r["row_id"]
        st_status, filename = statuses.get(i, ("checking", None))
        rows_payload.append({
            "row_id": i,
            "title": r["title"],
            "meta": r["meta"],
            "checking": st_status == "checking",
            "available": st_status != "unavailable",
            "added": bool(filename) and filename in cart_keys,
        })

    value = results_list(
        rows=rows_payload,
        badge_text=badge_text,
        badge_color=badge_color,
        key=widget_key,
    )

    if isinstance(value, dict) and value.get("action") == "add":
        nonce = value.get("nonce")
        nonce_state_key = f"last_results_nonce_{widget_key}"
        if nonce is not None and nonce != st.session_state.get(nonce_state_key):
            st.session_state[nonce_state_key] = nonce
            row_id = value.get("row_id")
            st_status, filename = statuses.get(row_id, (None, None))
            if st_status == "available" and filename:
                keyword = row_meta[row_id]["keyword"]
                cart.append({
                    "label": f"{doc_type_label}-{keyword}",
                    "doc_type": doc_type_label,
                    "folder": s3_folder,
                    "keyword": keyword,
                    "dedup_key": filename,
                })
                st.session_state["download_cart"] = cart
                st.rerun()

    # 逐筆確認下一筆還沒查過的資料，查完一筆就整頁重新整理，
    # 畫面上會看到「加入下載」欄位一筆一筆從「確認中…」變成「＋加入下載」或「無檔案」
    pending = [r["row_id"] for r in row_meta if r["row_id"] not in statuses]
    if pending:
        i = pending[0]
        keyword = row_meta[i]["keyword"]
        data, filename = find_and_download_s3(s3_folder, keyword)
        statuses[i] = ("available", filename) if data else ("unavailable", None)
        st.session_state[status_key] = statuses
        st.rerun()

# ─────────────────────────────────────────────
# 主查詢畫面
# ─────────────────────────────────────────────
def render_main():
    inject_css()

    st.markdown("""
    <div class="main-header">
      <h1>商品驗證登錄證書 &amp; 能效分級標示 查詢系統</h1>
    </div>
    """, unsafe_allow_html=True)

    col_space, col_user, col_logout = st.columns([7, 1.5, 1])
    with col_user:
        st.markdown(f'<div class="user-info">👤 {st.session_state.get("username","")}</div>', unsafe_allow_html=True)
    with col_logout:
        if st.button("登出", use_container_width=True):
            st.session_state["logged_in"]     = False
            st.session_state["username"]      = ""
            st.session_state["search_result"] = None
            st.session_state["ai_messages"]   = None
            st.session_state["app_mode"]      = False
            st.session_state["app_step"]      = 0
            st.session_state["app_data"]      = {}
            st.session_state["app_confirmed"] = False
            st.session_state["download_cart"] = []
            st.rerun()

    col_left, col_right = st.columns([1.15, 1])

    with col_left:
        with st.container(key="search_left_col"):
            default_type = st.session_state.get("search_query_type", "商品驗證登錄證書")
            type_options = ["商品驗證登錄證書", "能效分級標示", "節能標章證書"]
            default_idx  = type_options.index(default_type) if default_type in type_options else 0
            query_type = st.radio("查詢類型 *", type_options, index=default_idx, horizontal=True, key="query_type")

            sub1, sub2, sub3 = st.columns([1.7, 1, 0.9])
            with sub1:
                model_input = st.text_input("室外機型號", placeholder="例：RXQ8AYLT", key="model_input")
            with sub2:
                if query_type == "能效分級標示":
                    category = st.selectbox("類別", ["（全部）", "RA", "MA", "SA", "VRV", "空氣清淨機", "除濕機"], key="category")
                else:
                    category = st.selectbox("類別", ["（全部）", "RA", "MA", "SA", "VRV"], key="category")
            with sub3:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                search_clicked = st.button("🔍 搜尋", use_container_width=True, key="search_btn")

            wm_middle = render_apply_purpose_field()

    with col_right:
        render_download_data_panel(wm_middle, cart_height=176)

    if search_clicked:
        model_kw   = model_input.strip()
        cat_filter = None if category == "（全部）" else category
        result_subtype = "aircon"

        if query_type == "商品驗證登錄證書":
            with st.spinner("載入資料中…"):
                df = load_cert_data()
            result = df.copy()
            if model_kw:
                result = result[result["室外機型號"].astype(str).str.contains(model_kw, case=False, na=False)]
            if cat_filter:
                result = result[result["類別"].astype(str).str.contains(cat_filter, case=False, na=False)]

        elif query_type == "能效分級標示":
            with st.spinner("載入資料中…"):
                result, result_subtype = search_energy_label(model_kw, category)

        else:
            with st.spinner("載入資料中…"):
                df = load_energy_save_data()
            result = df.copy()
            if model_kw:
                result = result[
                    result["顯示型號"].astype(str).str.contains(model_kw, case=False, na=False) |
                    result["室外機型號"].astype(str).str.contains(model_kw, case=False, na=False)
                ]
            if cat_filter:
                result = result[result["類別"].astype(str).str.contains(cat_filter, case=False, na=False)]

        st.session_state["search_result"]         = result.reset_index(drop=True)
        st.session_state["search_query_type"]     = query_type
        st.session_state["search_result_subtype"] = result_subtype

    # AI 對話區塊（搜尋欄下方）－ 由頂部 AI_CHAT_ENABLED 常數控制顯示/隱藏
    if AI_CHAT_ENABLED:
        render_ai_chat()

    if st.session_state["search_result"] is None:
        return

    result     = st.session_state["search_result"]
    query_type = st.session_state["search_query_type"]
    subtype    = st.session_state.get("search_result_subtype", "aircon")
    total      = len(result)

    st.markdown(f'<div class="stat-bar"><div class="stat-card"><div class="num">{total}</div><div class="lbl">搜尋結果筆數</div></div></div>', unsafe_allow_html=True)

    if total == 0:
        st.info("查無符合條件的資料。")
        return

    if query_type == "商品驗證登錄證書":
        render_results_list(
            result,
            title_field="室外機型號",
            meta_fields=[("實驗室", "實驗室"), ("類別", "類別"), ("證書編號", "商品驗證登錄書編號"), ("有效期限", "證書有效期限")],
            s3_folder=S3_CERT_FOLDER,
            keyword_field="室外機型號",
            doc_type_label="商品驗證登錄證書",
            badge_text="商品驗證登錄證書",
            widget_key="results_cert",
        )

    elif query_type == "能效分級標示" and subtype == "air_purifier":
        render_results_list(
            result,
            title_field="型號",
            meta_fields=[("能源效率分級", "能源效率分級")],
            s3_folder=S3_AIR_PURIFIER_FOLDER,
            keyword_field="型號",
            doc_type_label="空氣清淨機能效分級",
            badge_text="能效分級－空氣清淨機",
            widget_key="results_air_purifier",
            badge_color=MORANDI_PINK,
        )

    elif query_type == "能效分級標示" and subtype == "dehumidifier":
        render_results_list(
            result,
            title_field="型號",
            meta_fields=[("能源效率分級", "能源效率分級")],
            s3_folder=S3_DEHUMIDIFIER_FOLDER,
            keyword_field="型號",
            doc_type_label="除濕機能效分級",
            badge_text="能效分級－除濕機",
            widget_key="results_dehumidifier",
            badge_color=MORANDI_PINK,
        )

    elif query_type == "能效分級標示":
        render_results_list(
            result,
            title_field="室外機型號",
            meta_fields=[("類別", "類別"), ("CSPF", "冷氣季節性能因數CSPF"), ("能源效率等級", "能源效率等級"), ("額定冷氣能力標示", "額定冷氣能力標示")],
            s3_folder=S3_ENERGY_FOLDER,
            keyword_field="室外機型號",
            doc_type_label="能效分級標示",
            badge_text="能效分級標示",
            widget_key="results_energy",
            badge_color=MORANDI_PINK,
        )

    else:
        render_results_list(
            result,
            title_field="顯示型號",
            meta_fields=[("類別", "類別"), ("節能標章證書編號", "節能標章證書編號"), ("有效日期", "節能標章有效日期")],
            s3_folder=S3_ENERGY_SAVE_FOLDER,
            keyword_field="顯示型號",
            doc_type_label="節能標章證書",
            badge_text="節能標章證書",
            widget_key="results_energysave",
            badge_color=MORANDI_GREEN,
        )



render = render_main
