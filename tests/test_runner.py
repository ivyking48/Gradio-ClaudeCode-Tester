"""Tests for runner.py."""

from unittest.mock import patch

from gradio_tester.models import TestResult
from gradio_tester.runner import run_all_checks


@patch("gradio_tester.health.run_health_checks")
def test_short_circuits_on_unreachable(mock_health):
    mock_health.return_value = [
        TestResult(name="health_reachable", passed=False, duration_ms=100, error="Connection refused")
    ]
    report = run_all_checks("https://dead.gradio.live")
    assert report.reachable is False
    # Should have skipped checks
    skipped = [r for r in report.results if "skipped" in r.name]
    assert len(skipped) == 3  # introspect, client, screenshot


@patch("gradio_tester.screenshot.run_screenshot_checks")
@patch("gradio_tester.client.call_all_endpoints")
@patch("gradio_tester.introspect.run_introspection")
@patch("gradio_tester.health.run_health_checks")
def test_runs_all_checks_when_reachable(mock_health, mock_introspect, mock_client, mock_screenshot):
    mock_health.return_value = [
        TestResult(name="health_reachable", passed=True, duration_ms=50)
    ]
    mock_introspect.return_value = [
        TestResult(name="introspect_config", passed=True, duration_ms=30)
    ]
    mock_client.return_value = [
        TestResult(name="client_list_endpoints", passed=True, duration_ms=40)
    ]
    mock_screenshot.return_value = [
        TestResult(name="screenshot_capture", passed=True, duration_ms=200)
    ]

    report = run_all_checks("https://test.gradio.live")
    assert report.reachable is True
    assert len(report.results) == 4
    assert all(r.passed for r in report.results)


@patch("gradio_tester.health.run_health_checks")
def test_selective_checks(mock_health):
    mock_health.return_value = [
        TestResult(name="health_reachable", passed=True, duration_ms=50)
    ]
    report = run_all_checks("https://test.gradio.live", checks=["health"])
    assert len(report.results) == 1
    assert report.results[0].name == "health_reachable"
