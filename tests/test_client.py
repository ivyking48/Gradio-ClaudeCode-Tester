"""Tests for client.py."""

from unittest.mock import MagicMock, patch

from gradio_tester.client import call_endpoint, call_all_endpoints, check_output_variance, list_endpoints, _is_serializable


@patch("gradio_client.Client")
def test_list_endpoints_success(MockClient):
    mock_client = MagicMock()
    MockClient.return_value = mock_client
    mock_client.view_api.return_value = {
        "named_endpoints": {
            "/predict": {
                "parameters": [{"label": "text", "type": "string", "component": "Textbox"}],
                "returns": [{"label": "output", "type": "string", "component": "Textbox"}],
            }
        },
        "unnamed_endpoints": {},
    }

    result = list_endpoints("https://test.gradio.live")
    assert result.passed is True
    assert "/predict" in result.details["named_endpoints"]


@patch("gradio_client.Client")
def test_list_endpoints_connection_error(MockClient):
    MockClient.side_effect = ConnectionError("Could not connect")
    result = list_endpoints("https://bad.gradio.live")
    assert result.passed is False
    assert "connect" in result.error.lower()


@patch("gradio_client.Client")
def test_call_endpoint_success(MockClient):
    mock_client = MagicMock()
    MockClient.return_value = mock_client
    mock_client.predict.return_value = "Hello World"

    result = call_endpoint("https://test.gradio.live", api_name="/predict", inputs=["test"])
    assert result.passed is True
    assert result.details["output"] == "Hello World"
    assert result.details["output_type"] == "str"


@patch("gradio_client.Client")
def test_call_endpoint_type_mismatch(MockClient):
    mock_client = MagicMock()
    MockClient.return_value = mock_client
    mock_client.predict.return_value = "not a number"

    result = call_endpoint(
        "https://test.gradio.live",
        api_name="/predict",
        inputs=["test"],
        expected_output_type=int,
    )
    assert result.passed is False
    assert "Expected output type" in result.error


# --- Edge case tests ---


@patch("gradio_client.Client")
def test_call_endpoint_connection_error(MockClient):
    MockClient.side_effect = ConnectionError("Connection refused")
    result = call_endpoint("https://bad.gradio.live", api_name="/predict", inputs=["test"])
    assert result.passed is False
    assert "Connection refused" in result.error


@patch("gradio_client.Client")
def test_call_all_endpoints_success(MockClient):
    mock_client = MagicMock()
    MockClient.return_value = mock_client
    mock_client.view_api.return_value = {
        "named_endpoints": {
            "/predict": {
                "parameters": [{"label": "text", "type": "string", "component": "Textbox"}],
                "returns": [{"label": "output", "type": "string", "component": "Textbox"}],
            },
            "/generate": {
                "parameters": [{"label": "prompt", "type": "string", "component": "Textbox"}],
                "returns": [{"label": "result", "type": "string", "component": "Textbox"}],
            },
        },
        "unnamed_endpoints": {},
    }
    mock_client.predict.return_value = "result"

    results = call_all_endpoints(
        "https://test.gradio.live",
        endpoint_inputs={"/predict": ["hello"], "/generate": ["prompt"]},
    )
    assert isinstance(results, list)
    assert len(results) >= 2  # list + calls


@patch("gradio_client.Client")
def test_call_all_endpoints_no_inputs(MockClient):
    mock_client = MagicMock()
    MockClient.return_value = mock_client
    mock_client.view_api.return_value = {
        "named_endpoints": {"/predict": {"parameters": [], "returns": []}},
        "unnamed_endpoints": {},
    }

    results = call_all_endpoints("https://test.gradio.live", endpoint_inputs=None)
    assert isinstance(results, list)
    # Should at least have the list_endpoints result
    assert any(r.name == "client_list_endpoints" for r in results)


def test_is_serializable():
    assert _is_serializable("hello") is True
    assert _is_serializable(42) is True
    assert _is_serializable({"key": "value"}) is True
    assert _is_serializable([1, "two", None]) is True


# --- Output variance tests ---


@patch("gradio_client.Client")
def test_check_output_variance_passes_when_outputs_vary(MockClient):
    mock_client = MagicMock()
    MockClient.return_value = mock_client
    mock_client.predict.side_effect = ["red", "blue", "green"]

    result = check_output_variance(
        "https://test.gradio.live",
        api_name="/get_color",
        input_samples=[[0], [5], [9]],
    )
    assert result.passed is True
    assert result.details["unique_outputs"] == 3
    assert result.details["total_calls"] == 3
    assert result.error is None


@patch("gradio_client.Client")
def test_check_output_variance_fails_when_all_same(MockClient):
    mock_client = MagicMock()
    MockClient.return_value = mock_client
    mock_client.predict.return_value = "red"  # Always returns "red"

    result = check_output_variance(
        "https://test.gradio.live",
        api_name="/get_color",
        input_samples=[[0], [5], [9]],
    )
    assert result.passed is False
    assert result.details["unique_outputs"] == 1
    assert "always returns" in result.error
    assert "ignoring input" in result.error


@patch("gradio_client.Client")
def test_check_output_variance_connection_error(MockClient):
    MockClient.side_effect = ConnectionError("Refused")
    result = check_output_variance(
        "https://bad.gradio.live",
        api_name="/predict",
        input_samples=[[0], [1]],
    )
    assert result.passed is False
    assert "Refused" in result.error
