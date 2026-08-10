import streamlit as st
import boto3
import anthropic
import json
import random
import string
import base64
import gspread
from google.oauth2.service_account import Credentials as GCredentials
from io import BytesIO
from datetime import datetime, timedelta
import fitz  # PyMuPDF，用於 PDF 轉圖片


# S3 資料夾名稱，必須跟查詢系統（cert-query-system）完全一致
CATEGORIES = {
    "I":   "I.Product verification login certifcate",
    "II":  "II.Safety Test Report",
    "III": "III.Energy-saving label certificate",
    "IV":  "IV.Energy efficiency logo",
}

CATEGORY_NAMES_ZH = {
    "I":   "商品驗證登錄證書",
    "II":  "安規測試報告書",
    "III": "節能標章證書",
    "IV":  "能效分級標示圖示",
}

S3_BUCKET = "cert-query-pdf"

# ─────────────────────────────────────────────
# Google Sheets - 資料來源設定
# 正式資料表：Total Certificate Management（與 cert-query-system 共用同一份）
# ─────────────────────────────────────────────
DATA_SHEET_ID       = "1hEt4uxBABBicxIMJuR57lMiigQYF02CQHZfB-Nc6vjo"  # Total Certificate Management
DATA_WORKSHEET_NAME = "工作表1"
DATA_START_ROW      = 3  # 前兩列非資料，從第三列開始（比照 cert-query-system 的 skiprows=2）

# 工作表2：能效分級標示圖示 - 空氣清淨機／除濕機（與工作表1 同一份試算表，另開分頁）
DATA_WORKSHEET2_NAME = "工作表2"
# G=型號  H=能源效率分級  I=登錄編號
# 空氣清淨機：J=CASR值  K=能源效率值(CASR/W)  L=待機功率
# 除濕機：    M=除濕能力  N=能源因數值

# Log 設定
LOG_SHEET_ID = "1nawjrMiI9zEtgzKVHvK9p6qsAZte66TFJF6E0bTO7ww"
LOG_SHEET_NAME = "操作紀錄"

# ─────────────────────────────────────────────
# Google Sheets Client / Log
# ─────────────────────────────────────────────
def get_gsheet_client():
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = GCredentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

def get_data_worksheet():
    """取得 Total Certificate Management／工作表1 的 worksheet 物件"""
    gc = get_gsheet_client()
    sh = gc.open_by_key(DATA_SHEET_ID)
    return sh.worksheet(DATA_WORKSHEET_NAME)

def get_data_worksheet2():
    """取得 Total Certificate Management／工作表2 的 worksheet 物件（空氣清淨機／除濕機能效分級）"""
    gc = get_gsheet_client()
    sh = gc.open_by_key(DATA_SHEET_ID)
    return sh.worksheet(DATA_WORKSHEET2_NAME)

def log_ocr_action(operator: str, filename: str, action: str, detail: str = ""):
    """
    寫入操作紀錄到 Google Sheets
    action: 上傳 / 修改 / 刪除
    detail: 額外說明（例如 S3 路徑、修改欄位等）
    """
    try:
        gc = get_gsheet_client()
        sh = gc.open_by_key(LOG_SHEET_ID)
        try:
            ws = sh.worksheet(LOG_SHEET_NAME)
        except Exception:
            ws = sh.add_worksheet(title=LOG_SHEET_NAME, rows=5000, cols=6)
            ws.append_row(["日期", "時間", "檔名", "操作人員", "操作內容", "備註"])

        now = datetime.now()
        ws.append_row([
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M:%S"),
            filename,
            operator,
            action,
            detail,
        ])
    except Exception as e:
        st.warning(f"⚠️ 操作紀錄寫入失敗：{e}")

# ─────────────────────────────────────────────
# Session State 初始化
# ─────────────────────────────────────────────
def init_session():
    defaults = {
        "logged_in":     False,
        "username":      "",
        "login_step":    "email",
        "login_email":   "",
        "otp_code":      "",
        "otp_expiry":    None,
        "ocr_results":   [],   # 辨識結果清單（每份 PDF 一筆）
        "uploaded_files_cache": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

# ─────────────────────────────────────────────
# Gmail SMTP 寄 OTP
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
        <h2 style="color:#1a3f6f;">【PDF 辨識歸檔系統】登入驗證碼</h2>
        <p>您的驗證碼為：</p>
        <h1 style="letter-spacing:8px;color:#1565c0;font-size:36px;">{code}</h1>
        <p>驗證碼有效時間為 <strong>5 分鐘</strong>，請盡快輸入。</p>
        </body></html>
        """
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "【PDF 辨識歸檔系統】登入驗證碼"
        msg["From"]    = f"PDF 辨識歸檔系統通知 <{gmail_user}>"
        msg["To"]      = email
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, email, msg.as_string())
        return True
    except Exception as e:
        st.error(f"寄信錯誤：{e}")
        return False

# ─────────────────────────────────────────────
# S3 工具
# ─────────────────────────────────────────────
def get_s3_client():
    return boto3.client(
        "s3",
        region_name           = st.secrets.get("S3_REGION", "ap-northeast-1"),
        aws_access_key_id     = st.secrets["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key = st.secrets["AWS_SECRET_ACCESS_KEY"],
    )

def upload_pdf_to_s3(file_bytes: bytes, s3_key: str) -> str:
    """上傳 PDF 到 S3（正式路徑，不加測試前綴），回傳 S3 key"""
    s3 = get_s3_client()
    s3.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=file_bytes, ContentType="application/pdf")
    return s3_key

def list_s3_subfolders(prefix: str) -> list:
    """列出 S3 某個 prefix 下的直接子資料夾名稱"""
    s3 = get_s3_client()
    prefix = prefix.rstrip("/") + "/"
    resp = s3.list_objects_v2(
        Bucket=S3_BUCKET, Prefix=prefix,
        Delimiter="/"
    )
    folders = []
    for cp in resp.get("CommonPrefixes", []):
        key = cp["Prefix"].rstrip("/")
        name = key.split("/")[-1]
        if name:
            folders.append(name)
    return sorted(folders)

def build_auto_filename(category: str, fields: dict, models: list) -> str:
    """依命名規則自動產生檔名（不含 .pdf）"""
    outdoor_models = list(dict.fromkeys(
        m.get("outdoor_model", "").strip()
        for m in models
        if m.get("outdoor_model", "").strip()
    ))
    models_str = " ".join(outdoor_models)

    if category == "I":
        cert_no = fields.get("cert_no", "").strip()
        return f"{cert_no}({models_str})" if models_str else cert_no
    elif category == "II":
        report_no = fields.get("report_no", "").strip()
        return f"測試報告-{models_str}" if models_str else report_no
    elif category == "III":
        energy_no = fields.get("energy_no", "").strip()
        return f"{energy_no}-節能標章證書{models_str}" if models_str else energy_no
    else:  # IV
        return models_str

# ─────────────────────────────────────────────
# PDF → 圖片（給 Claude vision 用）
# ─────────────────────────────────────────────
def pdf_to_images_base64(pdf_bytes: bytes, max_pages: int = 5, dpi: int = 150,
                          tail_pages: int = 0) -> list:
    """把 PDF 轉成 base64 圖片清單
    max_pages: 從頭讀幾頁
    tail_pages: 額外從尾端讀幾頁（不與前段重複）
    """
    images = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total = len(doc)
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)

    head_idx = list(range(min(total, max_pages)))
    if tail_pages > 0:
        tail_start = max(max_pages, total - tail_pages)
        tail_idx = list(range(tail_start, total))
    else:
        tail_idx = []

    for i in head_idx + tail_idx:
        page = doc[i]
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        images.append(b64)

    doc.close()
    return images

# ─────────────────────────────────────────────
# Claude API 辨識
# ─────────────────────────────────────────────
RECOGNITION_PROMPT = """你是冷氣設備證書辨識專家。請判斷這份 PDF 屬於以下四種類型的哪一種，並擷取對應欄位。

━━━━ 核心規則（非常重要）━━━━

【室外機決定列數】
- 每台「不同的室外機型號」對應 Excel 的一列
- 同一台室外機型號重複出現，只算一筆，不重複
- 一份證書有幾台不同室外機，models 陣列就有幾筆

【室內機填法】
- 每筆 model 的 "indoor_models" 欄位：填入該台室外機搭配的「所有室內機」，用「、」分隔
- 若所有室外機共用同一批室內機（系列型式附表），每筆的 indoor_models 填相同的完整清單
- 若室內機超過 20 台，仍請全部列出

【實驗室名稱標準化】只能填以下三者之一：
- "ETC"（台灣商品檢測驗證中心）
- "TERTEC"（台灣大電力研究試驗中心）
- "MIRDC"（金屬工業研究發展中心）

━━━━━━━━━━━━━━━━━━━━━

類型一【商品驗證登錄證書】欄位：
- lab：實驗室名稱（ETC / TERTEC / MIRDC）
- cert_no：商品驗證登錄書編號
- expire_date：證書有效期限（格式 YYYY-MM-DD）
- models：陣列，每個元素代表一台「不同的」室外機（不重複）：
  {
    "outdoor_model": "室外機型號",
    "indoor_models": "所有搭配室內機型號，用、分隔（含系列型式附表中的所有型號）"
  }
- unpaired_models：無法配對的型號（選填）

類型二【安規測試報告書】欄位：
- report_no：報告編號（ACT 或 ACS 開頭）
- models：陣列，每個元素代表一台室外機的測試數據（取無風管型數值）

━━━━ 安規報告附表格式說明（請逐張附表仔細閱讀）━━━━

表格中每行資料的格式通常是：
「型號 | 左欄數值（實測/量測）| 右欄數值（標示/額定）| 百分比% | 限制值 | 符合」

⚠ 左欄 = 實測值（actual），右欄 = 標示值（test）
⚠ 百分比 = 左欄/右欄 × 100%，通常在 90%~110% 之間
⚠ 用百分比欄位來驗證你取的左右欄是否正確

【5.1.1 附表：額定冷氣能力（無風管型，無「100Pa」字樣）】
欄位：型號 | 實測值(kW) | 標示值(kW) | 實測/標示(%) | 限制值
範例：室外機REYQ12BYLT/室內機FXFSQ50BVT×6 | 32.027 | 33.5 | 95.6 | 須≥95%
→ rated_capacity_actual = 32.027（左欄，較小的那個）
→ rated_capacity_test   = 33.5（右欄，較大的整數）

【5.1.2 附表：中間冷氣能力（無風管型）】
欄位：型號 | 實測值(kW) | 標示值(kW) | 實測/標示(%) | 限制值
範例：REYQ12BYLT/FXFSQ50BVT×6 | 14.520 | 15.1 | 96.2 | 須≥95%且≤105%
→ middle_capacity_actual = 14.520
→ middle_capacity_test   = 15.1

【5.2.1 附表：額定消耗功率（無風管型，無「100Pa」字樣）】
欄位：型號/條件 | 量測功率(W) | 額定功率(W) | 實測/標示(%) | 限制值
範例：REYQ12BYLT/FXFSQ50BVT×6 | 9961 | 9540 | 104.4 | 須≤110%
→ rated_power_actual = 9961（左欄「量測功率」= 實測值，單位W）
→ rated_power_test   = 9540（右欄「額定功率」= 標示值，單位W）
⚠ 注意：這裡左欄（實測）可能比右欄（標示）大，因為限制值是≤110%

【5.2.2 附表：中間消耗功率（無風管型）】
欄位：型號/條件 | 量測功率(W) | 額定功率(W) | 實測/標示(%) | 限制值
範例：REYQ12BYLT/FXFSQ50BVT×6 | 2851 | 2870 | 99.3 | 須≤110%
→ middle_power_actual = 2851（左欄「量測功率」）
→ middle_power_test   = 2870（右欄「額定功率」）

【5.14 附表：CSPF（無風管型）】
這張表格較複雜，包含 CSTL/CSEC 大數字（數萬），最後才是 CSPF 小數：
欄位：型號 | CSTL實測(kWh) | CSEC實測(kWh) | CSTL標示(kWh) | CSEC標示(kWh) | CSPF實測 | CSPF標示 | 標準值 | ...
範例：REYQ12BYLT/FXFSQ50BVT×6 | 38059.82 | 7426.73 | 39810.29 | 7403.69 | 5.12 | 5.38 | 3.40 | ...
→ cspf_actual = 5.12（「實測值」欄，通常在 3.0~7.0 之間）
→ cspf_test   = 5.38（「標示值」欄）
⚠ 忽略 CSTL/CSEC 那幾個大數字（萬位數），只取最後的 CSPF 小數

【數值格式規則】
- 完整保留小數（32.027 不可簡化為 32.0；14.520 必須保留為 "14.520"）
- 所有數值欄位請用「字串」格式回傳（加引號），例如 "14.520" 而不是 14.52
- 消耗功率單位固定為 W（整數，例如 "9961"）
- CSPF 通常在 3.0～7.0 之間

models 陣列格式：
[{
  "outdoor_model": "室外機型號",
  "rated_capacity_actual": "5.1.1無風管實測kW",
  "rated_capacity_test": "5.1.1標示kW",
  "rated_capacity_pct": "5.1.1表格中的實測/標示(%)欄數值，例如 95.6",
  "middle_capacity_actual": "5.1.2無風管實測kW",
  "middle_capacity_test": "5.1.2標示kW",
  "middle_capacity_pct": "5.1.2表格中的實測/標示(%)欄數值，例如 96.2",
  "rated_power_actual": "5.2.1無風管量測功率W",
  "rated_power_test": "5.2.1額定功率W",
  "rated_power_pct": "5.2.1表格中的實測/標示(%)欄數值，例如 104.4",
  "middle_power_actual": "5.2.2無風管量測功率W",
  "middle_power_test": "5.2.2額定功率W",
  "middle_power_pct": "5.2.2表格中的實測/標示(%)欄數值，例如 99.3",
  "cspf_actual": "5.14無風管實測CSPF",
  "cspf_test": "5.14標示CSPF",
  "cspf_pct": "5.14表格中的實測值/標示值(%)欄數值，例如 95.2"
}]

類型三【節能標章證書】欄位：
- energy_no：節能標章證書編號
- valid_date：有效日期（格式 YYYY-MM-DD）
- models：陣列，每個元素為：
  {"outdoor_model": "室外機型號", "indoor_models": "搭配室內機，用、分隔"}

類型四【能效分級標示圖示】欄位：
先看圖示上的「名稱」欄位，判斷 product_type 是「冷氣機」「空氣清淨機」還是「除濕機」，再依類型擷取對應欄位。

- product_type："冷氣機" 或 "空氣清淨機" 或 "除濕機"（依圖示「名稱」欄位判斷）
- reg_no：登錄編號（圖示上「登錄編號」欄位的完整文字）
- models：陣列，每個元素依 product_type 不同，欄位如下（型號一律填在 outdoor_model）：

  若 product_type = "冷氣機"：
  {
    "outdoor_model": "室外機型號",
    "level": "能源效率等級（數字1~5）",
    "rated_capacity": "額定冷氣能力（kW，圖示上的數值，例如 7.2）",
    "cspf": "CSPF 冷氣季節性能因數（kWh/kWh，圖示上的數值，例如 5.75）"
  }

  若 product_type = "空氣清淨機"：
  {
    "outdoor_model": "型號",
    "level": "能源效率等級（數字1~5）",
    "casr": "CASR值（cmm，例如 2.77）",
    "casr_per_w": "能源效率值 CASR/W（cmm/W，例如 0.121）",
    "standby_power": "待機功率（W，例如 1.00）"
  }

  若 product_type = "除濕機"：
  {
    "outdoor_model": "型號",
    "level": "能源效率等級（數字1~5）",
    "dehumid_capacity": "額定除濕能力（公升/日，例如 12.0）",
    "energy_factor": "能源因數值（公升/千瓦小時，例如 2.57）"
  }

【JSON 格式鐵則（非常重要，違反會導致系統無法解析）】
- note 欄位務必簡短，20字以內，只寫「有疑慮」或「需人工複查」等提示語，絕對不要重新描述證書內容或型號清單
- 所有文字欄位內絕對不可出現英文雙引號 "，如需引用文字請改用「」（中文引號）
- 絕對不可在 JSON 之外加註解、說明文字，也不可使用換行符號 \\n 以外的跳脫符號

請只回傳 JSON，不要其他文字：
{
  "category": "I" 或 "II" 或 "III" 或 "IV",
  "category_name": "對應的中文類型名稱",
  "confidence": "high" 或 "medium" 或 "low",
  "fields": { 依類型填入對應欄位 },
  "note": "辨識備註（20字以內）"
}"""

def recognize_pdf_with_claude(pdf_bytes: bytes, filename: str) -> dict:
    """呼叫 Claude API 辨識 PDF 內容
    策略：
    - 第一次：讀前3頁，判斷證書類型
    - 若為安規測試報告書（II）：補讀後10頁，進行完整辨識
    - 其他類型：讀前5頁完整辨識
    """
    try:
        client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

        QUICK_PROMPT = """請判斷這份 PDF 是以下哪種類型，並擷取基本資訊（只回傳 JSON，不要其他文字）：
{
  "category": "I" 或 "II" 或 "III" 或 "IV" 或 "unknown",
  "lab": "ETC 或 TERTEC 或 MIRDC",
  "report_no": "報告編號（ACT或ACS開頭，安規報告才有，否則填空字串）",
  "outdoor_model": "室外機型號（主型號，否則填空字串）"
}
I=商品驗證登錄證書, II=安規測試報告書, III=節能標章證書, IV=能效分級標示圖示"""

        quick_images = pdf_to_images_base64(pdf_bytes, max_pages=3)
        if not quick_images:
            return {"error": "PDF 無法轉換為圖片", "filename": filename}

        quick_content = [{"type": "text", "text": QUICK_PROMPT}]
        for b64 in quick_images:
            quick_content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": b64}
            })

        quick_resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=256,
            messages=[{"role": "user", "content": quick_content}]
        )
        quick_text = quick_resp.content[0].text.strip()
        try:
            import json as _json
            if quick_text.startswith("```"):
                quick_text = quick_text.split("```")[1]
                if quick_text.startswith("json"):
                    quick_text = quick_text[4:]
            quick_result = _json.loads(quick_text.strip())
            detected_category = quick_result.get("category", "unknown")
            quick_report_no   = quick_result.get("report_no", "")
            quick_outdoor     = quick_result.get("outdoor_model", "")
            quick_lab         = quick_result.get("lab", "")
        except Exception:
            detected_category = "unknown"
            quick_report_no = quick_outdoor = quick_lab = ""

        if detected_category == "II":
            images_b64 = pdf_to_images_base64(pdf_bytes, max_pages=3, tail_pages=15, dpi=250)
        else:
            images_b64 = pdf_to_images_base64(pdf_bytes, max_pages=5)

        if not images_b64:
            return {"error": "PDF 無法轉換為圖片", "filename": filename}

        extra_context = ""
        if detected_category == "II" and (quick_report_no or quick_outdoor):
            extra_context = f"\n\n【封面已確認的資訊，請直接填入 report_no 和 outdoor_model】\n報告編號：{quick_report_no}\n室外機型號：{quick_outdoor}\n實驗室：{quick_lab}\n以下圖片為報告後段附表頁面，請擷取各附表的實測值和標示值。"

        prompt_text = RECOGNITION_PROMPT + extra_context
        content_msg = [{"type": "text", "text": prompt_text}]
        for b64 in images_b64:
            content_msg.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": b64}
            })

        max_out = 8192 if detected_category == "II" else 4096
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_out,
            messages=[{"role": "user", "content": content_msg}]
        )

        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        def try_repair_json(t):
            s1, s2, s3 = '"}}', '"]}', '"]}}'
            for suffix in ["}", "}}", "]}", "]}}", s1, s2, s3]:
                try:
                    return json.loads(t + suffix)
                except json.JSONDecodeError:
                    pass
            for marker in ['"]}}'+ ",", '"]}' + "},"]:
                idx = t.rfind(marker)
                if idx > 0:
                    for ending in [' "note": ""}', "}"]:
                        try:
                            return json.loads(t[:idx + len(marker)] + ending)
                        except json.JSONDecodeError:
                            pass
            for i in range(len(t) - 1, max(0, len(t) - 300), -1):
                if t[i] in ('}', ']'):
                    for suffix in ["}", "}}", "]}}"]:
                        try:
                            return json.loads(t[:i+1] + suffix)
                        except json.JSONDecodeError:
                            pass
            return None

        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            repaired = try_repair_json(text)
            if repaired is None:
                return {"error": f"JSON 解析失敗（可能回傳被截斷）：{text[-150:]}", "filename": filename}
            result = repaired

        if result.get("category") not in ("I", "II", "III", "IV"):
            return {
                "error": f"無法辨識證書類型（回傳值：{result.get('category')}）",
                "filename": filename,
            }

        result["filename"] = filename
        result["pdf_bytes"] = pdf_bytes
        return result

    except Exception as e:
        return {"error": str(e), "filename": filename}

# ─────────────────────────────────────────────
# Google Sheets 寫入邏輯（比照原 openpyxl 欄位對應）
# ─────────────────────────────────────────────
UNPAIRED_MODEL_COL = "AL"
SHEET_MIN_COLS = 40  # 涵蓋到 AL 欄，多留一些緩衝

# 型號前綴 → 類別（RA/SA/MA/VRV）
_CATEGORY_PREFIX_MAP = {
    "REYQ": "VRV", "RXYQ": "VRV", "RXYCQ": "VRV", "RXYSQ": "VRV",
    "RQYQ": "VRV", "RSUYQ": "VRV", "RWEYQ": "VRV",
    "2MXM": "MA",  "3MXM": "MA",  "4MXM": "MA",  "5MXM": "MA",
    "RXYMQ": "MA",
    "RXQ":  "SA",
    "RXV": "RA", "RXM": "RA", "RXS": "RA", "RXK": "RA", "RXJ": "RA",
    "RXP": "RA", "RXN": "RA", "RXL": "RA", "RHF": "RA", "RZF": "RA",
    "RZAC": "RA", "RZAG": "RA", "RZAS": "RA", "RKF": "RA",
}

def classify_outdoor_model(model: str) -> str:
    """依室外機型號前綴判斷 RA/SA/MA/VRV 類別"""
    if not model:
        return ""
    m = model.upper().strip()
    for prefix in sorted(_CATEGORY_PREFIX_MAP.keys(), key=len, reverse=True):
        if m.startswith(prefix):
            return _CATEGORY_PREFIX_MAP[prefix]
    return ""

def _col_idx0(letter: str) -> int:
    """欄位字母轉 0-based index，A -> 0, B -> 1, ..., AH -> 33"""
    idx = 0
    for ch in letter:
        idx = idx * 26 + (ord(ch.upper()) - ord("A") + 1)
    return idx - 1

def _pad_row(row, min_len=SHEET_MIN_COLS):
    if len(row) < min_len:
        row = row + [""] * (min_len - len(row))
    return row

def find_row_by_outdoor_model(values, outdoor_model, search_cols=("C", "O")):
    """在記憶體中的 values（list of list）搜尋室外機型號所在列，回傳 1-based 列號"""
    if not outdoor_model:
        return None
    col_idxs = [_col_idx0(c) for c in search_cols]
    for i, row in enumerate(values):
        row_num = i + 1
        if row_num < DATA_START_ROW:
            continue
        for ci in col_idxs:
            val = row[ci] if ci < len(row) else ""
            if str(val).strip() == str(outdoor_model).strip():
                return row_num
    return None

def find_next_empty_row(values, check_columns, start_row=DATA_START_ROW):
    col_idxs = [_col_idx0(c) for c in check_columns]
    row_num = start_row
    while True:
        idx = row_num - 1
        if idx >= len(values):
            return row_num
        row = values[idx]
        if all((row[ci] if ci < len(row) else "") in ("", None) for ci in col_idxs):
            return row_num
        row_num += 1

def get_or_create_row(values, outdoor_model):
    row = find_row_by_outdoor_model(values, outdoor_model)
    if row:
        return row
    row = find_next_empty_row(values, ["C", "O"])
    while len(values) < row:
        values.append([""] * SHEET_MIN_COLS)
    return row

SHEET2_MIN_COLS = 20  # 工作表2 欄位只用到 N（14），留些緩衝

def get_or_create_row_sheet2(values2, model):
    """工作表2 專用：依 G 欄（型號）查找或建立新列"""
    row = find_row_by_outdoor_model(values2, model, search_cols=("G",))
    if row:
        return row
    row = find_next_empty_row(values2, ["G"])
    while len(values2) < row:
        values2.append([""] * SHEET2_MIN_COLS)
    return row

def safe_set_cell(values, pending_updates, col_letter, row, value):
    """在記憶體 values 中更新欄位，並記錄到 pending_updates 供之後批次寫入"""
    if value in [None, ""]:
        return
    col_idx = _col_idx0(col_letter)
    while len(values) < row:
        values.append([""] * SHEET_MIN_COLS)
    if len(values[row - 1]) <= col_idx:
        values[row - 1] = values[row - 1] + [""] * (col_idx + 1 - len(values[row - 1]))
    values[row - 1][col_idx] = str(value)
    pending_updates[f"{col_letter}{row}"] = str(value)

def set_cell_with_highlight(values, pending_updates, pending_formats, col_letter, row, new_value):
    """寫入欄位，若新舊值不同則標記需要紅字提醒（用於類型 IV 的 AF/AK 欄）"""
    new_value = str(new_value).strip() if new_value not in [None, ""] else ""
    if not new_value:
        return
    col_idx = _col_idx0(col_letter)
    existing = ""
    if row - 1 < len(values) and col_idx < len(values[row - 1]):
        existing = str(values[row - 1][col_idx] or "").strip()

    safe_set_cell(values, pending_updates, col_letter, row, new_value)

    if existing and existing != new_value:
        pending_formats.append(f"{col_letter}{row}")

def write_one_row(values, pending_updates, pending_formats, category: str, fields: dict, model_item: dict) -> int:
    """寫入單一外機型號的一列資料（更新記憶體 values + 累積 pending_updates）"""
    outdoor = model_item.get("outdoor_model", "")

    if category == "I":
        row = get_or_create_row(values, outdoor) if outdoor else find_next_empty_row(
            values, ["A", "C", "D", "F", "G", UNPAIRED_MODEL_COL]
        )
        safe_set_cell(values, pending_updates, "A", row, fields.get("lab", ""))
        safe_set_cell(values, pending_updates, "B", row, classify_outdoor_model(outdoor))
        safe_set_cell(values, pending_updates, "C", row, outdoor)
        indoor_all = model_item.get("indoor_models", model_item.get("indoor_model", ""))
        if indoor_all:
            parts = [x.strip() for x in str(indoor_all).replace("，", "、").replace(",", "、").split("、") if x.strip()]
            safe_set_cell(values, pending_updates, "D", row, parts[0] if parts else "")
            if len(parts) > 1:
                safe_set_cell(values, pending_updates, "AJ", row, "、".join(parts[1:]))
        safe_set_cell(values, pending_updates, "F", row, fields.get("cert_no", ""))
        safe_set_cell(values, pending_updates, "G", row, fields.get("expire_date", ""))
        safe_set_cell(values, pending_updates, UNPAIRED_MODEL_COL, row, fields.get("unpaired_models", ""))

    elif category == "II":
        row = get_or_create_row(values, outdoor)
        safe_set_cell(values, pending_updates, "B", row, classify_outdoor_model(outdoor))
        safe_set_cell(values, pending_updates, "C", row, outdoor)
        safe_set_cell(values, pending_updates, "N", row, fields.get("report_no", ""))
        safe_set_cell(values, pending_updates, "O", row, outdoor)
        mapping = {
            "P": "rated_capacity_actual",  "Q": "rated_capacity_test",
            "R": "middle_capacity_actual", "S": "middle_capacity_test",
            "T": "rated_power_actual",     "U": "rated_power_test",
            "V": "middle_power_actual",    "W": "middle_power_test",
            "X": "cspf_actual",            "Y": "cspf_test",
        }
        for col, key in mapping.items():
            safe_set_cell(values, pending_updates, col, row, model_item.get(key, ""))

    elif category == "III":
        row = get_or_create_row(values, outdoor)
        safe_set_cell(values, pending_updates, "B", row, classify_outdoor_model(outdoor))
        safe_set_cell(values, pending_updates, "C", row, outdoor)
        safe_set_cell(values, pending_updates, "O", row, outdoor)
        safe_set_cell(values, pending_updates, "AC", row, fields.get("energy_no", ""))
        safe_set_cell(values, pending_updates, "AD", row, fields.get("valid_date", ""))
        safe_set_cell(values, pending_updates, "AE", row, outdoor)

    else:  # IV
        row = get_or_create_row(values, outdoor)
        safe_set_cell(values, pending_updates, "B", row, classify_outdoor_model(outdoor))
        safe_set_cell(values, pending_updates, "C", row, outdoor)
        safe_set_cell(values, pending_updates, "O", row, outdoor)
        safe_set_cell(values, pending_updates, "AG", row, model_item.get("level", ""))
        safe_set_cell(values, pending_updates, "AH", row, outdoor)
        safe_set_cell(values, pending_updates, "AI", row, fields.get("reg_no", ""))

        # AF：額定冷氣能力，AK：CSPF —— 新舊值不同時標記紅字提醒
        new_cap  = str(model_item.get("rated_capacity", "")).strip()
        new_cspf = str(model_item.get("cspf", "")).strip()
        set_cell_with_highlight(values, pending_updates, pending_formats, "AF", row, new_cap)
        set_cell_with_highlight(values, pending_updates, pending_formats, "AK", row, new_cspf)

    return row

def write_one_row_sheet2(values2, pending_updates2, product_type: str, fields: dict, model_item: dict) -> int:
    """寫入工作表2 單一列（空氣清淨機／除濕機能效分級）"""
    model = model_item.get("outdoor_model", "")
    row = get_or_create_row_sheet2(values2, model)

    safe_set_cell(values2, pending_updates2, "G", row, model)
    safe_set_cell(values2, pending_updates2, "H", row, model_item.get("level", ""))
    safe_set_cell(values2, pending_updates2, "I", row, fields.get("reg_no", ""))

    if product_type == "空氣清淨機":
        safe_set_cell(values2, pending_updates2, "J", row, model_item.get("casr", ""))
        safe_set_cell(values2, pending_updates2, "K", row, model_item.get("casr_per_w", ""))
        safe_set_cell(values2, pending_updates2, "L", row, model_item.get("standby_power", ""))
    elif product_type == "除濕機":
        safe_set_cell(values2, pending_updates2, "M", row, model_item.get("dehumid_capacity", ""))
        safe_set_cell(values2, pending_updates2, "N", row, model_item.get("energy_factor", ""))

    return row

def write_all_rows(values, pending_updates, pending_formats, values2, pending_updates2,
                    category: str, fields: dict) -> list:
    """
    寫入一份 PDF 的所有列（一個型號一列）
    回傳寫入的 (row, model_name, sheet_tag) 清單，sheet_tag 為 "sheet1" 或 "sheet2"
    """
    # 類型 IV 的空氣清淨機／除濕機寫到工作表2，其餘（含冷氣機）維持寫工作表1
    product_type = fields.get("product_type", "冷氣機") if category == "IV" else None

    if category == "IV" and product_type in ("空氣清淨機", "除濕機"):
        models = fields.get("models", [])
        if not models:
            single_defs = {
                "空氣清淨機": ["casr", "casr_per_w", "standby_power"],
                "除濕機": ["dehumid_capacity", "energy_factor"],
            }[product_type]
            single = {"outdoor_model": fields.get("outdoor_model", ""), "level": fields.get("level", "")}
            for k in single_defs:
                single[k] = fields.get(k, "")
            models = [single]

        rows = []
        for model_item in models:
            if not model_item.get("outdoor_model"):
                continue
            row = write_one_row_sheet2(values2, pending_updates2, product_type, fields, model_item)
            rows.append((row, model_item.get("outdoor_model", ""), "sheet2"))
        return rows

    models = fields.get("models", [])

    if not models:
        single = {"outdoor_model": fields.get("outdoor_model", "")}
        if category == "I":
            single["indoor_model"] = fields.get("indoor_model", "")
        elif category == "IV":
            single["level"] = fields.get("level", "")
        models = [single]

    rows = []
    for model_item in models:
        if not model_item.get("outdoor_model"):
            continue
        row = write_one_row(values, pending_updates, pending_formats, category, fields, model_item)
        rows.append((row, model_item.get("outdoor_model", ""), "sheet1"))

    return rows

def commit_updates_to_sheet(ws, pending_updates: dict, pending_formats: list):
    """把累積的變更一次性寫入 Google Sheets（單一 batch_update API 呼叫）＋設定紅字格式"""
    if pending_updates:
        batch_data = [
            {"range": addr, "values": [[val]]}
            for addr, val in pending_updates.items()
        ]
        ws.batch_update(batch_data, value_input_option="USER_ENTERED")

    for addr in pending_formats:
        ws.format(addr, {
            "textFormat": {
                "foregroundColor": {"red": 1, "green": 0, "blue": 0},
                "bold": True,
            }
        })

# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────
def inject_css():
    st.markdown("""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@300;400;500;700&display=swap');
      html, body, [class*="css"] { font-family: 'Noto Sans TC', sans-serif; }
      #MainMenu, footer, header, [data-testid="stHeader"], [data-testid="stToolbar"] { display: none !important; }
      .main-header {
        background: linear-gradient(135deg, #0f2744 0%, #1a3f6f 60%, #1565c0 100%);
        color: #fff; padding: 1.4rem 2.2rem 1.1rem; border-radius: 0 0 16px 16px; margin-bottom: 1rem;
      }
      .main-header h1 { font-size: 1.4rem; font-weight: 700; margin: 0; }
      .cat-badge { display:inline-block; padding:.15rem .55rem; border-radius:14px; font-size:.78rem; font-weight:600; }
      .cat-I   { background:#e3f0ff; color:#1565c0; }
      .cat-II  { background:#e8f5e9; color:#2e7d32; }
      .cat-III { background:#fff3e0; color:#e65100; }
      .cat-IV  { background:#fbe9f1; color:#993556; }
      .conf-high   { color:#2e7d32; font-weight:600; }
      .conf-medium { color:#e65100; font-weight:600; }
      .conf-low    { color:#c62828; font-weight:600; }
    </style>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────
# 主畫面
# ─────────────────────────────────────────────
def render_main():
    init_session()
    inject_css()

    st.markdown("""
    <div class="main-header"><h1>🗂️ PDF 辨識歸檔系統</h1></div>
    """, unsafe_allow_html=True)

    st.caption(f"辨識結果將寫入正式資料表「Total Certificate Management／{DATA_WORKSHEET_NAME}」，PDF 將上傳至正式 S3 資料夾。")

    col_sp, col_user, col_logout = st.columns([7, 1.5, 1])
    with col_user:
        st.markdown(f"👤 {st.session_state.get('username','')}")
    with col_logout:
        if st.button("登出", use_container_width=True):
            st.session_state["logged_in"]   = False
            st.session_state["username"]    = ""
            st.session_state["ocr_results"] = []
            st.rerun()

    st.subheader("第一步：上傳 PDF（可多份）")
    uploaded_files = st.file_uploader(
        "請選擇要辨識的證書 PDF",
        type=["pdf"],
        accept_multiple_files=True,
    )

    if uploaded_files and st.button("🔍 開始批次辨識", use_container_width=True):
        files_data = [(f.name, f.getvalue()) for f in uploaded_files]

        results = []
        progress = st.progress(0)
        status = st.empty()

        for i, (fname, pdf_bytes) in enumerate(files_data):
            status.caption(f"辨識中：{fname}（{i+1}/{len(files_data)}）")
            result = recognize_pdf_with_claude(pdf_bytes, fname)
            results.append(result)
            progress.progress((i + 1) / len(files_data))

        status.caption("✅ 辨識完成")
        st.session_state["ocr_results"] = results
        st.rerun()

    # ── 顯示辨識結果並可編輯確認 ──────────────────────────
    if st.session_state["ocr_results"]:
        st.divider()
        col_title, col_clear = st.columns([5, 1])
        with col_title:
            st.subheader("第二步：確認辨識結果")
        with col_clear:
            if st.button("🗑️ 清除全部", use_container_width=True):
                st.session_state["ocr_results"] = []
                st.rerun()

        confirmed_data = []

        for idx, r in enumerate(st.session_state["ocr_results"]):
            if "error" in r:
                st.error(f"❌ {r['filename']}：{r['error']}")
                continue

            cat = r.get("category", "")
            if cat not in ("I", "II", "III", "IV"):
                st.error(f"❌ {r.get('filename','未知檔案')}：辨識結果類型異常，請略過或重新上傳")
                continue

            cat_name = r.get("category_name", CATEGORY_NAMES_ZH.get(cat, "未知"))
            conf = r.get("confidence", "low")
            if conf not in ("high", "medium", "low"):
                conf = "low"
            fields = r.get("fields", {})

            with st.expander(f"📄 {r['filename']}　{cat_name}　（共 {len(fields.get('models', []))} 台外機）", expanded=True):
                col_a, col_b, col_c = st.columns([1.5, 1.5, 1])
                with col_a:
                    cat_options = ["I", "II", "III", "IV"]
                    cat_idx = cat_options.index(cat) if cat in cat_options else 0
                    corrected_cat = st.selectbox(
                        "證書類型（如辨識錯誤可手動修正）",
                        cat_options,
                        index=cat_idx,
                        format_func=lambda c: f"{c}. {CATEGORY_NAMES_ZH[c]}",
                        key=f"cat_select_{idx}",
                    )
                with col_b:
                    st.markdown(f'<span class="conf-{conf}">信心度：{conf}</span>', unsafe_allow_html=True)
                with col_c:
                    skip_this = st.checkbox("跳過此份", key=f"skip_{idx}")

                product_type = fields.get("product_type", "冷氣機")
                if corrected_cat == "IV":
                    pt_options = ["冷氣機", "空氣清淨機", "除濕機"]
                    pt_idx = pt_options.index(product_type) if product_type in pt_options else 0
                    product_type = st.selectbox(
                        "產品類型（能效分級標示圖示，如辨識錯誤可手動修正）",
                        pt_options,
                        index=pt_idx,
                        key=f"product_type_{idx}",
                    )
                    st.caption(
                        "冷氣機 → 寫入工作表1；空氣清淨機／除濕機 → 寫入工作表2"
                    )

                if r.get("note"):
                    st.caption(f"備註：{r['note']}")

                if skip_this:
                    st.info("此份已標記跳過，不會被歸檔")
                    continue

                edited_fields = {}
                if corrected_cat == "IV" and product_type != "冷氣機":
                    common_field_defs_iv = [("reg_no", "登錄編號")]
                else:
                    common_field_defs_iv = [("reg_no", "能效登錄編號")]

                common_field_defs = {
                    "I":   [("lab", "實驗室"), ("cert_no", "商品驗證登錄證書編號"), ("expire_date", "證書有效期限"), ("unpaired_models", "未配對型號")],
                    "II":  [("report_no", "安規報告編號")],
                    "III": [("energy_no", "節能標章證書編號"), ("valid_date", "節能標章有效日期")],
                    "IV":  common_field_defs_iv,
                }
                edited_fields["product_type"] = product_type
                st.markdown("**證書層級共用資訊**")
                common_cols = st.columns(2)
                for i, (key, label) in enumerate(common_field_defs.get(corrected_cat, [])):
                    with common_cols[i % 2]:
                        val = fields.get(key, "")
                        edited_fields[key] = st.text_input(label, value=str(val) if val else "", key=f"common_{idx}_{key}")

                model_label = "型號清單" if (corrected_cat == "IV" and product_type != "冷氣機") else "外機型號清單"
                st.markdown(f"**{model_label}**（一個型號一列，會各自寫入一列）")
                models = fields.get("models", [])
                if not models:
                    single = {"outdoor_model": fields.get("outdoor_model", ""), "level": fields.get("level", "")}
                    if corrected_cat == "I":
                        single["indoor_model"] = fields.get("indoor_model", "")
                    models = [single]

                model_field_defs_iv = {
                    "冷氣機":     [("outdoor_model", "室外機型號"), ("level", "能源效率等級"), ("rated_capacity", "額定冷氣能力(kW)→AF欄"), ("cspf", "CSPF→AK欄")],
                    "空氣清淨機": [("outdoor_model", "型號"), ("level", "能源效率等級"), ("casr", "CASR值→J欄"), ("casr_per_w", "能源效率值CASR/W→K欄"), ("standby_power", "待機功率→L欄")],
                    "除濕機":     [("outdoor_model", "型號"), ("level", "能源效率等級"), ("dehumid_capacity", "除濕能力→M欄"), ("energy_factor", "能源因數值→N欄")],
                }

                model_field_defs = {
                    "I":   [("outdoor_model", "室外機型號"), ("indoor_models", "室內機型號（多台用、分隔；第1台→D欄，其餘→AJ欄）")],
                    "II":  [
                        ("outdoor_model", "室外機型號"),
                        ("rated_capacity_actual", "額定冷氣能力(實測)"), ("rated_capacity_test", "額定冷氣能力(標示)"),
                        ("middle_capacity_actual", "中間冷氣能力(實測)"), ("middle_capacity_test", "中間冷氣能力(標示)"),
                        ("rated_power_actual", "額定消耗功率(實測)"), ("rated_power_test", "額定消耗功率(標示)"),
                        ("middle_power_actual", "中間消耗功率(實測)"), ("middle_power_test", "中間消耗功率(標示)"),
                        ("cspf_actual", "CSPF(實測)"), ("cspf_test", "CSPF(標示)"),
                    ],
                    "III": [("outdoor_model", "室外機型號"), ("indoor_models", "搭配室內機（多台用、分隔）")],
                    "IV":  model_field_defs_iv.get(product_type, model_field_defs_iv["冷氣機"]),
                }

                edited_models = []
                for m_idx, model_item in enumerate(models):
                    st.caption(f"— 第 {m_idx + 1} 台 —")
                    edited_model = {}

                    if corrected_cat == "II":
                        edited_model["outdoor_model"] = st.text_input(
                            "室外機型號",
                            value=str(model_item.get("outdoor_model", "")),
                            key=f"model_{idx}_{m_idx}_outdoor_model"
                        )

                        pair_defs = [
                            ("rated_capacity_actual",  "rated_capacity_test",  "rated_capacity_pct",  "額定冷氣能力(kW)"),
                            ("middle_capacity_actual", "middle_capacity_test", "middle_capacity_pct", "中間冷氣能力(kW)"),
                            ("rated_power_actual",     "rated_power_test",     "rated_power_pct",     "額定消耗功率(W)"),
                            ("middle_power_actual",    "middle_power_test",    "middle_power_pct",    "中間消耗功率(W)"),
                            ("cspf_actual",            "cspf_test",            "cspf_pct",            "CSPF"),
                        ]
                        for act_key, test_key, pct_key, label in pair_defs:
                            col_act, col_test, col_pct = st.columns(3)
                            with col_act:
                                act_val = str(model_item.get(act_key, ""))
                                edited_model[act_key] = st.text_input(
                                    f"{label} 實測",
                                    value=act_val,
                                    key=f"model_{idx}_{m_idx}_{act_key}"
                                )
                            with col_test:
                                test_val = str(model_item.get(test_key, ""))
                                edited_model[test_key] = st.text_input(
                                    f"{label} 標示",
                                    value=test_val,
                                    key=f"model_{idx}_{m_idx}_{test_key}"
                                )
                            with col_pct:
                                try:
                                    av = float(edited_model[act_key])
                                    tv = float(edited_model[test_key])
                                    calc_pct = av / tv * 100 if tv else 0
                                    pdf_pct_str = str(model_item.get(pct_key, "")).strip()
                                    calc_str = f"{calc_pct:.1f}"

                                    if pdf_pct_str:
                                        try:
                                            pdf_pct = float(pdf_pct_str)
                                            match = abs(calc_pct - pdf_pct) <= 0.5
                                            icon = "✅" if match else "⚠️"
                                            display = f"{icon} {calc_str}% (PDF:{pdf_pct_str}%)"
                                        except ValueError:
                                            display = f"計算:{calc_str}%"
                                    else:
                                        display = f"{calc_str}%"
                                    st.text_input("驗算%", value=display, key=f"pct_{idx}_{m_idx}_{act_key}", disabled=True)
                                except (ValueError, ZeroDivisionError):
                                    st.text_input("驗算%", value="—", key=f"pct_{idx}_{m_idx}_{act_key}", disabled=True)
                    else:
                        m_cols = st.columns(2)
                        for i, (key, label) in enumerate(model_field_defs.get(corrected_cat, [])):
                            with m_cols[i % 2]:
                                val = model_item.get(key, "")
                                edited_model[key] = st.text_input(
                                    label, value=str(val) if val else "",
                                    key=f"model_{idx}_{m_idx}_{key}"
                                )

                    edited_models.append(edited_model)

                edited_fields["models"] = edited_models

                st.markdown("**檔案設定**")
                auto_name = build_auto_filename(corrected_cat, edited_fields, edited_models)
                final_filename = st.text_input(
                    "PDF 檔名（不需輸入 .pdf，可手動修改）",
                    value=auto_name,
                    key=f"filename_{idx}"
                )

                cat_folder = CATEGORIES.get(corrected_cat, "")
                folder_mode = st.radio(
                    "子資料夾設定",
                    ["不使用子資料夾", "選擇既有子資料夾", "建立新子資料夾"],
                    horizontal=True, key=f"folder_mode_{idx}"
                )

                subfolder_path = ""

                if folder_mode == "選擇既有子資料夾":
                    current_prefix = cat_folder
                    path_parts = []
                    for level in range(4):
                        try:
                            sub_list = list_s3_subfolders(current_prefix)
                        except Exception:
                            sub_list = []
                        if not sub_list:
                            break
                        chosen = st.selectbox(
                            f"第 {level+1} 層資料夾",
                            ["（此層結束）"] + sub_list,
                            key=f"subfolder_L{level}_{idx}"
                        )
                        if chosen == "（此層結束）":
                            break
                        path_parts.append(chosen)
                        current_prefix = f"{current_prefix}/{chosen}"
                    subfolder_path = "/".join(path_parts)

                elif folder_mode == "建立新子資料夾":
                    subfolder_path = st.text_input(
                        "輸入新子資料夾路徑（多層用 / 分隔，例如 RA/【一對一】/【R32大關】）",
                        value="",
                        key=f"new_subfolder_{idx}"
                    )

                fname_clean = final_filename.strip() or "（未命名）"
                if subfolder_path.strip():
                    full_s3_path = f"{cat_folder}/{subfolder_path.strip('/')}/{fname_clean}.pdf"
                else:
                    full_s3_path = f"{cat_folder}/{fname_clean}.pdf"

                st.caption(f"📁 S3 存放路徑：`{full_s3_path}`")

                confirmed_data.append({
                    "filename": r["filename"],
                    "category": corrected_cat,
                    "fields": edited_fields,
                    "pdf_bytes": r["pdf_bytes"],
                    "s3_key": full_s3_path,
                })

        st.divider()
        if confirmed_data and st.button("✅ 確認無誤，批次歸檔並寫入資料表", use_container_width=True):
            with st.spinner("處理中…"):
                try:
                    ws = get_data_worksheet()
                    raw_values = ws.get_all_values()
                    values = [_pad_row(list(r)) for r in raw_values]

                    ws2 = get_data_worksheet2()
                    raw_values2 = ws2.get_all_values()
                    values2 = [_pad_row(list(r), min_len=SHEET2_MIN_COLS) for r in raw_values2]

                    pending_updates = {}
                    pending_formats = []
                    pending_updates2 = {}
                    written_rows = []   # (filename, s3_key, row, model_name, sheet_tag)

                    for item in confirmed_data:
                        cat = item["category"]

                        s3_key = upload_pdf_to_s3(item["pdf_bytes"], item["s3_key"])

                        rows = write_all_rows(values, pending_updates, pending_formats,
                                               values2, pending_updates2, cat, item["fields"])
                        for row, model_name, sheet_tag in rows:
                            written_rows.append((item["filename"], item["s3_key"], row, model_name, sheet_tag))

                    commit_updates_to_sheet(ws, pending_updates, pending_formats)
                    if pending_updates2:
                        ws2.batch_update(
                            [{"range": addr, "values": [[val]]} for addr, val in pending_updates2.items()],
                            value_input_option="USER_ENTERED",
                        )

                    total_pdfs = len(confirmed_data)
                    total_rows = len(written_rows)
                    st.success(f"✅ 已完成 {total_pdfs} 份 PDF、共 {total_rows} 筆型號資料的歸檔，並寫入「Total Certificate Management」！")
                    operator = st.session_state.get("username", "未知")
                    sheet_label = {"sheet1": "工作表1", "sheet2": "工作表2"}
                    for fname, s3_key, row, model_name, sheet_tag in written_rows:
                        st.caption(f"・{model_name} → `{s3_key}`（{sheet_label[sheet_tag]} 第 {row} 列）")
                        log_ocr_action(
                            operator=operator,
                            filename=s3_key.split("/")[-1],
                            action="上傳",
                            detail=f"S3: {s3_key} | {sheet_label[sheet_tag]}第{row}列 | 型號: {model_name}"
                        )

                    st.session_state["ocr_results"] = []

                except Exception as e:
                    st.error(f"歸檔失敗：{e}")



render = render_main
