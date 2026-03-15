"""Tests for health.py."""

import json
from unittest.mock import MagicMock, patch

from gradio_tester.health import check_reachable, check_queue_status


def _mock_response(body: str, status: int = 200, headers=None):
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = body.encode()
    resp.headers = headers or {}
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


@patch("gradio_tester.health.urllib.request.urlopen")
def test_check_reachable_success(mock_urlopen):
    mock_urlopen.return_value = _mock_response('<html><div class="gradio-container">ok</div></html>')
    result = check_reachable("https://test.gradio.live")
    assert result.passed is True
    assert result.details["status_code"] == 200
    assert result.details["is_gradio_app"] is True


@patch("gradio_tester.health.urllib.request.urlopen")
def test_check_reachable_not_gradio(mock_urlopen):
    mock_urlopen.return_value = _mock_response("<html><body>Hello World</body></html>")
    result = check_reachable("https://example.com")
    assert result.passed is True
    assert result.details["is_gradio_app"] is False


@patch("gradio_tester.health.urllib.request.urlopen")
def test_check_reachable_tunnel_expired(mock_urlopen):
    mock_urlopen.return_value = _mock_response("Tunnel expired, please restart")
    result = check_reachable("https://expired.gradio.live")
    assert result.passed is False
    assert "expired" in result.error.lower()


@patch("gradio_tester.health.urllib.request.urlopen")
def test_check_reachable_http_error(mock_urlopen):
    import urllib.error
    mock_urlopen.side_effect = urllib.error.HTTPError(
        "https://test.gradio.live", 502, "Bad Gateway", {}, None
    )
    result = check_reachable("https://test.gradio.live")
    assert result.passed is False
    assert result.details["status_code"] == 502


@patch("gradio_tester.health.urllib.request.urlopen")
def test_check_queue_status_success(mock_urlopen):
    mock_urlopen.return_value = _mock_response(json.dumps({"status": "OPEN", "queue_size": 0}))
    result = check_queue_status("https://test.gradio.live")
    assert result.passed is True
    assert result.details["queue_status"]["status"] == "OPEN"
