import streamlit as st
import random
import string
from datetime import datetime, timedelta

from login_panel import login_panel

st.set_page_config(
    page_title="Product Certification Compliance Department Library",
    page_icon="🗂️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────
# 登入白名單（沿用 cert-query-system）
# ─────────────────────────────────────────────
FIXED_CODE_ACCOUNTS = {
    "hungys@hotaidev.com.tw": "123456",
    "lozbutt@hotaidev.com.tw": "071071",
}
COMPANY_DOMAIN = "hotaidev.com.tw"

# ─────────────────────────────────────────────
# 分頁定義（不分組，直接依 01~08 排列）
# ─────────────────────────────────────────────
PAGES = [
    {"id": "01", "label": "證書管理"},
    {"id": "02", "label": "風險管理"},
    {"id": "03", "label": "證書總表"},
    {"id": "04", "label": "管理預警"},
    {"id": "05", "label": "PDF掃描歸檔"},
    {"id": "06", "label": "PDF切割工具"},
    {"id": "07", "label": "商品證書查詢"},
    {"id": "08", "label": "商品展延清單"},
]

# ─────────────────────────────────────────────
# Session state 初始化
# ─────────────────────────────────────────────
def init_session():
    defaults = {
        "logged_in": False,
        "username": "",
        "login_step": "email",
        "login_email": "",
        "otp_code": "",
        "otp_expiry": None,
        "login_error": None,
        "last_login_nonce": None,
        "current_page": "01",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ─────────────────────────────────────────────
# Google Sheets（登入紀錄用）
# ─────────────────────────────────────────────
@st.cache_resource
def get_gsheet_client():
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


def send_otp(email: str, code: str) -> bool:
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    try:
        gmail_user = st.secrets["GMAIL_USER"]
        gmail_password = st.secrets["GMAIL_APP_PASSWORD"]

        html_body = f"""
        <html><body style="font-family:Arial,sans-serif;font-size:14px;color:#333;">
        <h2 style="color:#3A7CA5;">【Product Certification Compliance Department Library】登入驗證碼</h2>
        <p>您的驗證碼為：</p>
        <h1 style="letter-spacing:8px;color:#205072;font-size:36px;">{code}</h1>
        <p>驗證碼有效時間為 <strong>5 分鐘</strong>，請盡快輸入。</p>
        <p style="color:#888;font-size:12px;">此為系統自動發送，請勿回覆。</p>
        </body></html>
        """
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "【Product Certification Compliance Department Library】登入驗證碼"
        msg["From"] = f"系統通知 <{gmail_user}>"
        msg["To"] = email
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
# 共用 CSS：高權重覆蓋 Streamlit 預設樣式
# ─────────────────────────────────────────────
def inject_shared_css():
    st.markdown("""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&display=swap');
      
      html, body, [class*="css"] { font-family: 'Noto Sans TC', sans-serif; }
      #MainMenu, footer, header, [data-testid="stHeader"], [data-testid="stToolbar"] { display: none !important; }
      
      .stApp { background-color: #f8fafc !important; }
      .block-container { padding: 0.6rem 0.8rem !important; max-width: 100% !important; }
      div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 0.8rem !important; }

      /* 經典深藍側邊欄 */
      .st-key-nav_col {
        background: #1e293b !important;
        border-radius: 12px !important;
        padding: 0.8rem 0.5rem !important;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05) !important;
      }

      .sys-title-box { padding: 0.2rem 0.4rem 0.6rem; border-bottom: 1px solid #334155; margin-bottom: 0.5rem; }
      .sys-title-box .app-badge { font-size: 0.6rem; font-weight: 700; color: #94a3b8; letter-spacing: 0.05em; }
      .sys-title-box .app-name { font-size: 0.78rem; font-weight: 700; color: #ffffff; line-height: 1.25; margin-top: 2px; }

      /* 側邊欄按鈕 */
      .st-key-nav_col [data-testid="stButton"] { margin-bottom: 3px !important; }
      .st-key-nav_col [data-testid="stButton"] > button {
        background: transparent !important; color: #cbd5e1 !important;
        border: 1px solid transparent !important; border-radius: 6px !important;
        font-size: 0.82rem !important; min-height: 34px !important; height: 34px !important;
        width: 100% !important; text-align: left !important; justify-content: flex-start !important;
      }
      .st-key-nav_col [data-testid="stButton"] > button:hover { background: rgba(255, 255, 255, 0.08) !important; color: #ffffff !important; }
      .st-key-nav_col [data-testid="stButton"] > button[kind="primary"] {
        background: #2563eb !important; color: #ffffff !important; font-weight: 700 !important;
        box-shadow: 0 4px 10px rgba(37, 99, 235, 0.3) !important;
      }
    </style>
    """, unsafe_allow_html=True)
# ─────────────────────────────────────────────
# 登入畫面
# ─────────────────────────────────────────────
def render_login():
    inject_shared_css()

    with st.container(key="login_wrap"):
        if True:
            step = st.session_state["login_step"]
            error_msg = st.session_state.get("login_error")

            value = login_panel(
                step=step,
                error=error_msg,
                email_hint=st.session_state.get("login_email", ""),
                key="login_panel_main",
            )

            if isinstance(value, dict) and value.get("action"):
                nonce = value.get("nonce")
                if nonce is not None and nonce != st.session_state.get("last_login_nonce"):
                    st.session_state["last_login_nonce"] = nonce
                    action = value["action"]

                    if action == "send":
                        email = (value.get("email") or "").strip().lower()
                        if not email:
                            st.session_state["login_error"] = "請輸入信箱"
                        else:
                            expiry = datetime.now() + timedelta(minutes=5)
                            matched_email = None
                            if email in FIXED_CODE_ACCOUNTS:
                                matched_email = email
                            else:
                                full_email = email + f"@{COMPANY_DOMAIN}" if "@" not in email else email
                                if full_email in FIXED_CODE_ACCOUNTS:
                                    matched_email = full_email

                            if matched_email:
                                code = FIXED_CODE_ACCOUNTS[matched_email]
                                st.session_state["login_email"] = matched_email
                                st.session_state["otp_code"] = code
                                st.session_state["otp_expiry"] = expiry
                                st.session_state["login_step"] = "code"
                                st.session_state["login_error"] = None
                                st.rerun()
                            elif not email.endswith(f"@{COMPANY_DOMAIN}"):
                                st.session_state["login_error"] = f"僅接受 @{COMPANY_DOMAIN} 的公司信箱"
                                log_login(email, False)
                            else:
                                code = "".join(random.choices(string.digits, k=6))
                                ok = send_otp(email, code)
                                if ok:
                                    st.session_state["login_email"] = email
                                    st.session_state["otp_code"] = code
                                    st.session_state["otp_expiry"] = expiry
                                    st.session_state["login_step"] = "code"
                                    st.session_state["login_error"] = None
                                    st.rerun()
                                else:
                                    st.session_state["login_error"] = "驗證碼寄送失敗，請稍後再試"

                    elif action == "verify":
                        email = st.session_state["login_email"]
                        code_input = (value.get("code") or "").strip()
                        now = datetime.now()
                        if st.session_state.get("otp_expiry") and now > st.session_state["otp_expiry"]:
                            st.session_state["login_error"] = "驗證碼已過期，請重新寄送"
                            st.session_state["login_step"] = "email"
                            log_login(email, False)
                            st.rerun()
                        elif code_input == st.session_state.get("otp_code"):
                            st.session_state["logged_in"] = True
                            st.session_state["username"] = email
                            st.session_state["login_step"] = "email"
                            st.session_state["otp_code"] = ""
                            st.session_state["login_error"] = None
                            log_login(email, True)
                            st.rerun()
                        else:
                            st.session_state["login_error"] = "驗證碼錯誤，請重新輸入"
                            log_login(email, False)

                    elif action == "resend":
                        st.session_state["login_step"] = "email"
                        st.session_state["login_error"] = None


# ─────────────────────────────────────────────
# 導覽列 (左側列表 01~08 直排)
# ─────────────────────────────────────────────
def render_nav():
    with st.container(key="nav_col"):
        # 系統名稱
        st.markdown("""
        <div class="sys-title-box">
            <div class="app-badge">PORTAL HUB</div>
            <div class="app-name">product certification compliance department library</div>
        </div>
        """, unsafe_allow_html=True)

        # 01 ~ 08 選單按鈕
        for page in PAGES:
            label = f"{page['id']}  {page['label']}"
            is_active = st.session_state["current_page"] == page["id"]
            if st.button(label, key=f"nav_{page['id']}", use_container_width=True,
                         type="primary" if is_active else "secondary"):
                st.session_state["current_page"] = page["id"]
                st.rerun()

        # 底部使用者資訊與登出
        st.markdown(f"""
        <div class="nav-user-container">
            <div class="nav-user" title="{st.session_state.get('username','')}">👤 {st.session_state.get('username','')}</div>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("登出", use_container_width=True, key="portal_logout_btn"):
            for k in ["logged_in", "username", "login_step", "login_email",
                      "otp_code", "otp_expiry", "login_error", "last_login_nonce"]:
                st.session_state.pop(k, None)
            st.rerun()


def render_page():
    page_id = st.session_state["current_page"]

    if page_id == "01":
        from pages_impl import page_dashboard_01
        page_dashboard_01.render()
    elif page_id == "02":
        from pages_impl import page_analysis_02
        page_analysis_02.render()
    elif page_id == "03":
        from pages_impl import page_detail_03
        page_detail_03.render()
    elif page_id == "04":
        from pages_impl import page_alert_04
        page_alert_04.render()
    elif page_id == "05":
        from pages_impl import page_pdf_ocr
        page_pdf_ocr.render()
    elif page_id == "06":
        from pages_impl import page_pdf_cut
        page_pdf_cut.render()
    elif page_id == "07":
        from pages_impl import page_cert_query
        page_cert_query.render()
    elif page_id == "08":
        from pages_impl import page_lifecycle
        page_lifecycle.render()


def main():
    init_session()
    if not st.session_state["logged_in"]:
        render_login()
    else:
        inject_shared_css()
        col_nav, col_content = st.columns([1.2, 6.8], gap="small")
        with col_nav:
            render_nav()
        with col_content:
            render_page()


if __name__ == "__main__":
    main()
