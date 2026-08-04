"""Async mirror of test_exceptions.py: error handling in _request."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from courtlistener import AsyncCourtListener
from courtlistener.exceptions import CourtListenerAPIError

pytestmark = pytest.mark.asyncio


@pytest.fixture
def cl():
    """Create an AsyncCourtListener client with a mocked HTTP client."""
    with patch.dict("os.environ", {"COURTLISTENER_API_TOKEN": "test-token"}):
        client = AsyncCourtListener(api_token="test-token")
    return client


def _make_response(status_code, json_body=None, text=""):
    """Build a fake httpx.Response that behaves like the real thing."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.text = text

    if json_body is not None:
        response.json.return_value = json_body
        response.text = str(json_body)
    else:
        response.json.side_effect = ValueError("No JSON")
        response.text = text

    def raise_for_status():
        if status_code >= 400:
            raise httpx.HTTPStatusError(
                message=f"{status_code}",
                request=MagicMock(),
                response=response,
            )

    response.raise_for_status = raise_for_status
    return response


def _attach(cl, response):
    """Wire a response onto the client's HTTP layer, return the mock."""
    cl._http_client = MagicMock()
    cl._http_client.request = AsyncMock(return_value=response)
    return cl._http_client.request


class TestCourtListenerAPIError:
    async def test_json_detail_dict(self, cl):
        body = {"detail": "Authentication credentials were not provided."}
        _attach(cl, _make_response(403, json_body=body))

        with pytest.raises(CourtListenerAPIError) as exc_info:
            await cl._request("GET", "/dockets/")

        err = exc_info.value
        assert err.status_code == 403
        assert err.detail == body
        assert "Authentication credentials were not provided." in str(err)

    async def test_json_detail_field_errors(self, cl):
        body = {"name": ["This field is required."]}
        _attach(cl, _make_response(400, json_body=body))

        with pytest.raises(CourtListenerAPIError) as exc_info:
            await cl._request("POST", "/alerts/")

        err = exc_info.value
        assert err.status_code == 400
        assert err.detail == body
        assert "HTTP 400" in str(err)

    async def test_non_json_response(self, cl):
        html = "<html><body>502 Bad Gateway</body></html>"
        _attach(cl, _make_response(502, text=html))

        with pytest.raises(CourtListenerAPIError) as exc_info:
            await cl._request("GET", "/dockets/")

        err = exc_info.value
        assert err.status_code == 502
        assert err.detail == html
        assert "502 Bad Gateway" in str(err)

    async def test_response_attribute(self, cl):
        response = _make_response(404, json_body={"detail": "Not found."})
        _attach(cl, response)

        with pytest.raises(CourtListenerAPIError) as exc_info:
            await cl._request("GET", "/dockets/999999/")

        assert exc_info.value.response is response

    async def test_successful_request_no_error(self, cl):
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.raise_for_status = MagicMock()
        response.json.return_value = {"id": 1}
        _attach(cl, response)

        result = await cl._request("GET", "/dockets/1/")
        assert result == {"id": 1}


class TestRequestResponseHandling:
    async def test_204_returns_empty_dict(self, cl):
        """DELETE returns no body; _request must not call .json()."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 204
        response.raise_for_status = MagicMock()
        response.json.side_effect = ValueError("No JSON")
        _attach(cl, response)

        assert await cl._request("DELETE", "/alerts/1/") == {}

    async def test_absolute_path_is_trimmed_against_base_url(self, cl):
        """Paginated URLs repeat the base path; the overlap is stripped."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.raise_for_status = MagicMock()
        response.json.return_value = {"results": []}
        request = _attach(cl, response)

        await cl._request("GET", "/api/rest/v4/dockets/?cursor=abc")

        request.assert_awaited_once_with("GET", "/dockets/?cursor=abc")

    async def test_relative_path_is_left_alone(self, cl):
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.raise_for_status = MagicMock()
        response.json.return_value = {"results": []}
        request = _attach(cl, response)

        await cl._request("GET", "/dockets/", params={"court": "scotus"})

        request.assert_awaited_once_with(
            "GET", "/dockets/", params={"court": "scotus"}
        )
