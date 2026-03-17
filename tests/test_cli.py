"""Tests for cli.py."""

import json
from unittest.mock import patch

import pytest

from gradio_tester.models import AppReport, TestResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(name="health_reachable", passed=True, duration_ms=50.0, error=None):
    return TestResult(name=name, passed=passed, duration_ms=duration_ms, error=error)


def _make_report(url="https://test.gradio.live", results=None, reachable=True):
    if results is None:
        results = [_make_result()]
    return AppReport(url=url, reachable=reachable, results=results)


def _make_all_passing_report(url="https://test.gradio.live"):
    return _make_report(url=url, results=[
        _make_result("health_reachable", True, 50),
        _make_result("introspect_config", True, 30),
        _make_result("client_list_endpoints", True, 40),
        _make_result("screenshot_capture", True, 200),
    ])


def _make_failing_report(url="https://test.gradio.live"):
    return _make_report(url=url, results=[
        _make_result("health_reachable", True, 50),
        _make_result("introspect_config", False, 30, error="Config not found"),
    ])


# ---------------------------------------------------------------------------
# Basic invocation
# ---------------------------------------------------------------------------

@patch("gradio_tester.cli.run_all_checks")
def test_main_minimal_args(mock_run):
    from gradio_tester.cli import main

    mock_run.return_value = _make_all_passing_report()

    with pytest.raises(SystemExit) as exc_info:
        main(["https://test.gradio.live"])

    assert exc_info.value.code == 0
    mock_run.assert_called_once()
    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["url"] == "https://test.gradio.live"


@patch("gradio_tester.cli.run_all_checks")
def test_main_passes_default_checks(mock_run):
    from gradio_tester.cli import main

    mock_run.return_value = _make_all_passing_report()

    with pytest.raises(SystemExit):
        main(["https://test.gradio.live"])

    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["checks"] == ["health", "introspect", "client", "screenshot"]


# ---------------------------------------------------------------------------
# --json flag
# ---------------------------------------------------------------------------

@patch("gradio_tester.cli.run_all_checks")
def test_json_flag_outputs_only_json(mock_run, capsys):
    from gradio_tester.cli import main

    mock_run.return_value = _make_all_passing_report()

    with pytest.raises(SystemExit) as exc_info:
        main(["https://test.gradio.live", "--json"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["url"] == "https://test.gradio.live"
    assert isinstance(parsed["results"], list)
    assert "Testing:" not in captured.out


@patch("gradio_tester.cli.run_all_checks")
def test_json_flag_no_human_preamble(mock_run, capsys):
    from gradio_tester.cli import main

    mock_run.return_value = _make_all_passing_report()

    with pytest.raises(SystemExit):
        main(["https://test.gradio.live", "--json"])

    captured = capsys.readouterr()
    assert "Checks:" not in captured.out


# ---------------------------------------------------------------------------
# --checks flag
# ---------------------------------------------------------------------------

@patch("gradio_tester.cli.run_all_checks")
def test_checks_flag_single(mock_run):
    from gradio_tester.cli import main

    mock_run.return_value = _make_report()

    with pytest.raises(SystemExit):
        main(["https://test.gradio.live", "--checks", "health"])

    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["checks"] == ["health"]


@patch("gradio_tester.cli.run_all_checks")
def test_checks_flag_multiple(mock_run):
    from gradio_tester.cli import main

    mock_run.return_value = _make_report()

    with pytest.raises(SystemExit):
        main(["https://test.gradio.live", "--checks", "health,introspect"])

    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["checks"] == ["health", "introspect"]


# ---------------------------------------------------------------------------
# --call flag
# ---------------------------------------------------------------------------

@patch("gradio_tester.cli.run_all_checks")
def test_call_flag_parses_endpoint_inputs(mock_run):
    from gradio_tester.cli import main

    mock_run.return_value = _make_report()

    with pytest.raises(SystemExit):
        main(["https://test.gradio.live", "--call", "/predict", '["hello"]'])

    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["endpoint_inputs"] == {"/predict": ["hello"]}


@patch("gradio_tester.cli.run_all_checks")
def test_call_flag_multiple_endpoints(mock_run):
    from gradio_tester.cli import main

    mock_run.return_value = _make_report()

    with pytest.raises(SystemExit):
        main([
            "https://test.gradio.live",
            "--call", "/predict", '["arg1"]',
            "--call", "/generate", '["arg2", 42]',
        ])

    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["endpoint_inputs"] == {
        "/predict": ["arg1"],
        "/generate": ["arg2", 42],
    }


def test_call_flag_malformed_json():
    from gradio_tester.cli import main

    with pytest.raises((SystemExit, json.JSONDecodeError)):
        main(["https://test.gradio.live", "--call", "/predict", "not-valid-json"])


# ---------------------------------------------------------------------------
# --expect-components flag
# ---------------------------------------------------------------------------

@patch("gradio_tester.cli.run_all_checks")
def test_expect_components_flag(mock_run):
    from gradio_tester.cli import main

    mock_run.return_value = _make_report()

    with pytest.raises(SystemExit):
        main(["https://test.gradio.live", "--expect-components", '{"Location": "textbox"}'])

    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["expected_components"] == {"Location": "textbox"}


@patch("gradio_tester.cli.run_all_checks")
def test_expect_components_none_by_default(mock_run):
    from gradio_tester.cli import main

    mock_run.return_value = _make_report()

    with pytest.raises(SystemExit):
        main(["https://test.gradio.live"])

    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["expected_components"] is None


def test_expect_components_malformed_json():
    from gradio_tester.cli import main

    with pytest.raises((SystemExit, json.JSONDecodeError)):
        main(["https://test.gradio.live", "--expect-components", "{bad json}"])


# ---------------------------------------------------------------------------
# --timeout flag
# ---------------------------------------------------------------------------

@patch("gradio_tester.cli.run_all_checks")
def test_timeout_flag(mock_run):
    from gradio_tester.cli import main

    mock_run.return_value = _make_report()

    with pytest.raises(SystemExit):
        main(["https://test.gradio.live", "--timeout", "60.5"])

    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["timeout"] == 60.5


@patch("gradio_tester.cli.run_all_checks")
def test_timeout_default(mock_run):
    from gradio_tester.cli import main

    mock_run.return_value = _make_report()

    with pytest.raises(SystemExit):
        main(["https://test.gradio.live"])

    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["timeout"] == 30.0


# ---------------------------------------------------------------------------
# --screenshot flag
# ---------------------------------------------------------------------------

@patch("gradio_tester.cli.run_all_checks")
def test_screenshot_flag(mock_run):
    from gradio_tester.cli import main

    mock_run.return_value = _make_report()

    with pytest.raises(SystemExit):
        main(["https://test.gradio.live", "--screenshot", "/tmp/my_shot.png"])

    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["screenshot_path"] == "/tmp/my_shot.png"


@patch("gradio_tester.cli.run_all_checks")
def test_screenshot_default(mock_run):
    from gradio_tester.cli import main

    mock_run.return_value = _make_report()

    with pytest.raises(SystemExit):
        main(["https://test.gradio.live"])

    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["screenshot_path"] == "screenshot.png"


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

@patch("gradio_tester.cli.run_all_checks")
def test_exit_code_0_all_pass(mock_run):
    from gradio_tester.cli import main

    mock_run.return_value = _make_all_passing_report()

    with pytest.raises(SystemExit) as exc_info:
        main(["https://test.gradio.live"])

    assert exc_info.value.code == 0


@patch("gradio_tester.cli.run_all_checks")
def test_exit_code_1_any_fail(mock_run):
    from gradio_tester.cli import main

    mock_run.return_value = _make_failing_report()

    with pytest.raises(SystemExit) as exc_info:
        main(["https://test.gradio.live"])

    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Human-readable output
# ---------------------------------------------------------------------------

@patch("gradio_tester.cli.run_all_checks")
def test_human_output_pass_lines(mock_run, capsys):
    from gradio_tester.cli import main

    mock_run.return_value = _make_all_passing_report()

    with pytest.raises(SystemExit):
        main(["https://test.gradio.live"])

    captured = capsys.readouterr()
    assert "[PASS] health_reachable" in captured.out
    assert "[PASS] introspect_config" in captured.out
    assert "Testing: https://test.gradio.live" in captured.out


@patch("gradio_tester.cli.run_all_checks")
def test_human_output_fail_lines(mock_run, capsys):
    from gradio_tester.cli import main

    mock_run.return_value = _make_failing_report()

    with pytest.raises(SystemExit):
        main(["https://test.gradio.live"])

    captured = capsys.readouterr()
    assert "[FAIL] introspect_config" in captured.out
    assert "Config not found" in captured.out


@patch("gradio_tester.cli.run_all_checks")
def test_human_output_includes_summary(mock_run, capsys):
    from gradio_tester.cli import main

    report = _make_all_passing_report()
    mock_run.return_value = report

    with pytest.raises(SystemExit):
        main(["https://test.gradio.live"])

    captured = capsys.readouterr()
    assert report.summary() in captured.out
