"""核心登入流程與攻擊情境的測試（不經過任何網站框架）。"""
import json
import time

import pytest
from eth_account import Account

from walletlogin import WalletLoginCore, WalletLoginError
from walletlogin.testing import make_test_account, sign_login

SECRET = "test-secret-" + "x" * 32
ORIGIN = "http://192.168.1.10:8000"


@pytest.fixture
def core():
    return WalletLoginCore(ORIGIN, SECRET)


@pytest.fixture
def wallet():
    return make_test_account()


def _verify(core, payload):
    return core.verify(payload["session_id"], payload["message"], payload["signature"])


def _error_code(fn, *args):
    with pytest.raises(WalletLoginError) as e:
        fn(*args)
    return e.value.status_code


def test_full_login_flow(core, wallet):
    s = core.create_session()
    assert core.poll(s["session_id"], s["poll_token"]) == {"status": "pending"}

    assert _verify(core, sign_login(wallet, s["qr_payload"])) == wallet.address

    result = core.poll(s["session_id"], s["poll_token"])
    assert result["status"] == "ok"
    assert result["address"] == wallet.address
    assert core.authenticate(result["token"]) == wallet.address


def test_qr_payload_format(core):
    s = core.create_session()
    qr = json.loads(s["qr_payload"])
    assert qr["type"] == "wallet-login"
    assert qr["v"] == 1
    assert qr["domain"] == "192.168.1.10:8000"
    assert qr["uri"] == ORIGIN
    assert qr["verify_url"] == ORIGIN + "/walletlogin/verify"
    assert s["poll_token"] not in s["qr_payload"]


def test_on_login_called_once(wallet):
    logins = []
    core = WalletLoginCore(ORIGIN, SECRET, on_login=logins.append)
    s = core.create_session()
    _verify(core, sign_login(wallet, s["qr_payload"]))
    assert logins == [wallet.address]


def test_replay_same_signature_fails(core, wallet):
    s = core.create_session()
    payload = sign_login(wallet, s["qr_payload"])
    _verify(core, payload)
    assert _error_code(_verify, core, payload) == 409


def test_jwt_is_issued_only_once(core, wallet):
    s = core.create_session()
    _verify(core, sign_login(wallet, s["qr_payload"]))
    assert core.poll(s["session_id"], s["poll_token"])["status"] == "ok"
    assert _error_code(core.poll, s["session_id"], s["poll_token"]) == 404


def test_signature_from_other_key_fails(core, wallet):
    s = core.create_session()
    payload = sign_login(wallet, s["qr_payload"])
    forged = sign_login(Account.create(), s["qr_payload"], address=wallet.address)
    payload["signature"] = forged["signature"]
    assert _error_code(_verify, core, payload) == 401


def test_tampered_message_fails(core, wallet):
    s = core.create_session()
    payload = sign_login(wallet, s["qr_payload"])
    payload["message"] = payload["message"].replace("Version: 1", "Version: 1 ")
    assert _error_code(_verify, core, payload) in (400, 401)


def test_wrong_domain_fails(core, wallet):
    s = core.create_session()
    payload = sign_login(wallet, s["qr_payload"], domain="evil.example.com")
    assert _error_code(_verify, core, payload) == 400


def test_wrong_nonce_fails(core, wallet):
    s = core.create_session()
    payload = sign_login(wallet, s["qr_payload"], nonce="0000000000000000")
    assert _error_code(_verify, core, payload) == 400


def test_signature_for_other_session_fails(core, wallet):
    s1 = core.create_session()
    s2 = core.create_session()
    payload = sign_login(wallet, s1["qr_payload"])
    payload["session_id"] = s2["session_id"]
    assert _error_code(_verify, core, payload) == 400


def test_signature_for_other_site_fails(wallet):
    """A 網站的簽名不能拿到 B 網站使用。"""
    site_a = WalletLoginCore("http://a.example.com", SECRET)
    site_b = WalletLoginCore("http://b.example.com", SECRET)
    s_a = site_a.create_session()
    s_b = site_b.create_session()
    payload = sign_login(wallet, s_a["qr_payload"])
    payload["session_id"] = s_b["session_id"]
    assert _error_code(_verify, site_b, payload) == 400


def test_expired_session_fails(core, wallet):
    s = core.create_session()
    core._store.get(s["session_id"]).expires_at = time.time() - 1
    assert _error_code(_verify, core, sign_login(wallet, s["qr_payload"])) == 400


def test_wrong_poll_token_cannot_steal_jwt(core, wallet):
    s = core.create_session()
    _verify(core, sign_login(wallet, s["qr_payload"]))
    assert _error_code(core.poll, s["session_id"], "guess") == 404


def test_invalid_token_rejected(core):
    assert _error_code(core.authenticate, "nope") == 401


def test_token_from_other_site_rejected(core, wallet):
    other = WalletLoginCore(ORIGIN, "another-secret-" + "y" * 32)
    s = other.create_session()
    _verify(other, sign_login(wallet, s["qr_payload"]))
    token = other.poll(s["session_id"], s["poll_token"])["token"]
    assert _error_code(core.authenticate, token) == 401


@pytest.mark.parametrize(
    "origin", ["ftp://example.com", "example.com", "http://example.com/login", "http://"]
)
def test_invalid_origin_rejected(origin):
    with pytest.raises(ValueError):
        WalletLoginCore(origin, SECRET)


def test_origin_trailing_slash_normalized():
    core = WalletLoginCore("https://shop.example.com/", SECRET)
    assert core.origin == "https://shop.example.com"
    assert core.domain == "shop.example.com"
