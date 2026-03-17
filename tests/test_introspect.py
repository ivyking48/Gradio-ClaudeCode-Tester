"""Tests for introspect.py."""

import json
from unittest.mock import MagicMock, patch

from tests.conftest import SAMPLE_API_INFO, SAMPLE_CONFIG
from gradio_tester.introspect import get_api_info, get_config, run_introspection, validate_components


def _mock_response(data: dict, status: int = 200):
    body = json.dumps(data).encode()
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


@patch("gradio_tester.introspect.urllib.request.urlopen")
def test_get_config_success(mock_urlopen):
    mock_urlopen.return_value = _mock_response(SAMPLE_CONFIG)
    result = get_config("https://test.gradio.live")
    assert result.passed is True
    assert result.details["gradio_version"] == "4.44.0"
    assert result.details["component_count"] == 3
    assert result.details["components"][0]["label"] == "Input"


@patch("gradio_tester.introspect.urllib.request.urlopen")
def test_get_api_info_success(mock_urlopen):
    mock_urlopen.return_value = _mock_response(SAMPLE_API_INFO)
    result = get_api_info("https://test.gradio.live")
    assert result.passed is True
    assert result.details["endpoint_count"] == 1
    assert "/predict" in result.details["endpoints"]


@patch("gradio_tester.introspect.urllib.request.urlopen")
def test_validate_components_pass(mock_urlopen):
    mock_urlopen.return_value = _mock_response(SAMPLE_CONFIG)
    result = validate_components(
        "https://test.gradio.live",
        expected={"Input": "textbox", "Output": "textbox"},
    )
    assert result.passed is True
    assert result.details["missing"] == []
    assert result.details["wrong_type"] == []


@patch("gradio_tester.introspect.urllib.request.urlopen")
def test_validate_components_missing(mock_urlopen):
    mock_urlopen.return_value = _mock_response(SAMPLE_CONFIG)
    result = validate_components(
        "https://test.gradio.live",
        expected={"NonExistent": "textbox"},
    )
    assert result.passed is False
    assert "NonExistent" in result.details["missing"]


@patch("gradio_tester.introspect.urllib.request.urlopen")
def test_validate_components_wrong_type(mock_urlopen):
    mock_urlopen.return_value = _mock_response(SAMPLE_CONFIG)
    result = validate_components(
        "https://test.gradio.live",
        expected={"Input": "slider"},
    )
    assert result.passed is False
    assert len(result.details["wrong_type"]) == 1


# --- Edge case tests ---


@patch("gradio_tester.introspect.urllib.request.urlopen")
def test_get_config_exception(mock_urlopen):
    mock_urlopen.side_effect = Exception("Network failure")
    result = get_config("https://test.gradio.live")
    assert result.passed is False
    assert result.error is not None


@patch("gradio_tester.introspect.urllib.request.urlopen")
def test_get_api_info_exception(mock_urlopen):
    mock_urlopen.side_effect = Exception("Connection reset")
    result = get_api_info("https://test.gradio.live")
    assert result.passed is False
    assert result.error is not None


@patch("gradio_tester.introspect.urllib.request.urlopen")
def test_validate_components_empty_expected(mock_urlopen):
    mock_urlopen.return_value = _mock_response(SAMPLE_CONFIG)
    result = validate_components("https://test.gradio.live", expected={})
    assert result.passed is True
    assert result.details["checked"] == 0


@patch("gradio_tester.introspect.urllib.request.urlopen")
def test_run_introspection_orchestration(mock_urlopen):
    # First call returns config, second returns api_info
    mock_urlopen.side_effect = [
        _mock_response(SAMPLE_CONFIG),
        _mock_response(SAMPLE_API_INFO),
    ]
    results = run_introspection("https://test.gradio.live")
    assert isinstance(results, list)
    assert len(results) == 2
