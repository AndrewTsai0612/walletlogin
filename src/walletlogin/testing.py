"""測試工具：模擬錢包 App 簽名，讓網站不用手機也能測試登入流程。"""
import json
from datetime import datetime, timezone

from eth_account.messages import encode_defunct

from . import siwe

# 公開的測試助記詞（Hardhat 預設），地址為 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
# 只能用於測試，任何人都知道這組助記詞
TEST_MNEMONIC = "test test test test test test test test test test test junk"
DERIVATION_PATH = "m/44'/60'/0'/0/0"


def make_test_account():
    """回傳測試助記詞推導出的帳戶（與錢包 App 使用相同的推導路徑）。"""
    from eth_account import Account

    Account.enable_unaudited_hdwallet_features()
    return Account.from_mnemonic(TEST_MNEMONIC, account_path=DERIVATION_PATH)


def sign_login(account, qr_payload: str, **overrides) -> dict:
    """模擬錢包 App：讀取 QR Code 內容、組訊息、簽名。

    回傳要 POST 到 QR Code 中 verify_url 的內容。
    overrides 可以竄改訊息欄位，用來測試攻擊情境。
    """
    qr = json.loads(qr_payload)
    fields = dict(
        domain=qr["domain"],
        address=account.address,
        statement=siwe.STATEMENT,
        uri=qr["uri"],
        version=siwe.VERSION,
        chain_id=siwe.CHAIN_ID,
        nonce=qr["nonce"],
        issued_at=datetime.now(timezone.utc).isoformat(),
        request_id=qr["session_id"],
    )
    fields.update(overrides)
    message = siwe.build_message(siwe.SiweMessage(**fields))
    signature = account.sign_message(encode_defunct(text=message)).signature.hex()
    return {"session_id": qr["session_id"], "message": message, "signature": signature}
