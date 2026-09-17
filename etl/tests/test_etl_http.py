"""HTTP 工具測試。"""

import httpx
import pytest

from twstock_etl.http import default_client, get_with_retry


class TestGetWithRetry:
    """get_with_retry 測試。"""

    def test_retry_on_503_then_200(self) -> None:
        """503 後成功。"""
        call_count = 0
        sleep_calls: list[float] = []

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(503)
            return httpx.Response(200, text="success")

        def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        transport = httpx.MockTransport(handler)
        client = httpx.Client(transport=transport)

        response = get_with_retry(
            client,
            "http://example.com/test",
            attempts=3,
            backoff_seconds=5.0,
            sleep=mock_sleep,
        )

        assert response.status_code == 200
        assert response.text == "success"
        assert sleep_calls == [5.0]
        assert call_count == 2

    def test_retry_all_503_raises(self) -> None:
        """三次都 503。"""
        sleep_calls: list[float] = []

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503)

        def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        transport = httpx.MockTransport(handler)
        client = httpx.Client(transport=transport)

        with pytest.raises(httpx.HTTPStatusError):
            get_with_retry(
                client,
                "http://example.com/test",
                attempts=3,
                backoff_seconds=5.0,
                sleep=mock_sleep,
            )

        assert sleep_calls == [5.0, 10.0]

    def test_404_no_retry(self) -> None:
        """404 不重試。"""
        call_count = 0
        sleep_calls: list[float] = []

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(404)

        def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        transport = httpx.MockTransport(handler)
        client = httpx.Client(transport=transport)

        with pytest.raises(httpx.HTTPStatusError):
            get_with_retry(
                client,
                "http://example.com/test",
                attempts=3,
                backoff_seconds=5.0,
                sleep=mock_sleep,
            )

        assert call_count == 1
        assert sleep_calls == []

    def test_402_no_retry(self) -> None:
        """402 不重試。"""
        call_count = 0
        sleep_calls: list[float] = []

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(402)

        def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        transport = httpx.MockTransport(handler)
        client = httpx.Client(transport=transport)

        with pytest.raises(httpx.HTTPStatusError):
            get_with_retry(
                client,
                "http://example.com/test",
                attempts=3,
                backoff_seconds=5.0,
                sleep=mock_sleep,
            )

        assert call_count == 1
        assert sleep_calls == []

    def test_retry_on_connect_error(self) -> None:
        """連線錯誤後成功。"""
        call_count = 0
        sleep_calls: list[float] = []

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise httpx.ConnectError("boom")
            return httpx.Response(200, text="success")

        def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        transport = httpx.MockTransport(handler)
        client = httpx.Client(transport=transport)

        response = get_with_retry(
            client,
            "http://example.com/test",
            attempts=3,
            backoff_seconds=5.0,
            sleep=mock_sleep,
        )

        assert response.status_code == 200
        assert response.text == "success"
        assert sleep_calls == [5.0, 10.0]
        assert call_count == 3

    def test_default_client_user_agent(self) -> None:
        """驗證預設 User-Agent。"""
        captured_request: httpx.Request | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_request
            captured_request = request
            return httpx.Response(200)

        transport = httpx.MockTransport(handler)
        client = default_client(transport=transport)

        client.get("http://example.com/test")

        assert captured_request is not None
        assert captured_request.headers["User-Agent"] == "TwStock/0.1 (personal use)"
