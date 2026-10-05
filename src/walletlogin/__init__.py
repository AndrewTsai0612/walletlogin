"""walletlogin：以錢包簽章取代帳號密碼的無密碼登入套件。

框架無關的核心：
    from walletlogin import WalletLoginCore

FastAPI 網站：
    from walletlogin.fastapi import WalletLogin
"""
from .core import WalletLoginCore, WalletLoginError
from .store import LoginSession, MemoryStore, SessionStore

__all__ = ["WalletLoginCore", "WalletLoginError", "SessionStore", "MemoryStore", "LoginSession"]
__version__ = "0.3.0"
