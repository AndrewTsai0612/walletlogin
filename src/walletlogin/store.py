"""登入請求（每個 QR Code 對應一個）的暫存。

一個登入請求的生命週期：
    1. 網頁要求登入 → save()，狀態 pending
    2. 手機簽名、驗證通過 → mark_verified()，記下地址
    3. 網頁詢問狀態、拿到 JWT → delete()，不能再用

預設的 MemoryStore 把資料放在記憶體：重啟網站時尚未完成的登入請求會失效。
網站如果有多台伺服器，可以照 SessionStore 的介面實作一個共用的版本（例如存在 Redis）。
"""
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class LoginSession:
    session_id: str
    nonce: str
    # 只有發起登入的網頁知道，用來詢問狀態；不放進 QR Code，避免旁人偷拍 QR 後搶走 JWT
    poll_token: str
    expires_at: float
    # 驗證成功後填入
    address: Optional[str] = None

    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class SessionStore:
    """登入請求暫存的介面。"""

    def save(self, session: LoginSession) -> None:
        raise NotImplementedError

    def get(self, session_id: str) -> Optional[LoginSession]:
        """取得尚未過期的登入請求；不存在或已過期回傳 None。"""
        raise NotImplementedError

    def mark_verified(self, session_id: str, address: str) -> bool:
        """標記為已驗證。同一個請求只能成功一次（防止重放攻擊），重複呼叫回傳 False。"""
        raise NotImplementedError

    def delete(self, session_id: str) -> None:
        raise NotImplementedError


class MemoryStore(SessionStore):
    def __init__(self):
        self._sessions: Dict[str, LoginSession] = {}
        # 確保「檢查是否用過」和「標記為已用」之間不會被其他請求插隊
        self._lock = threading.Lock()

    def save(self, session: LoginSession) -> None:
        with self._lock:
            self._cleanup()
            self._sessions[session.session_id] = session

    def get(self, session_id: str) -> Optional[LoginSession]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if session.is_expired():
                del self._sessions[session_id]
                return None
            return session

    def mark_verified(self, session_id: str, address: str) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.is_expired() or session.address is not None:
                return False
            session.address = address
            return True

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def _cleanup(self) -> None:
        expired = [sid for sid, s in self._sessions.items() if s.is_expired()]
        for sid in expired:
            del self._sessions[sid]
