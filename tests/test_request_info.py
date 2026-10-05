"""發起裝置資訊的測試：錢包 App 用它判斷 QR Code 是不是被轉貼到假網站。"""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from walletlogin import WalletLoginCore, WalletLoginError
from walletlogin.device import describe_user_agent
from walletlogin.fastapi import WalletLogin

SECRET = "test-secret-" + "x" * 32
ORIGIN = "http://192.168.1.10:8000"

CHROME_MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
EDGE_WINDOWS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0"
)
SAFARI_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
)
SAMSUNG_ANDROID = (
    "Mozilla/5.0 (Linux; Android 16; SM-S918B) AppleWebKit/537.36 "
    "(KHTML, like Gecko) SamsungBrowser/28.0 Chrome/130.0.0.0 Mobile Safari/537.36"
)
FIREFOX_LINUX = "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"


@pytest.mark.parametrize(
    "ua, expected",
    [
        (CHROME_MAC, ("Chrome", "macOS")),
        (EDGE_WINDOWS, ("Edge", "Windows")),
        (SAFARI_IPHONE, ("Safari", "iOS")),
        (SAMSUNG_ANDROID, ("Samsung Internet", "Android")),
        (FIREFOX_LINUX, ("Firefox", "Linux")),
        ("", ("未知瀏覽器", "未知系統")),
        ("curl/8.0", ("未知瀏覽器", "未知系統")),
    ],
)
def test_describe_user_agent(ua, expected):
    assert describe_user_agent(ua) == expected


def test_request_info_from_server():
    core = WalletLoginCore(ORIGIN, SECRET)
    s = core.create_session(user_agent=EDGE_WINDOWS, ip="203.0.113.45")
    info = core.request_info(s["session_id"])
    assert info["browser"] == "Edge"
    assert info["os"] == "Windows"
    assert info["ip"] == "203.0.113.45"
    assert 0 <= info["age_seconds"] <= 2
    assert info["mode"] == "cross_device"


def test_info_url_in_qr_but_requester_not():
    """QR Code 只放查詢網址，不放裝置資訊：QR Code 可以被竄改，網站回報的不行。"""
    core = WalletLoginCore(ORIGIN, SECRET)
    s = core.create_session(user_agent=EDGE_WINDOWS, ip="203.0.113.45")
    payload = json.loads(s["qr_payload"])
    assert payload["info_url"] == ORIGIN + "/walletlogin/info"
    assert "203.0.113.45" not in s["qr_payload"]
    assert "Edge" not in s["qr_payload"]


def test_unknown_session_info():
    core = WalletLoginCore(ORIGIN, SECRET)
    with pytest.raises(WalletLoginError) as e:
        core.request_info("nope")
    assert e.value.status_code == 404


def test_missing_requester_shows_unknown():
    core = WalletLoginCore(ORIGIN, SECRET)
    s = core.create_session()
    info = core.request_info(s["session_id"])
    assert (info["browser"], info["os"], info["ip"]) == ("未知瀏覽器", "未知系統", "未知")


def test_fastapi_records_requesting_browser():
    app = FastAPI()
    wallet_login = WalletLogin("http://testserver", SECRET, prefix="/auth")
    app.include_router(wallet_login.router)
    client = TestClient(app)

    s = client.post("/auth/session", headers={"User-Agent": CHROME_MAC}).json()
    payload = json.loads(s["qr_payload"])
    assert payload["info_url"] == "http://testserver/auth/info"

    info = client.get("/auth/info", params={"session_id": s["session_id"]}).json()
    assert info["browser"] == "Chrome"
    assert info["os"] == "macOS"
    assert info["ip"] == "testclient"  # TestClient 的連線位址
    assert client.get("/auth/info", params={"session_id": "nope"}).status_code == 404
