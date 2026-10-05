"""同一裝置登入（手機瀏覽器點按鈕開啟錢包 App）與兌換碼的測試。"""
import base64
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from walletlogin import WalletLoginCore, WalletLoginError
from walletlogin.fastapi import WalletLogin
from walletlogin.testing import make_test_account, sign_login

SECRET = "test-secret-" + "x" * 32
ORIGIN = "http://192.168.1.10:8000"
RETURN_URL = ORIGIN + "/index.html"


@pytest.fixture
def core():
    return WalletLoginCore(ORIGIN, SECRET)


@pytest.fixture
def wallet():
    return make_test_account()


def _sign_and_verify(core, wallet, session):
    payload = sign_login(wallet, session["qr_payload"])
    return core.verify(payload["session_id"], payload["message"], payload["signature"])


def _decode_app_link(link: str) -> dict:
    encoded = link.split("?p=", 1)[1]
    return json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))


def test_full_same_device_flow(core, wallet):
    s = core.create_session("same_device", RETURN_URL)
    result = _sign_and_verify(core, wallet, s)
    assert result["address"] == wallet.address
    assert result["code"]

    ok = core.poll(s["session_id"], s["poll_token"], result["code"])
    assert ok["status"] == "ok"
    assert core.authenticate(ok["token"]) == wallet.address


def test_app_link_contains_same_payload(core):
    s = core.create_session("same_device", RETURN_URL)
    assert s["app_link"].startswith("walletlogin://login?p=")
    payload = _decode_app_link(s["app_link"])
    assert payload == json.loads(s["qr_payload"])
    assert payload["mode"] == "same_device"
    assert payload["return_url"] == RETURN_URL
    assert s["poll_token"] not in s["app_link"]


def test_without_code_stays_pending(core, wallet):
    s = core.create_session("same_device", RETURN_URL)
    _sign_and_verify(core, wallet, s)
    assert core.poll(s["session_id"], s["poll_token"]) == {"status": "pending"}


def test_wrong_code_rejected(core, wallet):
    s = core.create_session("same_device", RETURN_URL)
    _sign_and_verify(core, wallet, s)
    with pytest.raises(WalletLoginError) as e:
        core.poll(s["session_id"], s["poll_token"], "guess")
    assert e.value.status_code == 400


def test_phishing_attacker_cannot_get_login(core, wallet):
    """駭客自己發起登入、把連結騙受害者點開；受害者簽了名，駭客仍然拿不到登入。"""
    attacker = core.create_session("same_device", RETURN_URL)  # 駭客的瀏覽器持有 poll_token
    victim_result = _sign_and_verify(core, wallet, attacker)  # 兌換碼回到受害者的手機
    assert victim_result["code"]

    for _ in range(3):  # 駭客一直詢問，永遠只看到 pending
        assert core.poll(attacker["session_id"], attacker["poll_token"]) == {"status": "pending"}


def test_code_is_single_use(core, wallet):
    s = core.create_session("same_device", RETURN_URL)
    code = _sign_and_verify(core, wallet, s)["code"]
    assert core.poll(s["session_id"], s["poll_token"], code)["status"] == "ok"
    with pytest.raises(WalletLoginError) as e:
        core.poll(s["session_id"], s["poll_token"], code)
    assert e.value.status_code == 404


@pytest.mark.parametrize(
    "return_url",
    [
        None,
        "",
        "http://evil.example.com/steal",  # 別的網站：兌換碼會被送到駭客手上
        "https://192.168.1.10:8000/",  # 協定不同
        "http://192.168.1.10:9999/",  # port 不同
        "walletlogin://login",
    ],
)
def test_return_url_must_belong_to_site(core, return_url):
    with pytest.raises(WalletLoginError) as e:
        core.create_session("same_device", return_url)
    assert e.value.status_code == 400


def test_return_url_fragment_removed(core):
    s = core.create_session("same_device", RETURN_URL + "#old")
    assert _decode_app_link(s["app_link"])["return_url"] == RETURN_URL


def test_unknown_mode_rejected(core):
    with pytest.raises(WalletLoginError):
        core.create_session("teleport")


def test_cross_device_has_no_code_or_link(core, wallet):
    s = core.create_session()
    assert "app_link" not in s
    assert "mode" not in json.loads(s["qr_payload"])
    assert _sign_and_verify(core, wallet, s)["code"] is None


def test_fastapi_same_device_flow(wallet):
    app = FastAPI()
    wallet_login = WalletLogin("http://testserver", SECRET)
    app.include_router(wallet_login.router)
    client = TestClient(app)

    s = client.post(
        "/walletlogin/session",
        json={"mode": "same_device", "return_url": "http://testserver/index.html"},
    ).json()
    assert s["app_link"].startswith("walletlogin://login?p=")

    verify = client.post("/walletlogin/verify", json=sign_login(wallet, s["qr_payload"])).json()
    code = verify["code"]
    assert code

    status_url = "/walletlogin/status"
    base = {"session_id": s["session_id"], "poll_token": s["poll_token"]}
    assert client.post(status_url, json=base).json()["status"] == "pending"
    assert client.post(status_url, json={**base, "code": "guess"}).status_code == 400
    assert client.post(status_url, json={**base, "code": code}).json()["status"] == "ok"

    bad = client.post(
        "/walletlogin/session", json={"mode": "same_device", "return_url": "http://evil.com/"}
    )
    assert bad.status_code == 400
