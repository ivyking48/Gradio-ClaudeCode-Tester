"""Tests for client.py."""

from unittest.mock import MagicMock, patch

from gradio_tester.client import call_endpoint, list_endpoints


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
