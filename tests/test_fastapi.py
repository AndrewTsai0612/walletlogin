"""FastAPI 轉接層的測試：模擬一個安裝了套件的網站。"""
import json

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from walletlogin.fastapi import WalletLogin
from walletlogin.testing import make_test_account, sign_login

SECRET = "test-secret-" + "x" * 32


def _make_site(prefix="/walletlogin"):
    logins = []
    app = FastAPI()
    wallet_login = WalletLogin(
        "http://testserver", SECRET, prefix=prefix, on_login=logins.append
    )
    app.include_router(wallet_login.router)

    @app.get("/api/secret")
    def secret(address: str = Depends(wallet_login.current_user)):
        return {"address": address}

    return TestClient(app), logins


@pytest.fixture
def wallet():
    return make_test_account()


def _login(client, wallet, prefix="/walletlogin"):
    s = client.post(f"{prefix}/session").json()
    qr = json.loads(s["qr_payload"])
    res = client.post(qr["verify_url"].replace("http://testserver", ""), json=sign_login(wallet, s["qr_payload"]))
    assert res.status_code == 200, res.text
    body = client.post(
        f"{prefix}/status", json={"session_id": s["session_id"], "poll_token": s["poll_token"]}
    ).json()
    assert body["status"] == "ok"
    return body["token"]


def test_full_flow_and_protected_api(wallet):
    client, logins = _make_site()
    token = _login(client, wallet)
    assert logins == [wallet.address]
    res = client.get("/api/secret", headers={"Authorization": f"Bearer {token}"})
    assert res.json() == {"address": wallet.address}


def test_custom_prefix(wallet):
    client, _ = _make_site(prefix="/auth/wallet")
    s = client.post("/auth/wallet/session").json()
    assert json.loads(s["qr_payload"])["verify_url"] == "http://testserver/auth/wallet/verify"
    _login(client, wallet, prefix="/auth/wallet")


def test_protected_api_requires_login():
    client, _ = _make_site()
    assert client.get("/api/secret").status_code == 401
    assert client.get("/api/secret", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_errors_become_http_status(wallet):
    client, _ = _make_site()
    s = client.post("/walletlogin/session").json()
    payload = sign_login(wallet, s["qr_payload"])
    assert client.post("/walletlogin/verify", json=payload).status_code == 200
    res = client.post("/walletlogin/verify", json=payload)
    assert res.status_code == 409
    assert res.json()["detail"] == "這個登入請求已經使用過了"


def test_serves_frontend_script():
    client, _ = _make_site()
    res = client.get("/walletlogin/walletlogin.js")
    assert res.status_code == 200
    assert "javascript" in res.headers["content-type"]
    assert "window.WalletLogin" in res.text
    assert "var qrcode" in res.text  # QR Code 函式庫已一併提供
