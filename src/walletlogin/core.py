"""錢包登入的核心邏輯，不依賴任何網站框架。

三個動作對應登入流程的三個角色：
    create_session()  網頁：建立登入請求，取得 QR Code 內容
    verify()          手機：送出簽名，驗證身份
    poll()            網頁：詢問登入狀態，成功時取得 JWT

兩種登入模式：
    cross_device  電腦顯示 QR Code、手機掃描（預設）
    same_device   手機瀏覽器點按鈕開啟錢包 App。驗證成功時多產生一組兌換碼，
                  App 把它帶回同一支手機的瀏覽器，網頁必須出示兌換碼才能領取登入。
                  這樣就算駭客把自己發起的登入連結騙受害者點開，登入結果也不會落到駭客手上。

網站框架的轉接層（例如 walletlogin.fastapi）只負責把 HTTP 請求轉給這裡。
"""
import base64
import json
import secrets
import time
from typing import Callable, Optional
from urllib.parse import urlsplit

from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import to_checksum_address

from . import siwe
from .store import LoginSession, MemoryStore, SessionStore
from .tokens import InvalidToken, TokenIssuer

PROTOCOL_VERSION = 1
CROSS_DEVICE = "cross_device"
SAME_DEVICE = "same_device"
APP_LINK_PREFIX = "walletlogin://login?p="


class WalletLoginError(Exception):
    """登入失敗。status_code 對應建議的 HTTP 狀態碼，message 可以直接顯示給使用者。"""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class WalletLoginCore:
    def __init__(
        self,
        origin: str,
        secret: str,
        *,
        verify_path: str = "/walletlogin/verify",
        on_login: Optional[Callable[[str], object]] = None,
        store: Optional[SessionStore] = None,
        session_ttl: int = 300,
        token_ttl: int = 3600,
    ):
        """
        origin:      網站對外的網址，例如 "https://shop.example.com"。手機會看到並簽署這個網域
        secret:      簽發 JWT 用的密鑰，每個網站要有自己的
        verify_path: 手機送出簽名的路徑，會和 origin 組成 QR Code 中的 verify_url
        on_login:    登入成功時呼叫，參數為錢包地址，網站可以在這裡建立或更新會員
        store:       登入請求暫存，預設放在記憶體
        session_ttl: 登入請求（QR Code）的有效秒數
        token_ttl:   JWT 的有效秒數
        """
        self.origin = _normalize_origin(origin)
        self.domain = urlsplit(self.origin).netloc
        self.verify_url = self.origin + verify_path
        self._on_login = on_login
        self._store = store or MemoryStore()
        self._session_ttl = session_ttl
        self._tokens = TokenIssuer(secret, ttl_seconds=token_ttl)

    # ---------- 1. 網頁建立登入請求 ----------

    def create_session(self, mode: str = CROSS_DEVICE, return_url: Optional[str] = None) -> dict:
        """建立登入請求。

        mode=same_device 時必須提供 return_url（發起登入的網頁網址），而且必須屬於本網站，
        否則駭客可以把返回網址設成自己的網站，直接拿走兌換碼。
        """
        if mode == CROSS_DEVICE:
            return_url = None
        elif mode == SAME_DEVICE:
            return_url = self._check_return_url(return_url)
        else:
            raise WalletLoginError(400, "不支援的登入模式")

        session = LoginSession(
            session_id=secrets.token_urlsafe(16),
            nonce=secrets.token_hex(16),
            poll_token=secrets.token_urlsafe(32),
            expires_at=time.time() + self._session_ttl,
            mode=mode,
            return_url=return_url,
        )
        self._store.save(session)

        # QR Code / App 連結的內容：手機需要的所有資訊，沒有任何秘密（poll_token 不在裡面）
        payload = {
            "type": "wallet-login",
            "v": PROTOCOL_VERSION,
            "domain": self.domain,
            "uri": self.origin,
            "session_id": session.session_id,
            "nonce": session.nonce,
            "verify_url": self.verify_url,
        }
        if mode == SAME_DEVICE:
            payload["mode"] = SAME_DEVICE
            payload["return_url"] = return_url
        qr_payload = json.dumps(payload, separators=(",", ":"))

        result = {
            "session_id": session.session_id,
            "poll_token": session.poll_token,
            "qr_payload": qr_payload,
            "expires_in": self._session_ttl,
        }
        if mode == SAME_DEVICE:
            encoded = base64.urlsafe_b64encode(qr_payload.encode()).decode().rstrip("=")
            result["app_link"] = APP_LINK_PREFIX + encoded
        return result

    def _check_return_url(self, return_url: Optional[str]) -> str:
        if not return_url:
            raise WalletLoginError(400, "同一裝置登入需要返回網址")
        parts = urlsplit(return_url)
        if f"{parts.scheme}://{parts.netloc}" != self.origin:
            raise WalletLoginError(400, "返回網址必須屬於本網站")
        # 去掉 # 之後的內容，App 會把兌換碼放在那裡
        return return_url.split("#", 1)[0]

    # ---------- 2. 手機送出簽名 ----------

    def verify(self, session_id: str, message: str, signature: str) -> dict:
        """驗證簽名。成功時回傳 {"address": 錢包地址, "code": 兌換碼或 None}；失敗時拋出 WalletLoginError。

        code 只在 same_device 模式產生，要交給錢包 App 帶回瀏覽器。
        """
        # (1) 登入請求必須存在且未過期
        session = self._store.get(session_id)
        if session is None:
            raise WalletLoginError(400, "登入請求不存在或已過期，請重新整理網頁")

        # (2) 訊息內容必須跟這個登入請求完全對應
        try:
            msg = siwe.parse_message(message)
        except ValueError as e:
            raise WalletLoginError(400, str(e))
        if msg.request_id != session.session_id:
            raise WalletLoginError(400, "簽名訊息不屬於這個登入請求")
        if msg.domain != self.domain or msg.uri != self.origin:
            raise WalletLoginError(400, "簽名訊息的網站不符")
        if msg.nonce != session.nonce:
            raise WalletLoginError(400, "Nonce 不符")
        if msg.version != siwe.VERSION or msg.chain_id != siwe.CHAIN_ID:
            raise WalletLoginError(400, "簽名訊息版本不符")

        # (3) 由訊息與簽名反推簽署者地址（ECDSA），必須等於訊息中宣稱的地址
        try:
            recovered = Account.recover_message(encode_defunct(text=message), signature=signature)
        except Exception:
            raise WalletLoginError(400, "簽名格式不正確")
        if recovered.lower() != msg.address.lower():
            raise WalletLoginError(401, "簽名驗證失敗")

        # (4) 標記為已使用；同一個請求第二次送來會失敗（防重放攻擊）
        address = to_checksum_address(recovered)
        code = secrets.token_urlsafe(24) if session.mode == SAME_DEVICE else None
        if not self._store.mark_verified(session.session_id, address, code):
            raise WalletLoginError(409, "這個登入請求已經使用過了")

        if self._on_login is not None:
            self._on_login(address)
        return {"address": address, "code": code}

    # ---------- 3. 網頁詢問登入狀態 ----------

    def poll(self, session_id: str, poll_token: str, code: Optional[str] = None) -> dict:
        """回傳 {"status": "pending"}，或 {"status": "ok", "token": JWT, "address": 地址}。

        same_device 模式必須同時出示兌換碼；沒有兌換碼的一方（例如發起釣魚的駭客）永遠只會看到 pending。
        """
        session = self._store.get(session_id)
        if session is None or not secrets.compare_digest(session.poll_token, poll_token):
            raise WalletLoginError(404, "登入請求不存在或已過期")
        if session.address is None:
            return {"status": "pending"}
        if session.mode == SAME_DEVICE:
            if code is None:
                return {"status": "pending"}
            if not secrets.compare_digest(session.code, code):
                raise WalletLoginError(400, "兌換碼錯誤")

        # 驗證成功：發 JWT，並刪除登入請求，JWT 只會發一次
        self._store.delete(session.session_id)
        return {
            "status": "ok",
            "token": self._tokens.issue(session.address),
            "address": session.address,
        }

    # ---------- 登入後：檢查 JWT ----------

    def authenticate(self, token: str) -> str:
        """檢查 JWT，回傳登入者地址；無效時拋出 WalletLoginError(401)。"""
        try:
            return self._tokens.verify(token)
        except InvalidToken as e:
            raise WalletLoginError(401, e.message)


def _normalize_origin(origin: str) -> str:
    parts = urlsplit(origin.rstrip("/"))
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.path:
        raise ValueError(f"origin 必須是 http(s)://網域[:port]，不能有路徑：{origin!r}")
    return f"{parts.scheme}://{parts.netloc}"
