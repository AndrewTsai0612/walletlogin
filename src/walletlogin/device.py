"""把瀏覽器的 User-Agent 轉成看得懂的「瀏覽器 · 作業系統」。

只辨識常見的幾種，用簡單的規則判斷，不需要額外的套件。
結果會顯示在錢包 App 的確認畫面，讓使用者確認「發起登入的是不是我眼前這台裝置」。
"""
import re
from typing import Tuple

# 順序很重要：許多瀏覽器的 User-Agent 都含有 "Chrome" 或 "Safari"，要先判斷比較特定的
_BROWSERS = [
    (r"Edg(e|A|iOS)?/", "Edge"),
    (r"OPR/|Opera", "Opera"),
    (r"SamsungBrowser/", "Samsung Internet"),
    (r"Firefox/|FxiOS/", "Firefox"),
    (r"Chrome/|CriOS/", "Chrome"),
    (r"Safari/", "Safari"),
]

_SYSTEMS = [
    (r"Windows NT", "Windows"),
    (r"Android", "Android"),
    (r"iPhone|iPad|iPod", "iOS"),
    (r"Macintosh|Mac OS X", "macOS"),
    (r"CrOS", "ChromeOS"),
    (r"Linux", "Linux"),
]


def describe_user_agent(user_agent: str) -> Tuple[str, str]:
    """回傳 (瀏覽器, 作業系統)；無法辨識時回傳「未知瀏覽器」「未知系統」。"""
    ua = user_agent or ""
    browser = next((name for pattern, name in _BROWSERS if re.search(pattern, ua)), "未知瀏覽器")
    system = next((name for pattern, name in _SYSTEMS if re.search(pattern, ua)), "未知系統")
    return browser, system
