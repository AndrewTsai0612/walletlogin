"""錢包簽名訊息的格式（參考 EIP-4361 Sign-In with Ethereum）。

訊息範例：

    192.168.1.10:8000 wants you to sign in with your Ethereum account:
    0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266

    Sign in with your wallet. This request will not trigger any transaction.

    URI: http://192.168.1.10:8000
    Version: 1
    Chain ID: 1
    Nonce: 8f2k3j4h5g6f7d8s
    Issued At: 2026-10-01T12:00:00.000Z
    Request ID: abc123

錢包 App 依照這個格式組出訊息並簽名，套件再把它拆開逐欄檢查。
格式的完整規定見 PROTOCOL.md。
"""
import re
from dataclasses import dataclass

STATEMENT = "Sign in with your wallet. This request will not trigger any transaction."
VERSION = "1"
CHAIN_ID = 1


@dataclass
class SiweMessage:
    domain: str
    address: str
    statement: str
    uri: str
    version: str
    chain_id: int
    nonce: str
    issued_at: str
    request_id: str


def build_message(m: SiweMessage) -> str:
    return (
        f"{m.domain} wants you to sign in with your Ethereum account:\n"
        f"{m.address}\n"
        f"\n"
        f"{m.statement}\n"
        f"\n"
        f"URI: {m.uri}\n"
        f"Version: {m.version}\n"
        f"Chain ID: {m.chain_id}\n"
        f"Nonce: {m.nonce}\n"
        f"Issued At: {m.issued_at}\n"
        f"Request ID: {m.request_id}"
    )


_PATTERN = re.compile(
    r"^(?P<domain>\S+) wants you to sign in with your Ethereum account:\n"
    r"(?P<address>0x[0-9a-fA-F]{40})\n"
    r"\n"
    r"(?P<statement>[^\n]*)\n"
    r"\n"
    r"URI: (?P<uri>[^\n]+)\n"
    r"Version: (?P<version>[^\n]+)\n"
    r"Chain ID: (?P<chain_id>\d+)\n"
    r"Nonce: (?P<nonce>[0-9A-Za-z]{8,})\n"
    r"Issued At: (?P<issued_at>[^\n]+)\n"
    r"Request ID: (?P<request_id>[^\n]+)$"
)


def parse_message(text: str) -> SiweMessage:
    """把簽名訊息拆成各欄位；格式不符時拋出 ValueError。"""
    match = _PATTERN.match(text)
    if not match:
        raise ValueError("簽名訊息格式不正確")
    fields = match.groupdict()
    fields["chain_id"] = int(fields["chain_id"])
    return SiweMessage(**fields)
