"""確認 Flutter 錢包 App 產生的簽名，後端可以正確驗證。

簽名由 wallet_app/test/wallet_service_test.dart 以相同的測試助記詞產生。
"""
from eth_account import Account
from eth_account.messages import encode_defunct

from walletlogin.siwe import parse_message

DART_MESSAGE = (
    "192.168.1.10:8000 wants you to sign in with your Ethereum account:\n"
    "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266\n"
    "\n"
    "Sign in with your wallet. This request will not trigger any transaction.\n"
    "\n"
    "URI: http://192.168.1.10:8000\n"
    "Version: 1\n"
    "Chain ID: 1\n"
    "Nonce: 0123456789abcdef\n"
    "Issued At: 2026-10-01T00:00:00.000Z\n"
    "Request ID: abc"
)
DART_SIGNATURE = "0x6fc7afd63b1d6ca966ddf358fde095947380d8bf1dc5f65a535c7528666ea3335f8eadfd59727f12cd6412b076dbd1aed1cbeb551305a3ee8fe21e19682ac0cc1c"


def test_dart_message_format_parses():
    msg = parse_message(DART_MESSAGE)
    assert msg.domain == "192.168.1.10:8000"
    assert msg.nonce == "0123456789abcdef"
    assert msg.request_id == "abc"


def test_dart_signature_recovers_address():
    recovered = Account.recover_message(encode_defunct(text=DART_MESSAGE), signature=DART_SIGNATURE)
    assert recovered == "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
