"""Shared test fixtures."""

import json
from unittest.mock import MagicMock

import pytest

# Sample Gradio /config response
SAMPLE_CONFIG = {
    "version": "4.44.0",
    "mode": "blocks",
    "title": "Test App",
    "components": [
        {"id": 1, "type": "textbox", "props": {"label": "Input", "lines": 1}},
        {"id": 2, "type": "button", "props": {"label": "Submit", "value": "Submit"}},
        {"id": 3, "type": "textbox", "props": {"label": "Output", "lines": 3}},
    ],
    "dependencies": [
        {"targets": [2], "inputs": [1], "outputs": [3]},
    ],
}

# Sample Gradio /info response
SAMPLE_API_INFO = {
    "named_endpoints": {
        "/predict": {
            "parameters": [
                {"label": "Input", "type": {"type": "string"}, "component": "Textbox"},
            ],
            "returns": [
                {"label": "Output", "type": {"type": "string"}, "component": "Textbox"},
            ],
        }
    },
    "unnamed_endpoints": {},
}

# Sample queue status
SAMPLE_QUEUE_STATUS = {
    "status": "OPEN",
    "queue_size": 0,
}


@pytest.fixture
def sample_config():
    return SAMPLE_CONFIG


@pytest.fixture
def sample_api_info():
    return SAMPLE_API_INFO


@pytest.fixture
def mock_urlopen(monkeypatch):
    """Mock urllib.request.urlopen to return controlled responses."""

    def _make_mock(data: dict | str, status: int = 200):
        body = json.dumps(data).encode() if isinstance(data, dict) else data.encode()
        resp = MagicMock()
        resp.status = status
        resp.read.return_value = body
        resp.headers = {"content-type": "application/json"}
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    return _make_mock
