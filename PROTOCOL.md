# 錢包登入協定 第 1 版

本文件定義網站、錢包 App 之間的登入協定（含 v0.2.0 新增的「同一裝置登入」見第 9 節、v0.3.0 新增的「發起裝置資訊」見第 10 節）。任何程式語言只要依照本文件實作，就能與錢包 App 互通。`walletlogin` 套件是這份協定的 Python 實作。

---

## 1. 角色

| 角色 | 說明 |
|---|---|
| **錢包** | 使用者手機上的 App，持有私鑰 |
| **網頁** | 使用者在瀏覽器開啟的網站頁面 |
| **網站伺服器** | 網站的後端，負責驗證簽名。**驗證只能在這裡做** |

錢包與網頁**不直接溝通**，兩者都只與網站伺服器溝通。

## 2. 流程

```
 網頁                      網站伺服器                      錢包
  │ ① POST /session          │                              │
  │─────────────────────────→│ 產生 session_id、nonce、      │
  │←─────────────────────────│ poll_token                   │
  │  QR Code 內容 + poll_token│                              │
  │                          │                              │
  │ 顯示 QR Code ─────────────────────────── ② 掃描 ────────→│
  │                          │                              │ 使用者確認網域
  │                          │                              │ 組訊息、簽名
  │                          │←──────── ③ POST verify_url ──│
  │                          │ 驗證簽名 ───────── 結果 ────→│
  │                          │                              │
  │ ④ POST /status（每 1.5 秒）│                              │
  │─────────────────────────→│                              │
  │←─────────────────────────│                              │
  │  JWT（只發一次）           │                              │
```

## 3. QR Code 內容

UTF-8 編碼的 JSON：

```json
{
  "type": "wallet-login",
  "v": 1,
  "domain": "shop.example.com",
  "uri": "https://shop.example.com",
  "session_id": "Mo3eubslMZp4ipKjYY5jcA",
  "nonce": "48ea6c0ab67cd09583e7dc192826faec",
  "verify_url": "https://shop.example.com/walletlogin/verify"
}
```

| 欄位 | 說明 |
|---|---|
| `type` | 固定為 `"wallet-login"` |
| `v` | 協定版本，本文件為 `1` |
| `domain` | 網站網域（含 port），會顯示給使用者確認 |
| `uri` | 網站網址（`http(s)://` + `domain`，沒有路徑） |
| `session_id` | 登入請求的編號 |
| `nonce` | 一次性亂數，至少 8 個英數字元 |
| `verify_url` | 錢包送出簽名的網址 |
| `info_url` | 選填（v0.3.0）。錢包查詢「發起這次登入的裝置」的網址，見第 10 節 |
| `mode` | 選填。`"same_device"` 表示同一裝置登入（見第 9 節）；沒有此欄位即為跨裝置（QR Code） |
| `return_url` | `mode` 為 `"same_device"` 時必填：簽名後錢包要切回的網頁 |

**QR Code 不可包含任何秘密**，因為它公開顯示在螢幕上。

### 錢包必須檢查

- `type`、`v` 正確，否則視為「不是登入用的 QR Code」
- `uri`、`verify_url`（以及 `return_url`、`info_url`，如果有）都是 `http` 或 `https`，且網域（含 port）都等於 `domain`。否則拒絕，避免畫面顯示 A 網站，簽名或兌換碼卻送到 B 網站
- 簽名前**必須顯示 `domain`** 讓使用者確認

## 4. 簽名訊息

採用 [EIP-4361（Sign-In with Ethereum）](https://eips.ethereum.org/EIPS/eip-4361) 的格式，以 `\n` 換行，結尾沒有換行：

```
{domain} wants you to sign in with your Ethereum account:
{address}

Sign in with your wallet. This request will not trigger any transaction.

URI: {uri}
Version: 1
Chain ID: 1
Nonce: {nonce}
Issued At: {ISO 8601 時間}
Request ID: {session_id}
```

| 欄位 | 值 |
|---|---|
| `{domain}`、`{uri}`、`{nonce}` | QR Code 中的對應欄位 |
| `{address}` | 錢包地址，EIP-55 大小寫格式 |
| `{session_id}` | QR Code 中的 `session_id` |
| `Issued At` | 簽名時間，ISO 8601 格式 |

### 簽名方式

[EIP-191](https://eips.ethereum.org/EIPS/eip-191)（`personal_sign`）：對 `"\x19Ethereum Signed Message:\n" + 訊息位元組長度 + 訊息` 做 Keccak-256 雜湊後，以 secp256k1 ECDSA 簽名。簽名為 65 位元組（r、s、v，v 為 27 或 28），以 `0x` 開頭的十六進位字串傳送。

### 金鑰推導（錢包）

助記詞依 BIP-39 轉為種子，再依 BIP-32 / BIP-44 路徑 `m/44'/60'/0'/0/0` 推導私鑰。與 MetaMask 等錢包相同。

## 5. API

以下路徑以預設的 `/walletlogin` 為例，實際路徑由網站決定（錢包只看 `verify_url`）。所有請求與回應皆為 JSON。錯誤時回應 `{"detail": "給使用者看的錯誤訊息"}`。

### ① `POST /walletlogin/session`（網頁）

請求：無內容（跨裝置），或同一裝置登入時：
```json
{ "mode": "same_device", "return_url": "https://shop.example.com/login" }
```

回應 `200`：
```json
{
  "session_id": "...",
  "poll_token": "...",
  "qr_payload": "{\"type\":\"wallet-login\",...}",
  "expires_in": 300
}
```

`poll_token` 只給網頁，**不可放進 QR Code**。同一裝置登入時，回應多一個 `app_link`（見第 9 節）。

### ③ `POST {verify_url}`（錢包）

請求：
```json
{ "session_id": "...", "message": "簽名訊息原文", "signature": "0x..." }
```

回應：

| 狀態碼 | 意思 |
|---|---|
| `200` | `{"ok": true, "address": "0x...", "code": null}` 驗證成功。同一裝置登入時 `code` 為兌換碼 |
| `400` | 登入請求不存在或已過期、訊息格式錯誤、欄位不符 |
| `401` | 簽名驗證失敗 |
| `409` | 這個登入請求已經用過了 |

### ④ `POST /walletlogin/status`（網頁）

請求：
```json
{ "session_id": "...", "poll_token": "...", "code": "同一裝置登入時必填" }
```

回應：

| 狀態碼 | 內容 |
|---|---|
| `200` | `{"status": "pending"}` 尚未簽名 |
| `200` | `{"status": "ok", "token": "JWT", "address": "0x..."}` 登入成功。**JWT 只發一次**，發出後登入請求即刪除 |
| `400` | 同一裝置登入的兌換碼錯誤 |
| `404` | 登入請求不存在、已過期，或 `poll_token` 錯誤 |

## 6. 網站伺服器的驗證步驟

收到 ③ 時，必須**依序**完成以下檢查，任一項失敗即拒絕：

1. `session_id` 對應的登入請求存在且未過期
2. 訊息符合第 4 節格式，且：
   - `Request ID` 等於 `session_id`
   - 網域、`URI` 等於網站自己設定的值（**不可從請求標頭推得**）
   - `Nonce` 等於該登入請求的 nonce
   - `Version` 為 `1`、`Chain ID` 為 `1`
3. 由訊息與簽名反推簽署者地址（ECDSA recover），必須等於訊息中的地址
4. 將登入請求標記為已驗證。**此步驟必須是原子操作**，同一個登入請求只能成功一次（防重放攻擊）

## 7. 時效

| 項目 | 建議值 |
|---|---|
| 登入請求（QR Code） | 5 分鐘 |
| JWT | 1 小時 |

## 8. 安全考量

- 正式環境必須使用 HTTPS
- 網站只會得到錢包地址，不會得到任何可用來登入其他網站的資訊
- 同一個錢包在不同網站使用相同地址，網站之間可以比對出同一個使用者（未來版本可考慮每個網站使用不同地址）
- 已知限制：攻擊者若將真網站的 QR Code 轉貼到假網站誘使使用者掃描，使用者簽名後登入的是攻擊者的瀏覽器。錢包顯示 `domain` 讓使用者確認，可以降低此風險

## 9. 同一裝置登入（v0.2.0）

使用者**直接用手機瀏覽網站**時，QR Code 在自己的螢幕上無法掃描。此時網頁改顯示「用錢包 App 開啟」按鈕。

### 流程

```
 手機瀏覽器（網頁）          網站伺服器                     錢包 App（同一支手機）
  │ ① POST /session              │                              │
  │   mode=same_device,          │ 檢查 return_url 屬於本網站     │
  │   return_url=目前網頁         │                              │
  │←─────────────────────────────│ app_link + poll_token        │
  │ 把 poll_token 存進 localStorage│                              │
  │                              │                              │
  │ ② 使用者點按鈕 app_link ────────────────────────────────────→│ 使用者確認網域、簽名
  │                              │←──────── ③ POST verify_url ──│
  │                              │ 驗證成功，產生兌換碼 ──── code →│
  │                              │                              │
  │←──────────── ④ 開啟 return_url#walletlogin_code=<code> ─────│
  │ ⑤ POST /status（poll_token + code）                          │
  │─────────────────────────────→│                              │
  │←─────────────────────────────│ JWT                          │
```

### App 連結

```
walletlogin://login?p=<QR Code 內容的 UTF-8 JSON，以 base64url 編碼，去掉結尾的 =>
```

內容與 QR Code 相同，多了 `"mode": "same_device"` 與 `return_url`。

### 返回網址

錢包簽名成功後開啟：

```
{return_url}#walletlogin_code={兌換碼}
```

兌換碼放在 `#` 之後，不會被送到伺服器，也不會出現在伺服器紀錄中。網頁讀取後應立即從網址列移除。

### 網站必須

- 建立同一裝置登入請求時，`return_url` 的協定與網域（含 port）必須等於網站自己的 `origin`，否則拒絕。**否則駭客可以把返回網址設成自己的網站，直接拿走兌換碼**
- 驗證成功時產生隨機兌換碼（建議至少 128 位元），只回傳給錢包
- `/status` 對同一裝置登入請求：沒有兌換碼時永遠回 `pending`，兌換碼錯誤回 `400`

### 錢包必須

- 收到連結時**只能開啟確認畫面，絕不自動簽名**
- 檢查 `return_url` 的網域等於 `domain`
- 確認畫面提醒使用者：只有自己剛剛在這支手機上按下按鈕時才繼續；別人傳來的連結請取消

### 為什麼需要兌換碼

防止「登入連結釣魚」：駭客在自己的電腦發起同一裝置登入，把連結傳給受害者。受害者點開後看到的是**真網站的網域**，簽名後登入結果若只憑 `poll_token` 領取，就會落到駭客的瀏覽器。加上兌換碼後，兌換碼只會被送到受害者手機上的瀏覽器，駭客永遠只看到 `pending`。

### 已知限制

- 使用者必須在手機的**預設瀏覽器**發起登入。錢包切回時會開啟預設瀏覽器，不同瀏覽器的 `localStorage` 不共用
- 其他 App 可以註冊相同的 `walletlogin://` 連結並攔截請求。連結不含秘密，私鑰不會外洩，Android 會讓使用者選擇開啟的 App；完全杜絕需要每個網站配合設定 App Links

## 10. 發起裝置資訊（v0.3.0）

### 要解決的攻擊

駭客在自己的電腦開啟真網站，取得登入 QR Code，再把它放到假網站（例如「掃碼領優惠」）。受害者掃描後，錢包顯示的是**真網站的網域**，簽名後登入的卻是駭客的電腦。

### 做法

網站建立登入請求時，記下**發起登入的瀏覽器**（瀏覽器、作業系統、IP）。錢包掃碼後**直接向網站查詢**，顯示在確認畫面，讓使用者確認「是不是我眼前這台裝置」。

### 為什麼不放在 QR Code 裡

QR Code 沒有任何防偽，駭客可以解開、把裝置資訊改成跟受害者相同，再重新產生。錢包必須**直接向真網站查詢**，網站回報的內容駭客改不了。QR Code 只放查詢網址 `info_url`。

### API：`GET {info_url}?session_id=...`（錢包）

回應 `200`：
```json
{ "browser": "Chrome", "os": "macOS", "ip": "192.168.1.101", "age_seconds": 12, "mode": "cross_device" }
```

| 欄位 | 說明 |
|---|---|
| `browser`、`os` | 由發起者的 User-Agent 判斷；無法辨識時為「未知瀏覽器」「未知系統」 |
| `ip` | 發起者的連線 IP |
| `age_seconds` | 幾秒前發起（由網站計算，不受手機時間誤差影響） |
| `mode` | 登入模式 |

登入請求不存在或已過期時回應 `404`。

### 錢包必須

- 檢查 `info_url` 的網域等於 `domain`，否則拒絕整個請求（避免駭客把查詢導向自己的網站、回報假資訊）
- 查詢失敗或網站不支援（沒有 `info_url`）時，提醒使用者「無法確認發起裝置」，但仍可登入

### 取捨

- **不顯示城市位置**：IP 轉城市需要第三方地理資料庫，違反「不依賴第三方」
- **看得到 QR Code 的人可以查到發起者的 IP**：通常就是使用者自己，風險低，換來能偵測轉貼攻擊
- **需要使用者自己比對**：錢包無法知道使用者眼前是哪台裝置，與 Google「新裝置登入」通知的做法相同
- **反向代理**：網站在代理之後時，看到的是代理的 IP，部署時需調整
