# ShopAlert

> [English](README.md) · 繁體中文

ShopAlert 是一個以 Flask 開發的社群店家爭議紀錄網站。使用者可以註冊帳號、用關鍵字或目前位置搜尋店家，並提交店家資料、爭議說明，以及至少一個圖片或影片證據。

重要提醒：網站內容是使用者提交的指控，並不代表已經過 ShopAlert 獨立查證。正式上線前，應依所在地法規加入內容審核、檢舉與申訴、資料保存政策，以及法律與隱私審查流程。

## 功能

- 使用唯一使用者名稱與 Email 註冊，可用任一識別資訊登入、記住登入狀態及登出
- 依帳號識別資訊／用戶端 IP 組合持久保存登入失敗限制
- 登入與註冊皆可啟用 Cloudflare Turnstile；設定後一定會進行伺服器端驗證
- 依店名、地址、主題標籤或事件內容進行關鍵字搜尋
- 使用瀏覽器定位，依 2–100 公里範圍搜尋附近紀錄
- 手動輸入店名與地址
- 網路商店紀錄不需要實體地址，且不會出現在附近搜尋結果中
- 可選用會跟隨目前介面語言的 Google 地點自動完成，並填入可編輯的店名、本地化地址、座標及 Place ID
- 必須上傳至少一個證據，支援多張圖片或多部影片；多次選取或拖放會持續加入目前清單，顯示響應式發布前縮圖，並可在發布前逐一旋轉檔案
- 於首次請求時產生並快取 WebP 縮圖，供紀錄卡片與證據縮圖列使用，列表載入量僅為原始檔案的一小部分
- 紀錄卡片的摘要不論內容長短一律固定占用三行，因此同一列的卡片版面能夠對齊
- 每筆紀錄最多可加入 10 個選用且可搜尋的主題標籤，支援 Enter／逗號轉標籤、移除標籤、熱門標籤及依介面語言顯示的入門建議
- 輸入店家名稱或位置時延遲檢查相似紀錄，在圓形檢查圖示顯示即時數量，並以保留草稿的頁內對話框預覽可能已存在的紀錄
- 每筆紀錄最多可加入 10 個選用爭議／來源網址，並套用 SSRF 檢查、選用的 Cloudflare URL Scanner 判定、伺服器截圖快取及離站確認
- 每筆紀錄最多可加入 10 間選用的關聯店家，可透過延遲搜尋連結至 ShopAlert 既有紀錄，或手動輸入尚未在 ShopAlert 回報的店家
- 每筆公開紀錄網址皆使用穩定的 GUID，舊有數字連結會自動重新導向
- 私人的「我的紀錄」頁面，讓使用者查看及編輯自己的提交內容
- 個人檔案頁面，可變更個人圖片與密碼，並查看此帳號建立的紀錄
- 管理後台可封存／恢復或永久刪除紀錄、重設密碼，以及停權／恢復使用者，破壞性操作皆明確標示，且管理員本身的帳號無法被停權
- 可選用環境變數管理管理員憑證，啟動時自動建立帳號，並讓使用者名稱與密碼與設定值保持一致
- 顯示紀錄發布時間，並只在紀錄曾被編輯後顯示最後更新時間；時間會依訪客時區顯示
- 可新增或移除證據，但每筆紀錄必須始終保留至少一個證據檔案
- 可重新命名新上傳及既有證據的顯示檔名，同時保留實際檔案類型與隨機儲存名稱
- 新增及編輯紀錄時皆可使用上下按鈕或拖放永久調整媒體順序，既有證據與新加入檔案可在同一順序中排列
- 針對個別紀錄聯絡管理員的彈出視窗，以及受保護的審查收件匣
- 可填寫 Facebook、Instagram、Threads、TikTok 及其他官方社群連結
- 響應式與無障礙介面，清楚標示內容屬於社群指控，紀錄表單進度也會隨目前捲動區段更新
- 提供 ShopAlert 品牌 Favicon、多尺寸瀏覽器圖示、Apple Touch Icon 及可安裝網頁應用程式圖示
- 提供英文（en-US）與繁體中文（zh-TW）介面切換；尚未儲存偏好時會依 IP 國家設定預設語言
- 在個人檔案與頁尾分別提供語言、外觀與色彩選單，可設定英文、繁體中文、淺色、深色、跟隨系統及珊瑚色、黃色、紫色
- 提供公開的雙語網站介紹、更新紀錄與授權／來源標示頁面
- 提供公開的雙語隱私權政策，說明資料收集、公開提交內容、位置搜尋、瀏覽器儲存、第三方服務、保存方式及使用者選擇
- CSRF 防護、密碼雜湊、安全轉址、隨機上傳檔名，以及檔案類型與容量檢查

## 使用技術

- Python 3.10 以上
- Flask、Flask-SQLAlchemy、Flask-Login、Flask-WTF、Gunicorn
- 預設使用 SQLite，也可設定其他 SQLAlchemy 資料庫網址
- Jinja 伺服器端樣板、原生 CSS 與 JavaScript
- 使用 Pillow 產生列表縮圖快取
- 使用 FFmpeg 旋轉上傳的影片

## 本機啟動

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
python run.py
```

若要啟用影片旋轉，請透過作業系統的套件管理員安裝 FFmpeg；Docker 映像檔已自動包含 FFmpeg。

開啟 `http://127.0.0.1:5000`。資料庫與上傳檔案會建立在 `instance/` 目錄中。

在共用環境或正式環境部署前，請產生安全的密鑰：

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

把結果填入 `.env` 的 `SECRET_KEY`。請勿將 `.env` 提交到版本控制。

## 使用 Docker Compose 啟動

正式環境形式的映像檔使用 Python 3.12 與 Gunicorn，內含 Playwright Chromium 與 FFmpeg，並預設以非特權 UID `10001` 執行。Compose 使用的映像檔名稱為 `shopalert-holey-cc:local`。

```bash
cp .env.example .env
docker compose -f docker/compose.yaml up --build -d
docker compose -f docker/compose.yaml ps
docker compose -f docker/compose.yaml logs -f app
```

開啟 `http://127.0.0.1:8080`。SQLite 資料、上傳檔案及連結預覽資料會以 `/instance` 為路徑，持久保存於 `shop-alert-data` 命名 Volume；Container 也包含針對 8080 Port 的 HTTP Health Check。

```bash
docker compose -f docker/compose.yaml down
```

除非明確加入 `--volumes`，否則 `docker compose down` 不會移除命名 Volume。搬移或刪除前請先備份。若要使用不同的數字使用者 ID 建置，請在建置時設定（例如 `APP_UID=$(id -u) docker compose -f docker/compose.yaml build`）；既有的 `/instance` Volume 必須允許該 UID 寫入。本機操作 Helper、部署指令稿與資料庫備份應存放於 `private/` 目錄；該目錄已同時排除於 Git 與 Docker 建置內容之外，且不影響上述 Repository 設定流程。

## 環境變數

| 變數 | 是否必填 | 預設值 | 用途 |
| --- | --- | --- | --- |
| `SECRET_KEY` | 正式環境必填 | 僅供開發的預設值 | 簽署 Session 與 CSRF Token |
| `DATABASE_URL` | 否 | `sqlite:///shop_alert.db` | SQLAlchemy 資料庫網址 |
| `HOME_RECENT_REPORTS_COUNT` | 否 | `9` | 首頁每批載入的紀錄數量：頁面初次顯示的批次，以及後續捲動時載入的每一批 |
| `GOOGLE_MAPS_API_KEY` | 否 | 空白 | 啟用 Google 地點自動完成 |
| `ADMIN_EMAIL` | 建議設定 | 空白 | 可使用紀錄管理、使用者管理與聯絡收件匣的管理員帳號 |
| `ADMIN_PASSWORD` | 否 | 空白 | 與 `ADMIN_EMAIL` 一併設定時，啟動時若管理員帳號不存在會自動建立，並讓其登入密碼與此值保持一致（至少 8 個字元） |
| `ADMIN_USERNAME` | 否 | 空白 | 與 `ADMIN_EMAIL` 一併設定時，強制指定管理員帳號的唯一登入使用者名稱（3–30 個字母、數字或底線） |
| `LOGIN_MAX_ATTEMPTS` | 否 | `5` | 重試計算期間內允許的登入失敗次數 |
| `LOGIN_ATTEMPT_WINDOW_MINUTES` | 否 | `15` | 登入失敗次數的計算期間（分鐘） |
| `LOGIN_LOCKOUT_MINUTES` | 否 | `15` | 達到限制後帳號識別資訊／用戶端 IP 組合的鎖定時間（分鐘） |
| `TURNSTILE_SITE_KEY` | 正式環境必填 | 空白 | 顯示 Cloudflare Turnstile 元件的公開金鑰 |
| `TURNSTILE_SECRET_KEY` | 正式環境必填 | 空白 | 僅供後端驗證 Turnstile 的私密金鑰 |
| `TURNSTILE_EXPECTED_HOSTNAME` | 建議設定 | 空白 | Turnstile 成功結果必須符合的網站主機名稱 |
| `LINK_PREVIEW_TIMEOUT_SECONDS` | 否 | `15` | 產生外部連結截圖的瀏覽器逾時秒數 |
| `LINK_PREVIEW_SETTLE_MS` | 否 | `1500` | 截圖前額外等待頁面完成顯示的毫秒數 |
| `LINK_PREVIEW_CACHE_HOURS` | 否 | `24` | 產生的截圖保持新鮮的時間 |
| `CLOUDFLARE_URL_SCANNER_ACCOUNT_ID` | 建議設定 | 空白 | 擁有 URL Scanner Token 的 Cloudflare 帳戶 ID |
| `CLOUDFLARE_URL_SCANNER_API_TOKEN` | 建議設定 | 空白 | 具備「Account → URL Scanner → Edit」權限的私密 API Token |
| `CLOUDFLARE_URL_SCANNER_REQUEST_TIMEOUT_SECONDS` | 否 | `10` | 每次 Cloudflare API 請求的逾時秒數 |
| `CLOUDFLARE_URL_SCANNER_RESULT_TIMEOUT_SECONDS` | 否 | `40` | 等待掃描結果的最長秒數 |
| `CLOUDFLARE_URL_SCANNER_POLL_INTERVAL_SECONDS` | 否 | `10` | 查詢結果的間隔；Cloudflare 建議 10–30 秒 |
| `CLOUDFLARE_URL_SCANNER_CACHE_HOURS` | 否 | `24` | 重複使用 Cloudflare 判定結果的時間 |
| `MAX_CONTENT_LENGTH_MB` | 否 | `50` | 單次請求／上傳總容量上限（MB） |

### 依 IP 設定語言與時區

尚未儲存語言偏好時，ShopAlert 會讀取 Cloudflare 的 `CF-IPCountry` Header。來自台灣、香港或澳門的訪客預設使用繁體中文；其他或無法判斷的地區預設使用英文。訪客自行選擇的語言會儲存於簽章 Session 中，並永遠優先套用。

請啟用 Cloudflare **IP Geolocation**，讓 Origin 收到 `CF-IPCountry`。啟用 **Add visitor location headers** Managed Transform 後也會提供 `CF-Timezone`，供 ShopAlert 作為伺服器端時間顯示的備援時區；JavaScript 隨後會依瀏覽器實際時區顯示時間，以更準確處理旅行、VPN 與裝置設定。兩者皆無法使用時則顯示 UTC。請參考 Cloudflare 的 [IP Geolocation 指南](https://developers.cloudflare.com/network/ip-geolocation/)與 [Managed Transforms 參考資料](https://developers.cloudflare.com/rules/transform/managed-transforms/reference/)。

### 爭議連結截圖

訪客第一次預覽爭議連結時，ShopAlert 會使用 Playwright Chromium 產生截圖。截圖快取在 `instance/link_previews/`，並在 `LINK_PREVIEW_CACHE_HOURS` 到期前直接提供快取 PNG。外部網站是由 ShopAlert 伺服器存取，不會嵌入訪客的瀏覽器，因此 Threads 等拒絕 iframe 的網站仍可顯示預覽。

同時設定 `CLOUDFLARE_URL_SCANNER_ACCOUNT_ID` 與 `CLOUDFLARE_URL_SCANNER_API_TOKEN` 後，ShopAlert 會先提交**不公開列出（Unlisted）**的掃描、輪詢結果，再檢查 `verdicts.overall.malicious`。若判定具有惡意，Playwright 不會啟動；API 錯誤、逾時、掃描失敗或無法判定時也會採取 Fail Closed，訪客無法透過預覽視窗繼續前往。正常及惡意判定都會快取於 `instance/link_previews/*.scan.json`。介面會顯示「未發現已知威脅」而非「安全」，因為掃描判定並不是安全保證。

請建立具備 **Account → URL Scanner → Edit** 權限的 Cloudflare 自訂 API Token，將帳戶 ID 與 Token 填入 `.env` 後重新啟動。兩者必須同時設定或同時留空；只設定一項會讓應用程式停止啟動。兩者留空時，本機開發仍會執行既有的公開網路／SSRF 檢查及截圖流程，並在介面清楚標示尚未設定 Cloudflare 檢查。請參考 Cloudflare 官方的 [URL Scanner 指南](https://developers.cloudflare.com/radar/investigate/url-scanner/)與[建立 URL 掃描 API](https://developers.cloudflare.com/api/resources/url_scanner/subresources/scans/methods/create/)。

完整網址會傳送給 Cloudflare，因此請勿在爭議連結中放入私密 Token、Session ID 或其他機密。Cloudflare 文件說明成功掃描會保留 12 個月，失敗掃描保留 30 天；Unlisted 不會出現在公開的近期掃描及搜尋結果，但知道掃描 ID 的人仍可存取。

截圖工作程序只接受 80／443 Port 的 HTTP(S)，拒絕含帳密的網址，並檢查所有解析出的位址，阻擋本機、私有、Loopback、Link-local、保留及其他非公開網路。瀏覽器請求會被攔截，Service Worker 亦會停用。正式部署仍應另外設定對外防火牆，禁止應用程式／瀏覽器程序連線至內部網路；應用程式層級 DNS 檢查無法取代網路層級的 Egress 控制，也無法單獨防禦所有 DNS Rebinding 情境。規模較大時，建議將截圖工作移至受資源限制的背景 Worker，不要佔用網頁請求。

安裝 Python 套件後，請安裝相符的瀏覽器版本：

```bash
playwright install chromium
```

Linux Container 可能還需要 Playwright 的系統套件，可在建立映像檔時執行 `playwright install --with-deps chromium`。

### 登入保護與 Cloudflare Turnstile

登入失敗狀態會儲存在資料庫中，索引鍵由正規化帳號識別資訊與 `request.remote_addr` 進行 SHA-256 運算產生；已知的使用者名稱會統一對應至帳號 Email，因此切換兩種登入方式不會取得第二組重試次數。限制資料表不會保存原始識別資訊／IP 組合。鎖定期間 ShopAlert 會回傳 HTTP `429` 與 `Retry-After` 標頭。請正確設定反向代理及 Flask Proxy，確保 `request.remote_addr` 是預期的用戶端；ShopAlert 預設不信任 `X-Forwarded-For`。

請先在 Cloudflare 建立 Turnstile 元件，再同時設定 `TURNSTILE_SITE_KEY` 與 `TURNSTILE_SECRET_KEY`。若只設定其中一個，程式會在啟動時失敗，避免在未察覺的情況下略過 CAPTCHA。正式環境也應將 `TURNSTILE_EXPECTED_HOSTNAME` 設為部署網站的主機名稱（例如 `shopalert.example`）。兩把金鑰都留空時，本機開發環境會停用 Turnstile。登入及註冊表單的 Token 會傳送至 Cloudflare Siteverify；後端只有在驗證成功且 `login`／`signup` action 相符時才會處理帳號資料。

自動化或本機整合測試可使用 Cloudflare 公開測試金鑰，請參考官方的 [Turnstile 測試指南](https://developers.cloudflare.com/turnstile/troubleshooting/testing/)與[伺服器端驗證文件](https://developers.cloudflare.com/turnstile/get-started/server-side-validation/)。

### Google 地點自動完成

沒有 API Key 時仍可手動輸入。若要啟用自動完成：

1. 建立已啟用帳務的 Google Cloud 專案。
2. 啟用 **Maps JavaScript API** 與 **Places API (New)**。
3. 建立瀏覽器 API Key，限制可用的網站 HTTP referrer 與必要 API。
4. 在 `.env` 設定 `GOOGLE_MAPS_API_KEY`，然後重新啟動 Flask。

自動完成建議會跟隨 ShopAlert 目前的 `en-US` 或 `zh-TW` 語言。選取 Google 地點時會同時儲存兩種語言的格式化地址，因此紀錄卡片、詳細頁及編輯表單會隨介面語言切換地址。手動輸入的地址仍屬於使用者控制的文字，兩種介面都會顯示相同內容。

本專案使用目前的 `PlaceAutocompleteElement` 與 Places 動態載入方式。Google Maps Platform 可能產生費用，並受 Google 服務條款約束。

### 主題標籤與相似紀錄檢查

輸入主題標籤後按 Enter 或輸入逗號，即會轉換成可移除的標籤。每筆紀錄最多接受 10 個不重複的主題標籤；每個標籤可包含 1–30 個文字、數字或底線。入門建議會跟隨目前的介面語言（`en-US` 或 `zh-TW`），熱門標籤則保留使用者原本提交的文字。

建立或編輯紀錄時，店名／地址欄位會在停止輸入 450 毫秒後，呼叫需要登入的 `/api/reports/similar` Endpoint。比對會考慮店名模糊相似度、原始與本地化地址、完全相同的 Google Place ID，以及鄰近座標。圓形檢查圖示會顯示目前結果數量。點選檢查器後，頁內對話框最多顯示五筆排序後的相似紀錄；選取紀錄會在同源且受 Sandbox 限制的預覽框中開啟詳細頁，不會另開分頁或清除草稿。編輯頁會排除目前正在編輯的紀錄本身。

相似度結果僅供提醒，並非唯一性保證。數量為零只代表沒有紀錄通過目前的比對門檻，不代表使用大幅不同資料的相關紀錄一定不存在。

### 關聯店家

選用的關聯店家區塊每筆紀錄最多可加入 10 筆。輸入至少兩個字元後，會呼叫需要登入的 `/api/reports/search` Endpoint，比對店名與兩種本地化地址，最多回傳八筆未封存的紀錄；選取後會儲存該紀錄的 GUID，因此詳細頁永遠顯示被連結紀錄目前的店名與地址。尚未在 ShopAlert 回報的店家，可手動輸入店名（2–180 個字元）與選填的地址或公開連結（最多 500 個字元）。

關聯資料儲存在紀錄本身，因此被連結的紀錄之後若遭封存或刪除，只會不再顯示，而不會留下失效連結。紀錄不能將自己列為關聯店家，編輯頁的搜尋結果也會排除正在編輯的紀錄。

## 測試

```bash
pytest
```

測試涵蓋登入失敗限制、Turnstile 強制驗證、帳號驗證、權限控管、輸入驗證、含證據的紀錄建立、主題標籤行為、關聯店家連結、相似紀錄排序、詳細頁與媒體讀取、關鍵字搜尋，以及附近搜尋，另外也涵蓋 Cloudflare URL Scanner 用戶端與 Docker 部署設定。

## 資訊與管理頁面

- `/updates` — 雙語產品與安全性更新時間軸
- `/introduction` — 雙語網站介紹、使用流程與負責任使用說明；入口位於頁尾
- `/privacy` — 雙語說明資料收集、公開內容、外部服務、保存方式及使用者選擇
- `/licenses` — 第三方授權、服務條款及開發協助說明
- `/profile` — 登入使用者的個人圖片、密碼及紀錄管理頁面
- `/admin` — 僅限符合 `ADMIN_EMAIL` 帳號使用的紀錄與使用者管理後台
- `/admin/report-contacts` — 僅限符合 `ADMIN_EMAIL` 的帳號查看之受保護收件匣

若要啟用管理功能，請設定 `ADMIN_EMAIL`，再以完全相同的 Email 註冊或登入。也可以同時設定 `ADMIN_PASSWORD`：啟動時若管理員帳號不存在會自動建立，且只要兩者不一致，登入密碼就會重設為設定值——因此在 `ADMIN_PASSWORD` 仍生效期間，透過個人資料頁修改的密碼會在下次重啟時還原。`ADMIN_USERNAME` 對管理員帳號的使用者名稱採取相同機制，讓管理員能以設定的使用者名稱或 Email 登入；若該使用者名稱已被其他帳號使用，啟動會失敗。任何能讀取 `.env` 的人都能以管理員身分登入，請妥善保護該檔案。設定的管理員帳號無法停權自己。密碼重設會立即生效，請透過另一個可信任管道將替代密碼交付給使用者。

## 正式環境檢查清單

- 使用正式 WSGI Server 並置於 HTTPS 反向代理之後（隨附的 Docker 映像使用 Gunicorn，HTTPS 應由反向代理終止）。
- 隔離截圖瀏覽器，並以對外防火牆禁止連線至內部／私有網路。
- 使用 PostgreSQL 或其他受管資料庫、物件儲存、備份與惡意檔案掃描。
- 設定安全的 `SECRET_KEY`、Cookie 安全選項、可信任 Proxy，以及嚴格的上傳與儲存權限。
- 加入 Email 驗證、速率限制、帳號復原、內容審核佇列、下架與申訴流程、稽核紀錄及濫用監控。
- 提供服務條款、隱私權政策、同意與媒體保存規則；未經審核前避免公開個資或不實指控。
- 建議加入伺服器端檔案特徵檢查與轉檔，不要只依副檔名及 MIME 類型判斷。

## 授權

ShopAlert 以 [MIT 授權條款](LICENSE)發布。第三方資產與服務仍受其各自的授權與條款規範，詳見網站內的 `/licenses` 頁面。
