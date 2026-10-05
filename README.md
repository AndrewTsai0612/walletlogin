# walletlogin

**以錢包簽章取代帳號密碼的無密碼登入套件。**

使用者用手機錢包 App 掃描網站上的 QR Code、簽名，就能登入。網站不儲存任何密碼，也不需要向任何第三方（例如 Google）註冊。

```
網站 A 的伺服器（裝了 walletlogin）←─┐
網站 B 的伺服器（裝了 walletlogin）←─┼── 同一個錢包 App
網站 C 的伺服器（裝了 walletlogin）←─┘
```

每個網站**自己驗證簽名**，中間沒有任何人，包括這個套件的作者。

---

## 五分鐘上手（FastAPI）

### 1. 安裝

```bash
pip install -e path/to/walletlogin   # 本機開發
```

> 發布到 GitHub 後改用 `pip install git+https://github.com/<帳號>/walletlogin.git`

### 2. 後端：加入錢包登入

```python
from fastapi import Depends, FastAPI
from walletlogin.fastapi import WalletLogin

app = FastAPI()

def on_login(address: str):
    # 登入成功時呼叫：在這裡建立或更新你的網站會員
    ...

wallet_login = WalletLogin(
    origin="https://shop.example.com",   # 你的網站網址，手機要連得到
    secret="至少 32 個字元的隨機密鑰",       # 簽發登入憑證（JWT）用，不可外流
    on_login=on_login,
)
app.include_router(wallet_login.router)

# 需要登入才能使用的 API
@app.get("/api/cart")
def cart(address: str = Depends(wallet_login.current_user)):
    return {"owner": address}
```

### 3. 前端：放上登入元件

```html
<div id="login"></div>
<script src="/walletlogin/walletlogin.js"></script>
<script>
  WalletLogin.mount("#login", {
    onSuccess: function (token, address) {
      // token 是 JWT，之後呼叫需要登入的 API 時放在 Authorization: Bearer <token>
      sessionStorage.setItem("token", token);
      location.href = "/cart.html";
    },
  });
</script>
```

完成。使用者打開網頁會看到 QR Code，用錢包 App 掃描、簽名後就會登入。

---

## 套件負責什麼、網站負責什麼

| 事情 | 誰負責 |
|---|---|
| 產生登入請求、Nonce、驗證簽名、防重放、檢查過期 | 套件 |
| 顯示 QR Code、倒數、詢問狀態、過期後重新產生 | 套件（前端元件） |
| 登入成功後要做什麼（建立會員、記錄登入） | 網站（`on_login`） |
| 使用者資料要存什麼 | 網站 |
| 網站畫面 | 網站（元件可以調整顏色） |

網站拿到的**只有錢包地址**，沒有 Email、沒有姓名、沒有密碼。

---

## 設定選項

### `WalletLogin(...)`（後端）

| 參數 | 必填 | 預設 | 說明 |
|---|---|---|---|
| `origin` | ✅ | | 網站對外的網址，例如 `https://shop.example.com`。會顯示在手機上讓使用者確認，**必須明確設定**，不從請求自動判斷，避免被偽造的請求標頭欺騙 |
| `secret` | ✅ | | 簽發 JWT 的密鑰，每個網站要有自己的，建議至少 32 個字元 |
| `prefix` | | `/walletlogin` | 套件 API 的路徑 |
| `on_login` | | 無 | 登入成功時呼叫，參數為錢包地址 |
| `store` | | 記憶體 | 登入請求暫存，見下方「多台伺服器」 |
| `session_ttl` | | `300` | QR Code 有效秒數 |
| `token_ttl` | | `3600` | 登入憑證（JWT）有效秒數 |

### `WalletLogin.mount(target, options)`（前端）

| 選項 | 預設 | 說明 |
|---|---|---|
| `onSuccess(token, address)` | | 登入成功時呼叫 |
| `basePath` | `/walletlogin` | 要和後端的 `prefix` 相同 |
| `pollInterval` | `1500` | 詢問登入狀態的間隔（毫秒） |
| `debug` | `false` | 顯示 QR Code 原始內容，開發測試用 |

外觀可以用 CSS 變數調整：

```css
#login {
  --wl-accent: #e91e63;   /* 按鈕顏色 */
  --wl-qr-size: 200px;    /* QR Code 大小 */
  /* 另有 --wl-ok、--wl-error、--wl-muted、--wl-border */
}
```

---

## 加入的 API

| 方法 | 路徑 | 誰呼叫 | 用途 |
|---|---|---|---|
| POST | `{prefix}/session` | 網頁 | 建立登入請求，回傳 QR Code 內容 |
| POST | `{prefix}/verify` | 手機 | 送出簽名 |
| POST | `{prefix}/status` | 網頁 | 詢問登入狀態，成功時取得 JWT |
| GET | `{prefix}/walletlogin.js` | 網頁 | 前端元件 |

詳細格式見 [PROTOCOL.md](PROTOCOL.md)。

---

## 不使用 FastAPI？

核心邏輯不依賴任何框架，可以自己接到 Flask、Django 等：

```python
from walletlogin import WalletLoginCore, WalletLoginError

core = WalletLoginCore(origin="https://shop.example.com", secret="...", verify_path="/walletlogin/verify")

core.create_session()                           # → dict，回傳給網頁
core.verify(session_id, message, signature)     # → 錢包地址；失敗時拋出 WalletLoginError
core.poll(session_id, poll_token)               # → {"status": "pending"} 或 {"status": "ok", "token": ..., "address": ...}
core.authenticate(jwt)                          # → 錢包地址；無效時拋出 WalletLoginError
```

`WalletLoginError.status_code` 是建議的 HTTP 狀態碼，`message` 可以直接顯示給使用者。

其他程式語言可以依照 [PROTOCOL.md](PROTOCOL.md) 自行實作。

---

## 多台伺服器

預設把登入請求放在記憶體，只適用單一伺服器。網站有多台伺服器時，照 `walletlogin.SessionStore` 的四個方法（`save`、`get`、`mark_verified`、`delete`）實作一個共用的版本（例如存在 Redis），再傳給 `store=`。

`mark_verified` 必須是**原子操作**：同一個登入請求只能成功一次，這是防止重放攻擊的關鍵。

---

## 測試你的網站（不用手機）

```python
from walletlogin.testing import make_test_account, sign_login

wallet = make_test_account()                         # 公開的測試帳號，只能用於測試
payload = sign_login(wallet, qr_payload)             # 模擬錢包 App 簽名
client.post("/walletlogin/verify", json=payload)
```

---

## 安全性

- **網站只存公開地址**：資料庫外洩也拿不到能拿去登入的東西
- **每次登入的訊息都不同**（一次性 Nonce），舊簽名無法重複使用
- **簽名綁定網站網域**：A 網站的簽名不能拿到 B 網站使用
- **QR Code 不含秘密**：網頁領取 JWT 需要另一組只有它知道的 `poll_token`，旁人偷拍 QR Code 也搶不走登入
- **正式上線必須使用 HTTPS**

---

## 程式結構（給維護者）

```
walletlogin/
├── README.md                 ← 本文件
├── PROTOCOL.md               ← 協定規格
├── pyproject.toml            ← 套件設定：名稱、版本、相依套件（pip install 靠它）
├── src/walletlogin/
│   ├── __init__.py           ← 對外公開的名稱
│   ├── core.py               ← ★ 核心：建立登入請求、驗證簽名、查詢狀態
│   ├── siwe.py               ← 簽名訊息的格式（組合／拆解）
│   ├── store.py              ← 登入請求暫存
│   ├── tokens.py             ← JWT 簽發與檢查
│   ├── fastapi.py            ← FastAPI 轉接層
│   ├── testing.py            ← 測試工具：模擬錢包簽名
│   └── static/
│       ├── walletlogin.js    ← 前端元件
│       ├── qrcode.min.js     ← QR Code 函式庫（第三方，MIT）
│       └── THIRD_PARTY_NOTICES.md
└── tests/
    ├── test_core.py          ← 核心流程與攻擊情境（20 項）
    ├── test_fastapi.py       ← 轉接層（5 項）
    └── test_dart_compat.py   ← 錢包 App 的簽名能被正確驗證（2 項）
```

### [core.py](src/walletlogin/core.py)：核心

[`WalletLoginCore`](src/walletlogin/core.py:36) 有四個方法，對應登入流程的每一步：

| 方法 | 誰觸發 | 做什麼 |
|---|---|---|
| [`create_session`](src/walletlogin/core.py:67) | 網頁 | 產生 `session_id`、`nonce`、`poll_token`，組出 QR Code 內容 |
| [`verify`](src/walletlogin/core.py:98) | 手機 | 驗證簽名（四道檢查，見下表），成功後呼叫 `on_login` |
| [`poll`](src/walletlogin/core.py:138) | 網頁 | 回報登入狀態；成功時發 JWT 並刪除登入請求 |
| [`authenticate`](src/walletlogin/core.py:156) | 網站 API | 檢查 JWT，回傳登入者地址 |

`verify` 的四道檢查：

| 步驟 | 程式位置 | 檢查什麼 | 擋住什麼攻擊 |
|---|---|---|---|
| (1) | [第 100 行](src/walletlogin/core.py:100) | 登入請求存在且沒過期 | 過期或捏造的請求 |
| (2) | [第 105 行](src/walletlogin/core.py:105) | 訊息中的網域、網址、Nonce、Request ID、版本都與登入請求一致 | 拿別的網站、別的登入請求的簽名來用 |
| (3) | [第 119 行](src/walletlogin/core.py:119) | 從簽名**反推**簽署者地址，必須等於訊息中的地址 | 偽造簽名、竄改訊息 |
| (4) | [第 127 行](src/walletlogin/core.py:127) | 這個登入請求還沒被用過 | 重放攻擊 |

[`_normalize_origin`](src/walletlogin/core.py:164) 檢查網站網址格式（必須是 `http(s)://網域`，不能有路徑）。

### [siwe.py](src/walletlogin/siwe.py)：簽名訊息格式

| 名稱 | 做什麼 |
|---|---|
| `STATEMENT`、`VERSION`、`CHAIN_ID` | 訊息中的固定欄位 |
| `SiweMessage` | 訊息的 9 個欄位 |
| `build_message` | 欄位 → 文字（測試工具使用） |
| `parse_message` | 文字 → 欄位，用正規表示式拆解，格式不對就拋出錯誤 |

⚠️ 格式必須和錢包 App（`wallet_app/lib/services/login_service.dart` 的 `buildSiweMessage`）**一字不差**。`test_dart_compat.py` 用 App 產生的真實簽名確保這件事。

### [store.py](src/walletlogin/store.py)：登入請求暫存

- [`LoginSession`](src/walletlogin/store.py:18)：一個登入請求，記錄 `session_id`、`nonce`、`poll_token`、過期時間、驗證後的地址
- [`SessionStore`](src/walletlogin/store.py:31)：暫存的介面（四個方法）
- [`MemoryStore`](src/walletlogin/store.py:49)：預設實作，存在記憶體。用 `threading.Lock` 確保 [`mark_verified`](src/walletlogin/store.py:70) 的「檢查是否用過」和「標記為已用」不會被插隊

### [tokens.py](src/walletlogin/tokens.py)：JWT

[`TokenIssuer`](src/walletlogin/tokens.py:14) 的 `issue` 產生 JWT（內容：地址、簽發時間、過期時間），`verify` 檢查簽章與過期。密鑰短於 32 位元組會發出警告。

### [fastapi.py](src/walletlogin/fastapi.py)：FastAPI 轉接層

[`WalletLogin`](src/walletlogin/fastapi.py:62) 建立一個 `WalletLoginCore`，再把它包成 4 個 API（`router`）。核心拋出的 `WalletLoginError` 會轉成對應的 HTTP 錯誤。

[`current_user`](src/walletlogin/fastapi.py:85) 是 FastAPI 的「依賴」：`Depends(wallet_login.current_user)` 表示執行 API 前先檢查 JWT，沒登入就直接回 401，有登入就把地址傳進來。

`/walletlogin.js` 會把 `qrcode.min.js` 和 `walletlogin.js` 合併成一個檔案回傳，網站只要載入一次。

### [static/walletlogin.js](src/walletlogin/static/walletlogin.js)：前端元件

[`mount`](src/walletlogin/static/walletlogin.js:54) 在指定的元素裡畫出 QR Code、狀態文字、倒數、重新產生按鈕：

| 函式 | 做什麼 |
|---|---|
| [`start`](src/walletlogin/static/walletlogin.js:116) | 呼叫 `/session` → 畫 QR Code → 開始倒數 → 每 1.5 秒呼叫 `poll` |
| [`poll`](src/walletlogin/static/walletlogin.js:148) | 呼叫 `/status`，成功時呼叫網站的 `onSuccess(token, address)` |
| [`renderQr`](src/walletlogin/static/walletlogin.js:92) | 用 QR Code 函式庫畫出 SVG 圖片 |
| [`showExpired`](src/walletlogin/static/walletlogin.js:100) | QR Code 過期：圖片變淡，顯示「重新產生」按鈕 |

樣式以 `<style id="wl-style">` 注入頁面，所有 class 都以 `wl-` 開頭，避免和網站原本的樣式衝突。

### [testing.py](src/walletlogin/testing.py)：測試工具

- `make_test_account()`：用公開的測試助記詞產生帳號（地址 `0xf39F…2266`），推導路徑與錢包 App 相同
- `sign_login(account, qr_payload, **overrides)`：模擬錢包 App 組訊息並簽名。`overrides` 可以竄改欄位，用來測試攻擊情境

## 開發

```bash
pip install -e ".[dev]"
pytest
```

## 第三方程式

前端元件內含 [qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator)（MIT License），見 `src/walletlogin/static/THIRD_PARTY_NOTICES.md`。
