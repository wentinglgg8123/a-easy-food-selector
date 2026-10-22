# FOODFLIX｜食刻決定

用 Excel 餐廳名單隨機決定下一餐的繁體中文網站。以 **Python、Streamlit 與 openpyxl** 實作，採深色及紅色的串流平台風格介面，與 Netflix 無關。

網站直接載入專案內的 [data/food.xlsx](data/food.xlsx)，每位訪客開啟就能使用，不必自行上傳。原始檔共有 **176 筆餐廳、8 個地點、25 種料理**；其中一筆備註為「關門了」，預設 **175 間可抽選**。名單來自提供的 Excel，包含公館、和平 118 巷、新生南路等地，**不是清華大學周邊 2 公里的完整店家資料**。店家是否營業並未即時查證。

## 本機啟動

需要 Python 3.12 以上；鎖定相依套件以 Python 3.12 驗證，不需要 Node.js。

Windows PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

macOS / Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements.txt
python -m streamlit run app.py
```

在瀏覽器開啟終端機顯示的網址，預設連接埠為 8501。結束時按 `Ctrl+C`。應用程式不需要帳號、API 金鑰或資料庫。

## 使用方式

1. 開啟網站即可使用內建餐廳名單。
2. 依地點、食物種類、最高價格等級與關鍵字篩選。
3. 可複選「一個人吃／約會／聚餐」及「快速上菜／慢慢享用」；所有選取條件必須同時符合。
4. 按下抽選按鈕推薦一家；有兩間以上可抽選時，會避開上一間。
5. 展開符合條件的名單，可匯出目前結果。也可下載完整原始名單。
6. 若要使用自己的資料，按「匯入 Excel 名單」；「恢復內建名單」會回到專案提供的 176 筆資料。

`Price` 是 **1–5 的價格等級**，不是新臺幣金額，不會換算成消費預算。內建名單有 4 筆未填價格；選擇價格上限時，不會納入價格未知的餐廳。

備註為「關門了」「已歇業」等明確歇業標記的餐廳預設隱藏。在「更多選項」勾選「包含已註記歇業店家」可檢視原始資訊，但 **歇業店家永遠不會被抽選**。目前原始名單中的「郭董麻辣牛肉麵」備註為「關門了」；這是 Excel 中的標記，並非網站查證的即時營業狀態。

內建原始資料隨程式碼提供給所有訪客，並可完整下載。自行上傳的 Excel 會傳送至目前執行網站的 **Python 伺服器** 解析，只保存在該訪客的 Streamlit 工作階段記憶體，不會取代專案的原始檔、不會成為其他訪客的名單。應用程式不將上傳檔另存至磁碟，也不使用瀏覽器 `localStorage`；重新整理、關閉分頁或重啟伺服器後，會回到內建名單，請自行保留原始 Excel。

## Excel 格式

只接受不超過 5 MiB 的 `.xlsx`，讀取第一個工作表；第一列為欄位名稱，最多 5,000 筆資料。下載範本包含 **2 筆虛構資料**，請替換後再匯入。

| 欄位 | 說明 |
| --- | --- |
| `Restaurant` | 必填，餐廳名稱 |
| `Location` | 地點代碼，例如 `Gongguan`；未知代碼照原樣顯示 |
| `Genre` | 料理代碼，例如 `Steak`、`Bento`；未知代碼照原樣顯示 |
| `Price` | 整數 1–5 的價格等級，不知道時留白 |
| `OnePerson` | 適合一人用餐填 `O`，未標記時留白 |
| `Dating` | 適合約會填 `O` |
| `Gathering` | 適合聚餐填 `O` |
| `FastServe` | 快速上菜填 `O` |
| `SlowEat` | 適合慢慢享用填 `O` |
| `Coordinates` | `緯度, 經度`，例如 `25.0182, 121.5310`；可留白 |
| `Comments` | 保留原始備註；含歇業標記的餐廳不會被推薦 |

介面將已知英文代碼顯示成中文，匯出時保留原始地點及料理代碼：

| 地點代碼 | 顯示名稱 |
| --- | --- |
| `Gongguan` | 公館 |
| `Heping118` | 和平 118 巷 |
| `Liuzhangli` | 六張犁 |
| `NTUMed` | 臺大醫學院 |
| `NTUST` | 臺灣科技大學 |
| `School` | 校內（原名單） |
| `Shida` | 師大 |
| `XinshengSouth` | 新生南路 |

料理代碼例如 `Steak` 顯示為「牛排」、`Bento` 為「便當」、`SouthEastAsian` 為「東南亞料理」。`School` 是原始資料的地點代碼，網站不會將它推定為清大校內，也不會根據座標自動套用清大 2 公里範圍。

仍支援舊版「餐廳名稱、區域、類型、均消、距離（公里）、地址、備註」格式。舊版均消使用新臺幣金額，與新版價格等級分開儲存；明確標為清大周邊且距離超過 2 公里的舊版資料仍會略過。新版篩選中，舊版未提供的等級、情境與節奏欄位不會被臆測補上。

解析時會略過無效資料列、處理重複資料並顯示提醒。為限制資源使用，Excel 解壓後總量最多 32 MiB、256 個封裝項目；第一個工作表最多 10,000 列及 32 欄。公式不會執行，損壞或超過限制的檔案會被拒絕。

點選地圖連結後才會開啟外部 Google Maps；有座標時使用餐廳座標搜尋，不會請求瀏覽器定位。店家名稱、地點、價格與營業資訊請以原始資料及出發前確認結果為準。

## 程式架構與語言比例

| 路徑 | 功能 |
| --- | --- |
| `app.py` | Python 網頁介面、篩選與推薦呈現 |
| `data/food.xlsx` | 提供給所有訪客的完整原始餐廳名單 |
| `food_picker/defaults.py` | 載入內建原始資料，載入失敗時明確回報 |
| `food_picker/models.py` | 餐廳及篩選條件資料模型 |
| `food_picker/catalog.py` | 資料驗證、代碼對照、篩選及隨機推薦 |
| `food_picker/excel.py` | Excel 匯入、範本及結果匯出 |
| `food_picker/session.py` | 每位訪客獨立的名單與推薦紀錄 |
| `food_picker/presentation.py` | 顯示文字、餐廳卡片與地圖連結 |
| `static/styles.css` | 深色紅色介面與手機版樣式 |
| `tests/` | Python 單元、介面與瀏覽器測試 |
| `tools/language_report.py` | 以原始碼位元組估算 Python 比例 |

網頁及核心功能由 Python 實作，可在本機檢查原始碼比例：

```bash
python tools/language_report.py
```

工具分別列出包含測試及排除測試的比例，任一項 Python 未超過 50% 時會失敗。這是依已知副檔名計算的本機估算，**不等同 GitHub Linguist 的正式統計**。GitHub Languages 以預設分支的原始碼位元組與 Linguist 規則計算，推送後可能需等待更新。本專案不使用 `.gitattributes` 覆寫語言，也不靠無功能程式碼增加比例。

## 驗證

一般測試不需要瀏覽器：

```bash
python -m pytest
python -m compileall -q app.py food_picker
python tools/language_report.py
```

選用的 Playwright 瀏覽器測試會自動啟動網站，並檢查桌面與手機介面：

```bash
python -m playwright install chromium
python -m pytest -m browser
```

雲端環境若已提供 Chromium，可直接使用：

```bash
CHROMIUM_PATH=/usr/bin/chromium python -m pytest -m browser
```

GitHub Actions 使用 Python 3.12 執行套件安裝、一般測試、語法編譯與語言比例檢查。

## 部署

這是需持續執行 Python 程序的 Streamlit 網站。部署至支援 Python 的平台時，須一併保留 `data/food.xlsx`；安裝命令為 `python -m pip install --require-hashes -r requirements.txt`，啟動命令為 `python -m streamlit run app.py`。預設連接埠為 8501，平台若指定其他連接埠，可加上 `--server.port`。不能直接作為 GitHub Pages 靜態網站部署。
