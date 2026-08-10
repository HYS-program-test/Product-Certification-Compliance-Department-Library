# 商品證書管理入口 — 開發中版本

## 目前狀態

**已完成（可運作）**
- 登入（沿用 cert-query-system 的 OTP 元件 + 白名單）
- 導覽列（01-08，點擊切換分頁）
- 05 PDF掃描歸檔（來自 pdf-ocr-claude，已移除內部登入）
- 06 PDF切割工具（來自 pdf-cut）
- 07 商品證書查詢（來自 cert-query-system，含 AI 查詢助理、S3 下載、申請送審文件）
- 08 生命週期審核（來自 product-life-circle，展延決策 + 排程寄信設定）

**尚未完成（先放佔位訊息）**
- 01 原儀表板
- 02 新增分析
- 03 明細查詢
- 04 管理預警（之後會串接 08 的展延決策功能）

## 部署前必須設定的 Streamlit Secrets

跟原本三套系統相同，這是合併後單一部署需要的完整清單（缺一項，對應分頁會出現錯誤訊息，不影響其他分頁）：

```toml
GOOGLE_SHEETS_ID = "..."          # 登入/下載/申請紀錄用的 Google Sheet
GMAIL_USER = "..."
GMAIL_APP_PASSWORD = "..."        # 入口登入 + 08頁寄信 共用
ANTHROPIC_API_KEY = "..."         # 05頁 OCR + 07頁 AI查詢助理
AWS_ACCESS_KEY_ID = "..."
AWS_SECRET_ACCESS_KEY = "..."     # 07頁 S3 下載

[gcp_service_account]
# 完整貼上服務帳號 JSON 內容（跟三套系統原本用的是同一組）
```

## 已知限制／待確認事項

1. **`pdf-cut`／`pdf-ocr-claude` 內部呼叫 `st.stop()`**：在合併後的頁面裡呼叫 `st.stop()` 會中止「整個 App 這一次的執行」，不只是那個分頁——實務上影響不大（畫面已經畫完），但如果切換分頁後偶爾要多點一次才有反應，這是原因，之後可以優化掉。
2. **05／06／07／08 四個頁面內部各自都有 `st.cache_data` / `st.cache_resource` 快取**，四頁共用同一個 Python process，快取彼此獨立不會互相污染，但代表如果四頁都同時讀 Google Sheets，第一次載入可能會感覺到多次讀取的等待時間疊加。
3. 尚未在真實環境跑過（沒有 Secrets 無法完整測試），已完成的是語法檢查與靜態掃描（無 import 錯誤、無未定義變數），實際部署後可能還會有要修的小問題。

## 部署方式

跟現有三套系統一樣：整個資料夾推上 GitHub repo，Streamlit Community Cloud 指向 `app.py`，設定上面的 Secrets。
