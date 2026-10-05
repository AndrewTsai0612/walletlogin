# 錢包登入協定 第 1 版

本文件定義網站、錢包 App 之間的登入協定。任何程式語言只要依照本文件實作，就能與錢包 App 互通。`walletlogin` 套件是這份協定的 Python 實作。

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

**QR Code 不可包含任何秘密**，因為它公開顯示在螢幕上。

### 錢包必須檢查

- `type`、`v` 正確，否則視為「不是登入用的 QR Code」
- `uri` 與 `verify_url` 都是 `http` 或 `https`，且網域（含 port）都等於 `domain`。否則拒絕，避免畫面顯示 A 網站，簽名卻送到 B 網站
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

請求：無內容

回應 `200`：
```json
{
  "session_id": "...",
  "poll_token": "...",
  "qr_payload": "{\"type\":\"wallet-login\",...}",
  "expires_in": 300
}
```

`poll_token` 只給網頁，**不可放進 QR Code**。

### ③ `POST {verify_url}`（錢包）

請求：
```json
{ "session_id": "...", "message": "簽名訊息原文", "signature": "0x..." }
```

回應：

| 狀態碼 | 意思 |
|---|---|
| `200` | `{"ok": true, "address": "0x..."}` 驗證成功 |
| `400` | 登入請求不存在或已過期、訊息格式錯誤、欄位不符 |
| `401` | 簽名驗證失敗 |
| `409` | 這個登入請求已經用過了 |

### ④ `POST /walletlogin/status`（網頁）

請求：
```json
{ "session_id": "...", "poll_token": "..." }
```

回應：

| 狀態碼 | 內容 |
|---|---|
| `200` | `{"status": "pending"}` 尚未簽名 |
| `200` | `{"status": "ok", "token": "JWT", "address": "0x..."}` 登入成功。**JWT 只發一次**，發出後登入請求即刪除 |
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
