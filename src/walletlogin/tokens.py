"""JWT 登入憑證的簽發與檢查。"""
import time
import warnings

import jwt


class InvalidToken(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class TokenIssuer:
    def __init__(self, secret: str, ttl_seconds: int = 3600, algorithm: str = "HS256"):
        if len(secret.encode()) < 32:
            warnings.warn("JWT 密鑰太短，建議至少 32 個位元組", stacklevel=3)
        self._secret = secret
        self._ttl = ttl_seconds
        self._algorithm = algorithm

    def issue(self, address: str) -> str:
        now = int(time.time())
        payload = {"sub": address, "iat": now, "exp": now + self._ttl}
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def verify(self, token: str) -> str:
        """檢查 JWT，回傳登入者地址；無效或過期時拋出 InvalidToken。"""
        try:
            payload = jwt.decode(token, self._secret, algorithms=[self._algorithm])
        except jwt.ExpiredSignatureError:
            raise InvalidToken("登入已過期，請重新登入")
        except jwt.InvalidTokenError:
            raise InvalidToken("登入憑證無效")
        return payload["sub"]
