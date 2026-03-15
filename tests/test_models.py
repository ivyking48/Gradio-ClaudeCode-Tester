"""Tests for models.py."""

import json

from gradio_tester.models import AppReport, TestResult


def test_test_result_to_dict():
    r = TestResult(name="test", passed=True, duration_ms=42.0, details={"key": "val"})
    d = r.to_dict()
    assert d["name"] == "test"
    assert d["passed"] is True
    assert d["duration_ms"] == 42.0
    assert d["details"]["key"] == "val"
    assert d["error"] is None


def test_test_result_to_json():
    r = TestResult(name="test", passed=False, duration_ms=10.0, error="boom")
    data = json.loads(r.to_json())
    assert data["passed"] is False
    assert data["error"] == "boom"


def test_app_report_summary_all_pass():
    report = AppReport(
        url="https://test.gradio.live",
        results=[
            TestResult(name="a", passed=True, duration_ms=1),
            TestResult(name="b", passed=True, duration_ms=2),
        ],
    )
    assert report.summary().startswith("PASS")
    assert "2/2" in report.summary()


def test_app_report_summary_with_failures():
    report = AppReport(
        url="https://test.gradio.live",
        results=[
            TestResult(name="a", passed=True, duration_ms=1),
            TestResult(name="b", passed=False, duration_ms=2, error="fail"),
        ],
    )
    assert report.summary().startswith("FAIL")
    assert "1/2" in report.summary()
    assert "b" in report.summary()


def test_app_report_to_json():
    report = AppReport(url="https://test.gradio.live", reachable=True, results=[])
    data = json.loads(report.to_json())
    assert data["url"] == "https://test.gradio.live"
    assert data["reachable"] is True
    assert "summary" in data
