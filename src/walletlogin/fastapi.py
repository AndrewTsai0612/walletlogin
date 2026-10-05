"""FastAPI 轉接層：把核心邏輯變成網站的 API。

用法：
    from walletlogin.fastapi import WalletLogin

    wallet_login = WalletLogin(origin="https://shop.example.com", secret="...", on_login=建立會員的函式)
    app.include_router(wallet_login.router)

    @app.get("/api/cart")
    def cart(address: str = Depends(wallet_login.current_user)):
        ...

加入的 API（prefix 預設為 /walletlogin）：
    POST {prefix}/session          網頁：建立登入請求
    POST {prefix}/verify           手機：送出簽名
    POST {prefix}/status           網頁：詢問登入狀態
    GET  {prefix}/walletlogin.js   前端元件
"""
from pathlib import Path
from typing import Callable, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from .core import WalletLoginCore, WalletLoginError
from .store import SessionStore

_STATIC_DIR = Path(__file__).parent / "static"


class SessionRequest(BaseModel):
    mode: str = "cross_device"  # "cross_device" | "same_device"
    return_url: Optional[str] = None  # same_device 模式：簽名後 App 要切回的網頁


class SessionResponse(BaseModel):
    session_id: str
    poll_token: str
    qr_payload: str
    expires_in: int
    app_link: Optional[str] = None  # same_device 模式：開啟錢包 App 的連結


class VerifyRequest(BaseModel):
    session_id: str
    message: str
    signature: str


class VerifyResponse(BaseModel):
    ok: bool
    address: str
    code: Optional[str] = None  # same_device 模式：兌換碼，錢包 App 要帶回瀏覽器


class StatusRequest(BaseModel):
    session_id: str
    poll_token: str
    code: Optional[str] = None  # same_device 模式必填


class StatusResponse(BaseModel):
    status: str  # "pending" | "ok"
    token: Optional[str] = None
    address: Optional[str] = None


class WalletLogin:
    def __init__(
        self,
        origin: str,
        secret: str,
        *,
        prefix: str = "/walletlogin",
        on_login: Optional[Callable[[str], object]] = None,
        store: Optional[SessionStore] = None,
        session_ttl: int = 300,
        token_ttl: int = 3600,
    ):
        self.core = WalletLoginCore(
            origin,
            secret,
            verify_path=prefix + "/verify",
            on_login=on_login,
            store=store,
            session_ttl=session_ttl,
            token_ttl=token_ttl,
        )
        self.router = self._build_router(prefix)

    def current_user(
        self, credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
    ) -> str:
        """FastAPI 依賴：從 Authorization: Bearer <JWT> 取出登入者地址，未登入回 401。"""
        if credentials is None:
            raise HTTPException(status_code=401, detail="尚未登入")
        try:
            return self.core.authenticate(credentials.credentials)
        except WalletLoginError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

    def _build_router(self, prefix: str) -> APIRouter:
        router = APIRouter(prefix=prefix, tags=["walletlogin"])
        core = self.core

        @router.post("/session", response_model=SessionResponse)
        def create_session(body: Optional[SessionRequest] = None):
            body = body or SessionRequest()
            try:
                return core.create_session(body.mode, body.return_url)
            except WalletLoginError as e:
                raise HTTPException(status_code=e.status_code, detail=e.message)

        @router.post("/verify", response_model=VerifyResponse)
        def verify(body: VerifyRequest):
            try:
                result = core.verify(body.session_id, body.message, body.signature)
            except WalletLoginError as e:
                raise HTTPException(status_code=e.status_code, detail=e.message)
            return VerifyResponse(ok=True, address=result["address"], code=result["code"])

        @router.post("/status", response_model=StatusResponse)
        def status(body: StatusRequest):
            try:
                return core.poll(body.session_id, body.poll_token, body.code)
            except WalletLoginError as e:
                raise HTTPException(status_code=e.status_code, detail=e.message)

        @router.get("/walletlogin.js", include_in_schema=False)
        def script():
            # 前端元件與它使用的 QR Code 函式庫合併成一個檔案，網站只要載入一次
            js = (_STATIC_DIR / "qrcode.min.js").read_text() + "\n" + (
                _STATIC_DIR / "walletlogin.js"
            ).read_text()
            return Response(js, media_type="application/javascript")

        return router
