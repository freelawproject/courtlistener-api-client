"""Tests for CourtListenerAPIError and error handling in _request."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from courtlistener import CourtListener, CourtListenerAPIError


@pytest.fixture
def cl():
    """Create a CourtListener client with a mocked HTTP client."""
    with patch.dict("os.environ", {"COURTLISTENER_API_TOKEN": "test-token"}):
        client = CourtListener(api_token="test-token")
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


class TestCourtListenerAPIError:
    def test_json_detail_dict(self, cl):
        body = {"detail": "Authentication credentials were not provided."}
        response = _make_response(403, json_body=body)
        cl._http_client = MagicMock()
        cl._http_client.request.return_value = response

        with pytest.raises(CourtListenerAPIError) as exc_info:
            cl._request("GET", "/dockets/")

        err = exc_info.value
        assert err.status_code == 403
        assert err.detail == body
        assert "Authentication credentials were not provided." in str(err)

    def test_json_detail_field_errors(self, cl):
        body = {"name": ["This field is required."]}
        response = _make_response(400, json_body=body)
        cl._http_client = MagicMock()
        cl._http_client.request.return_value = response

        with pytest.raises(CourtListenerAPIError) as exc_info:
            cl._request("POST", "/alerts/")

        err = exc_info.value
        assert err.status_code == 400
        assert err.detail == body
        assert "HTTP 400" in str(err)

    def test_non_json_response(self, cl):
        html = "<html><body>502 Bad Gateway</body></html>"
        response = _make_response(502, text=html)
        cl._http_client = MagicMock()
        cl._http_client.request.return_value = response

        with pytest.raises(CourtListenerAPIError) as exc_info:
            cl._request("GET", "/dockets/")

        err = exc_info.value
        assert err.status_code == 502
        assert err.detail == html
        assert "502 Bad Gateway" in str(err)

    def test_response_attribute(self, cl):
        response = _make_response(404, json_body={"detail": "Not found."})
        cl._http_client = MagicMock()
        cl._http_client.request.return_value = response

        with pytest.raises(CourtListenerAPIError) as exc_info:
            cl._request("GET", "/dockets/999999/")

        assert exc_info.value.response is response

    def test_successful_request_no_error(self, cl):
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.raise_for_status = MagicMock()
        response.json.return_value = {"id": 1}
        cl._http_client = MagicMock()
        cl._http_client.request.return_value = response

        result = cl._request("GET", "/dockets/1/")
        assert result == {"id": 1}
