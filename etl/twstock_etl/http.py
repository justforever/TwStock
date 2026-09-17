"""HTTP 工具與重試邏輯。"""

import logging
import time
from typing import Callable

import httpx

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {"User-Agent": "TwStock/0.1 (personal use)"}
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def default_client(
    timeout: float = 30.0, transport: httpx.BaseTransport | None = None
) -> httpx.Client:
    """建立帶預設 headers、timeout、follow_redirects=True 的 httpx.Client。

    Args:
        timeout: 要求逾時秒數
        transport: 測試用的自訂 transport；生產用則為 None

    Returns:
        設定好的 httpx.Client 實例
    """
    return httpx.Client(
        headers=DEFAULT_HEADERS,
        timeout=timeout,
        follow_redirects=True,
        transport=transport,
    )


def get_with_retry(
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, str] | None = None,
    attempts: int = 3,
    backoff_seconds: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
) -> httpx.Response:
    """GET 並在連線錯誤或可重試狀態碼時重試。

    重試策略：
    - 連線錯誤（httpx.TransportError 含逾時）→ 可重試
    - 狀態碼在 RETRYABLE_STATUS → 可重試
    - 其他 4xx → 不重試，立刻 raise_for_status()
    - 2xx → 回傳 response

    第 i 次（i 從 1 起）失敗後若還有剩餘次數，記 warning log 後
    sleep(backoff_seconds * i)，再試。最後仍失敗則拋出例外。

    Args:
        client: httpx.Client 實例
        url: 要求 URL
        params: URL 參數
        attempts: 最多嘗試次數
        backoff_seconds: 基礎退避秒數
        sleep: 睡眠函式（測試可注入假函式）

    Returns:
        成功的 httpx.Response

    Raises:
        httpx.TransportError: 連線錯誤無法重試
        httpx.HTTPStatusError: 最後仍為可重試或不可重試的非 2xx
    """
    last_error: BaseException | None = None

    for attempt in range(1, attempts + 1):
        try:
            response = client.get(url, params=params)

            # 檢查狀態碼
            if response.status_code in RETRYABLE_STATUS:
                if attempt < attempts:
                    logger.warning(
                        f"GET {url} 回傳 {response.status_code}，準備重試（第 {attempt} 次失敗）"
                    )
                    sleep(backoff_seconds * attempt)
                    continue
                else:
                    # 最後一次仍失敗
                    response.raise_for_status()
                    return response  # 不會到這裡（raise_for_status 會拋例外）
            elif response.status_code >= 400:
                # 其他 4xx，不重試
                response.raise_for_status()
                return response  # 不會到這裡
            else:
                # 2xx，成功
                return response

        except httpx.TransportError as e:
            last_error = e
            if attempt < attempts:
                logger.warning(
                    f"GET {url} 連線錯誤，準備重試（第 {attempt} 次失敗）：{e}"
                )
                sleep(backoff_seconds * attempt)
                continue
            else:
                # 最後一次仍失敗
                raise

    # 不應該到達這裡
    if last_error:
        raise last_error
    raise RuntimeError("get_with_retry 邏輯錯誤")
