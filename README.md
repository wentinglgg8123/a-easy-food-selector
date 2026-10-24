# 食刻決定

用 Excel 餐廳名單隨機決定下一餐的繁體中文網站。以 **Python、Streamlit、openpyxl 與 pypinyin** 實作，採淺色簡約介面；頁面最上方先提供店名搜尋，下方接續篩選與推薦。

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

在瀏覽器開啟終端機顯示的網址，預設連接埠為 8501。結束時按 `Ctrl+C`。餐廳篩選與抽選不需要帳號、API 金鑰或資料庫；跨訪客共用的永久留言須另外設定 Supabase，步驟見下方。

## 使用方式

1. 開啟網站即可使用內建餐廳名單。最上方「搜尋店家」輸入店名並按 Enter，會從目前整份名單搜尋，每頁顯示 3 間，可直接查看及發布評論。搜尋框右側的 ×「清除搜尋」可清空文字，包括尚未按 Enter 的輸入。
2. 下方可點選標籤按鈕，依地點、食物種類與價格篩選，不需展開下拉選單。各組均可複選，再點一次即可取消；每組的「全選／取消」只操作該組，整體「全部取消」會清空所有選項、搜尋及額外篩選。
3. 「一個人吃／約會／聚餐」與「快速上菜／慢慢享用」也可複選；餐廳必須同時具有所有選取的情境及節奏標記。因此全選這兩組會要求店家具備該組的全部標記，並非取消限制。
4. 按下抽選按鈕推薦一家；有兩間以上可抽選時，會避開上一間。推薦結果下方也能直接填寫暱稱、評分與評論。
5. 符合條件的餐廳每頁顯示 6 間，以「上一頁／下一頁」瀏覽；各餐廳下方可查看最新 3 則公開留言或新增留言。展開完整名單可匯出篩選結果，也可下載原始 Excel。
6. 若要使用自己的資料，按「匯入 Excel 名單」；「恢復內建名單」會回到專案提供的 176 筆資料。

頂部搜尋只比對**店名**，不受地點、料理、價格、情境、節奏或歇業隱藏設定限制，包含原表註記歇業的店家。搜尋結果區與下方進階篩選獨立；同一關鍵字仍會套用至下方推薦與篩選名單，並須同時符合其他已選條件。因此頂部找得到的店家，不一定會出現在下方可抽選名單。

「清除搜尋」只重設搜尋文字及搜尋頁碼，保留進階篩選與推薦紀錄。直接搜尋沒有結果時，「你是不是想找這些店家？」會列出最多 5 間目前名單中讀音或拼字接近的餐廳，例如「孫東保牛排」可建議「孫東寶牛排」。點選建議的實際店名後，才會代入搜尋並開啟該店的評論與評分表單。

近似搜尋使用 pypinyin 在 Python 本機比對忽略聲調的國語讀音與近似拼字，不需外部 API 或資料庫升級。讀音字典未必涵蓋所有多音字或方言；單字或不明文字可能沒有建議。

地點、食物種類及價格等級各組內，符合任一選項即可；各組之間則須同時符合。某組沒有選取項目時，該組不限條件。例如選「公館、師大」、「便當、日式」及價格「1、3」，會保留位於公館或師大、屬於便當或日式，且等級恰好為 1 或 3 的餐廳。

`Price` 保留原始 Excel 的 **1–5 等級**，介面以金幣數與以下價格範圍顯示，篩選區也會提供圖例。這是網站採用的級距說明，並非即時查證的每人消費。

| 原始等級 | 金幣 | 價格範圍（新臺幣） |
| --- | --- | --- |
| 1 | 🪙 | 0–100 元 |
| 2 | 🪙🪙 | 100–200 元 |
| 3 | 🪙🪙🪙 | 200–300 元 |
| 4 | 🪙🪙🪙🪙 | 300–500 元 |
| 5 | 🪙🪙🪙🪙🪙 | 500 元以上 |

價格按鈕選取的是確切等級；例如選 3 不會自動納入 1、2。畫面顯示金幣不會改寫原始資料，匯出仍保留 `Price` 的 1–5 數值。內建名單有 4 筆未填價格；價格組未選項目時保留，選取任何等級後則不納入價格未知的餐廳。價格組「全選」會選取所有已知等級；若要同時保留未知價格，請清空該組。

備註為「關門了」「已歇業」等明確歇業標記的餐廳，在下方篩選名單預設隱藏。在「更多選項」勾選「包含已註記歇業店家」可檢視原始資訊；頂部搜尋則一直能找到這些店家，但 **歇業店家永遠不會被抽選**。目前原始名單中的「郭董麻辣牛肉麵」備註為「關門了」；這是 Excel 中的標記，並非網站查證的即時營業狀態。

內建原始資料隨程式碼提供給所有訪客，並可完整下載。自行上傳的 Excel 會傳送至目前執行網站的 **Python 伺服器** 解析，只保存在該訪客的 Streamlit 工作階段記憶體，不會取代專案的原始檔、不會成為其他訪客的名單。應用程式不將上傳檔另存至磁碟，也不使用瀏覽器 `localStorage`；重新整理、關閉分頁或重啟伺服器後，會回到內建名單，請自行保留原始 Excel。

## 公開留言與 Supabase 設定

搜尋結果、推薦結果及餐廳名單都能直接評論。「您的暱稱」可留白、最多 40 字，留白時顯示為訪客；「評論內容」須為 1–500 字。「您的評分」滑桿預設為 3 分，可選 **1、1.5、2、2.5、3、3.5、4、4.5、5** 共 9 個分數。

每間餐廳顯示最新 3 則留言，星星與數值依資料庫實際保存的評分呈現，支援半顆星。升級前未含評分的舊留言顯示「未評分」，不會自動補上分數。留言及評分會傳至 Supabase，供其他訪客讀取，並保留於資料庫中，不隨 Streamlit 工作階段或網站重啟而清除。這與額外匯入 Excel 的暫存方式不同。

### 既有留言服務：升級半星評分

已成功使用共享留言的部署，**沿用既有 Supabase 專案及 Streamlit Secrets，不必重建或重新設定金鑰**。本次須執行一次資料庫升級：

1. 開啟既有 Supabase 專案，進入 **SQL Editor → New query**。
2. 確認查詢來源選擇 **Database**，不要選 **Logs**；這份 SQL 要在資料庫執行。
3. 貼上 [sql/upgrade_ratings.sql](sql/upgrade_ratings.sql) 的完整內容，按 **Run**，確認執行成功。
4. 回到 Streamlit Community Cloud 的 **Manage App**，選擇 **Reboot**。
5. 發布一則含半星評分的測試留言，並用另一個瀏覽器工作階段確認文字、星星及分數可讀取。

升級只新增評分欄位、約束及新版讀取函式，保留所有既有留言、ID、時間與舊版讀取函式。舊留言的評分維持空值。程式不會自動修改遠端資料庫；尚未升級時仍可讀取舊留言，「發布評論」則停用並提示管理員升級，待完成後才啟用。

### 全新部署：第一次設定共享留言

只有尚未設定留言服務的新部署才需要以下步驟。未設定時仍會顯示留言區，但「發布評論」按鈕會停用；程式不會改用本機暫存，也不會顯示虛假的送出成功。

1. 在 [Supabase](https://supabase.com/) 建立專案，等待資料庫準備完成。
2. 開啟該專案的 **SQL Editor**，新增查詢並選擇 **Database**，貼上並執行 [sql/reviews.sql](sql/reviews.sql) 的完整內容。此檔已包含留言與半星評分所需結構，新專案不需再執行升級檔。
3. 在 Supabase 專案設定找到 **Project URL** 與 **API Keys → Legacy API Keys** 中的 `service_role` 伺服器金鑰。請使用服務角色金鑰，勿使用 `anon` 或公開的 publishable key。
4. 在 Streamlit Community Cloud 開啟應用程式的 **Manage App → Settings → Secrets**，依 [.streamlit/secrets.toml.example](.streamlit/secrets.toml.example) 填入設定：

   ```toml
   [reviews]
   url = "https://YOUR_PROJECT.supabase.co"
   service_role_key = "YOUR_SERVER_SERVICE_ROLE_KEY"
   ```

5. 儲存後 **Reboot** 應用程式。先送出一則測試留言，再用另一個瀏覽器工作階段確認可讀取，才算完成實際連線與保存驗證。

本機可將範例檔複製為 `.streamlit/secrets.toml` 後填入；其他部署環境也可設定 `SUPABASE_URL` 與 `SUPABASE_SERVICE_ROLE_KEY` 兩個環境變數。正式金鑰只放在伺服器的環境變數或 Streamlit Secrets，**不要提交至 Git、寫進 Excel 或前端程式碼**；本機 `secrets.toml` 已列入 `.gitignore`。

SQL 啟用資料列層級安全性（RLS），不授予匿名瀏覽器直接讀寫權限；由 Python 伺服器使用服務角色金鑰呼叫 Supabase REST API，不需額外安裝 Supabase 套件。目前留言不要求使用者登入，也沒有網站內的審核後台；管理者可在 Supabase **Table Editor** 查閱及刪除留言。

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

推薦結果的地點、餐廳卡片及完整名單中的地圖連結皆可點選，會以餐廳名稱搭配名單中的地址或地點開啟外部 Google Maps 搜尋，不會請求瀏覽器定位。目前內建來源沒有完整地址及 Google Place ID，因此不保證搜尋會直接開啟已查證的特定店家頁面；請確認店名、分店、地點、價格與營業資訊後再出發。

## 程式架構與語言比例

| 路徑 | 功能 |
| --- | --- |
| `app.py` | Python 網頁介面、篩選與推薦呈現 |
| `data/food.xlsx` | 提供給所有訪客的完整原始餐廳名單 |
| `food_picker/defaults.py` | 載入內建原始資料，載入失敗時明確回報 |
| `food_picker/models.py` | 餐廳及篩選條件資料模型 |
| `food_picker/catalog.py` | 資料驗證、代碼對照、篩選及隨機推薦 |
| `food_picker/search.py` | 店名搜尋與本機讀音、近似拼字建議 |
| `food_picker/excel.py` | Excel 匯入、範本及結果匯出 |
| `food_picker/session.py` | 每位訪客獨立的名單與推薦紀錄 |
| `food_picker/presentation.py` | 顯示文字、餐廳卡片與地圖連結 |
| `food_picker/reviews.py` | Supabase REST 共享留言讀寫與驗證 |
| `sql/reviews.sql` | 建立留言資料表及 RLS 存取設定 |
| `sql/upgrade_ratings.sql` | 既有留言資料庫的半星評分升級，保留舊留言 |
| `.streamlit/secrets.toml.example` | 伺服器端 Supabase 設定範例，不含真實金鑰 |
| `static/styles.css` | 淺色簡約介面與手機版樣式 |
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
