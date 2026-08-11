from pathlib import Path
from typing import Any, Optional

import streamlit.components.v1 as components

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
INDEX_FILE = FRONTEND_DIR / "index.html"

if not FRONTEND_DIR.is_dir():
    raise FileNotFoundError("找不到自訂元件資料夾：{}".format(FRONTEND_DIR))
if not INDEX_FILE.is_file():
    raise FileNotFoundError("找不到自訂元件入口檔：{}".format(INDEX_FILE))

_COMPONENT = components.declare_component(
    "login_panel",
    path=str(FRONTEND_DIR),
)


def login_panel(
    step: str,
    error: Optional[str] = None,
    email_hint: str = "",
    key: Optional[str] = None,
) -> Any:
    """
    白底莫蘭迪藍風格的登入畫面（信箱驗證碼兩步驟）。

    step: "email"（輸入信箱）或 "code"（輸入驗證碼）
    error: 要顯示在卡片內的錯誤訊息，沒有就傳 None
    email_hint: step=="code" 時，顯示「驗證碼已寄至 xxx」的信箱

    回傳： {"action": "send" | "verify" | "resend" | None, "email": str, "code": str, "nonce": int}
    """
    return _COMPONENT(
        step=step,
        error=error,
        email_hint=email_hint,
        key=key,
        default={"action": None, "email": "", "code": "", "nonce": 0},
    )
