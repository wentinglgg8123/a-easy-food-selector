# 食刻決定｜清大今天吃什麼

從 Excel 餐廳清單中隨機推薦一餐的繁體中文網站，支援清華大學校內及周邊 2 公里的用餐選擇。使用 **Python、Streamlit 與 openpyxl** 實作網頁、資料驗證、篩選、推薦和 Excel 讀寫，不需要 Node.js。

**目前隨附 8 間虛構示範餐廳，並非清大真實或完整的餐廳名單。** 請匯入自行確認過的餐廳資料後再用於實際推薦。

## 本機啟動

需要 Python 3.12 以上（鎖定相依套件以 Python 3.12 驗證）。先在專案目錄建立並啟用虛擬環境。

Windows PowerShell：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

macOS / Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

安裝已鎖定版本且附有檔案雜湊的相依套件，再啟動網站：

```bash
python -m pip install --require-hashes -r requirements.txt
python -m streamlit run app.py
```

在瀏覽器開啟終端機顯示的本機網址。設定檔 `.streamlit/config.toml` 使用連接埠 8501；結束時在終端機按 `Ctrl+C`。應用程式不需要帳號、API 金鑰或資料庫。

## 使用方式

1. 用示範資料體驗，或下載 Excel 範本並替換成真實餐廳資料。
2. 匯入 `.xlsx` 檔案，查看匯入結果及資料警告。
3. 依區域、類型、最高均消與關鍵字篩選，再隨機選一家。
4. 符合條件的餐廳有兩間以上時，下一次抽選會避開上一間。
5. 可將目前篩選結果下載為 Excel，或清除匯入名單以恢復示範資料。

上傳的 Excel 會傳送至目前執行網站的 **Python 伺服器**，由 openpyxl 解析。名單保存在該使用者的 Streamlit 工作階段記憶體，應用程式不會將它另存成永久檔案，也不使用瀏覽器 `localStorage`。重新整理頁面、關閉分頁或伺服器重新啟動後，資料可能重設；請保留原始 Excel。

## Excel 格式

只接受不超過 5 MB 的 `.xlsx` 檔案，讀取第一個工作表。第一列須為欄位名稱，最多支援 5,000 筆資料。

| 欄位 | 必填 | 說明 |
| --- | --- | --- |
| 餐廳名稱 | 是 | 餐廳或攤位名稱 |
| 區域 | 是 | `清大校內` 或 `校園周邊` |
| 類型 | 否 | 例如便當、麵食、早餐、素食 |
| 均消 | 否 | 每人平均消費，填寫新臺幣數字 |
| 距離（公里） | 否 | 與統一基準點的距離，填寫公里數字 |
| 地址 | 否 | 顯示及 Google Maps 搜尋使用 |
| 備註 | 否 | 可記錄營業資訊、資料來源與最後查證日期 |

範本也包含 8 間虛構餐廳，請先刪除或替換範例。匯入時會略過無效資料列、移除重複資料並顯示警告；`校園周邊` 中距離超過 2 公里的餐廳會被排除。缺少距離的餐廳會標示為尚未確認。

為限制解析資源，Excel 壓縮檔解壓後總量不得超過 32 MiB，最多 256 個封裝項目；第一個工作表最多 10,000 個實體資料列及 32 欄。超過限制或格式損壞的檔案會被拒絕。

距離由 Excel 提供，網站不會定位、計算路線或自動查證地址。整理資料時請選定一致的基準點，例如清華大學校本部校門，並確認名稱、地址、均消及距離。網站未蒐集清大校內及周邊所有店家，不能保證名單完整或資訊即時。點選地圖連結後才會開啟外部 Google Maps，並傳入搜尋內容。

## 程式架構與語言比例

| 路徑 | 功能 |
| --- | --- |
| `app.py` | Python 網頁介面與使用者工作階段 |
| `food_picker/models.py` | 餐廳及篩選條件資料模型 |
| `food_picker/catalog.py` | 資料驗證、篩選、隨機推薦與示範清單 |
| `food_picker/excel.py` | Excel 匯入、範本及結果匯出 |
| `static/styles.css` | 網頁樣式 |
| `tests/` | Python 單元、網頁與瀏覽器測試 |
| `tools/language_report.py` | 以原始碼位元組估算 Python 比例 |

網頁及核心功能由 Python 實作。可在本機檢查原始碼比例：

```bash
python tools/language_report.py
```

工具分別列出包含測試及排除測試的比例，任一項 Python 未超過 50% 時會失敗。它是依已知副檔名計算的本機估算，**不等同 GitHub Linguist 的正式統計**。GitHub 的 Languages 以預設分支中的原始碼位元組及 Linguist 規則計算，推送後可能需等待更新。本專案不使用 `.gitattributes` 覆寫語言，也不靠無功能程式碼提高比例。

## 驗證

一般測試不需要瀏覽器：

```bash
python -m pytest
python -m compileall -q app.py food_picker
python tools/language_report.py
```

另有選用的 Playwright 瀏覽器測試，會自動啟動網站：

```bash
python -m playwright install chromium
python -m pytest -m browser
```

雲端環境若已提供 Chromium，可直接使用：

```bash
CHROMIUM_PATH=/usr/bin/chromium python -m pytest -m browser
```

GitHub Actions 使用 Python 3.12 執行相依套件安裝、一般測試、語法編譯與語言比例檢查。

## 部署

這是需要持續執行 Python 程序的 Streamlit 網站，可部署至支援 Streamlit 或 Python 服務的平台。設定安裝命令為 `python -m pip install --require-hashes -r requirements.txt`，啟動命令為 `python -m streamlit run app.py`；若平台指定連接埠，可加上 `--server.port`。不能將專案直接當作 GitHub Pages 靜態網站部署。
