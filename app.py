import streamlit as st
import random
import string
from datetime import datetime, timedelta

from login_panel import login_panel

st.set_page_config(
    page_title="商品證書管理入口",
    page_icon="🗂️",
    layout="wide",
    initial_sidebar_state="expanded",
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
# 分頁定義
# ─────────────────────────────────────────────
PAGES = [
    {"id": "01", "label": "原儀表板",   "group": "dashboard"},
    {"id": "02", "label": "新增分析",   "group": "dashboard"},
    {"id": "03", "label": "明細查詢",   "group": "dashboard"},
    {"id": "04", "label": "管理預警",   "group": "dashboard"},
    {"id": "05", "label": "PDF掃描歸檔", "group": "tools"},
    {"id": "06", "label": "PDF切割工具", "group": "tools"},
    {"id": "07", "label": "商品證書查詢", "group": "tools"},
    {"id": "08", "label": "生命週期審核", "group": "tools"},
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
# Google Sheets（登入紀錄用，跟 cert-query-system 共用同一份）
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
        <h2 style="color:#5C7A8A;">【商品證書管理入口】登入驗證碼</h2>
        <p>您的驗證碼為：</p>
        <h1 style="letter-spacing:8px;color:#7B98A8;font-size:36px;">{code}</h1>
        <p>驗證碼有效時間為 <strong>5 分鐘</strong>，請盡快輸入。</p>
        <p style="color:#888;font-size:12px;">此為系統自動發送，請勿回覆。</p>
        </body></html>
        """
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "【商品證書管理入口】登入驗證碼"
        msg["From"] = f"商品證書管理入口通知 <{gmail_user}>"
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
# 共用 CSS：白底莫蘭迪藍 + 深藍導覽列（延續 PBI 報表視覺，蓋掉 Streamlit 預設樣式）
# ─────────────────────────────────────────────
def inject_shared_css():
    st.markdown("""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@300;400;500;700&display=swap');
      html, body, [class*="css"] { font-family: 'Noto Sans TC', sans-serif; }
      #MainMenu, footer, header,
      [data-testid="stHeader"], [data-testid="stToolbar"],
      [data-testid="stDecoration"] { display: none !important; visibility: hidden !important; }
      [data-testid="stStatusWidget"] { opacity: 0 !important; pointer-events: none !important; }
      [data-testid="collapsedControl"] {
        display: flex !important; visibility: visible !important; opacity: 1 !important;
      }
      .block-container { padding-top: 1rem !important; margin-top: 0 !important; max-width: 100% !important; }
      .stApp { background-color: #F7F8F9; }

      .portal-header {
        background: #16324F; color: #fff; padding: .9rem 1.5rem;
        border-radius: 12px; margin-bottom: .8rem;
        display: flex; align-items: center; justify-content: space-between;
      }
      .portal-header h1 { font-size: 1.25rem; font-weight: 700; margin: 0; color: #fff; }
      .portal-header .user-info { font-size: .85rem; color: #CBD9E3; }

      .nav-bar {
        display: flex; gap: 6px; margin-bottom: 1rem; flex-wrap: wrap;
      }
      div[data-testid="stButton"] button {
        border-radius: 8px !important;
      }
      .st-key-nav_row div[data-testid="stButton"] button {
        background: #EEF2F4 !important; color: #33414A !important;
        border: 1px solid #E1E6E9 !important; font-weight: 600 !important;
        font-size: .82rem !important; padding: .4rem .3rem !important;
      }
      .st-key-nav_row div[data-testid="stButton"] button:hover {
        background: #DCE6EC !important;
      }
    </style>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────
# 登入畫面（沿用 cert-query-system 的 OTP 元件與流程）
# ─────────────────────────────────────────────
def render_login():
    inject_shared_css()
    st.markdown("""
    <div class="portal-header"><h1>商品證書管理入口</h1></div>
    """, unsafe_allow_html=True)

    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        st.markdown("<br>", unsafe_allow_html=True)
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
# 導覽列 + 分頁分發
# ─────────────────────────────────────────────
def render_nav():
    col_head_l, col_head_r = st.columns([5, 1.5])
    with col_head_l:
        st.markdown(f"""
        <div class="portal-header">
          <h1>商品證書管理入口</h1>
          <span class="user-info">👤 {st.session_state.get("username","")}</span>
        </div>
        """, unsafe_allow_html=True)
    with col_head_r:
        if st.button("登出", use_container_width=True, key="portal_logout_btn"):
            for k in ["logged_in", "username", "login_step", "login_email",
                      "otp_code", "otp_expiry", "login_error", "last_login_nonce"]:
                st.session_state.pop(k, None)
            st.rerun()

    with st.container(key="nav_row"):
        cols = st.columns(len(PAGES))
        for col, page in zip(cols, PAGES):
            with col:
                label = f"{page['id']} {page['label']}"
                is_active = st.session_state["current_page"] == page["id"]
                if st.button(label, key=f"nav_{page['id']}", use_container_width=True,
                             type="primary" if is_active else "secondary"):
                    st.session_state["current_page"] = page["id"]
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
        render_nav()
        render_page()


if __name__ == "__main__":
    main()
