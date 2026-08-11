from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit.components.v1 as components

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
INDEX_FILE = FRONTEND_DIR / "index.html"

if not FRONTEND_DIR.is_dir():
    raise FileNotFoundError("找不到自訂元件資料夾：{}".format(FRONTEND_DIR))
if not INDEX_FILE.is_file():
    raise FileNotFoundError("找不到自訂元件入口檔：{}".format(INDEX_FILE))

_COMPONENT = components.declare_component(
    "results_list",
    path=str(FRONTEND_DIR),
)


def results_list(
    rows: List[Dict[str, Any]],
    badge_text: str,
    badge_color: str = "#7B98A8",
    key: Optional[str] = None,
) -> Any:
    """
    白底莫蘭迪藍風格的搜尋結果清單（仿新聞列表：分類標籤＋標題＋副資訊＋右側加入下載）。

    rows: [
        {
            "row_id": int,        # 對應原始 DataFrame 的 index，用來回報是哪一列被點擊
            "title": str,         # 主要顯示文字（例如型號）
            "meta": str,          # 次要資訊（例如「實驗室：XXX　證書編號：XXX　有效期限：2027-05-01」）
            "available": bool,    # S3 是否有對應檔案；False 時右側按鈕會顯示為無法點擊
            "added": bool,        # 是否已經在下載清單中
        }, ...
    ]

    回傳： {"action": "add" | None, "row_id": int, "nonce": int}
    """
    return _COMPONENT(
        rows=rows,
        badge_text=badge_text,
        badge_color=badge_color,
        key=key,
        default={"action": None, "row_id": None, "nonce": 0},
    )
