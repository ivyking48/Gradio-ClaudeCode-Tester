"""Tests for screenshot.py."""

from unittest.mock import AsyncMock, MagicMock, patch

from gradio_tester.models import TestResult


# ---------------------------------------------------------------------------
# Helpers to build mock Playwright objects
# ---------------------------------------------------------------------------

def _make_mock_page(title="Test App", error_elements=None):
    """Create a mock Playwright page with configurable behaviour."""
    page = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.screenshot = AsyncMock()
    page.title = AsyncMock(return_value=title)
    page.query_selector_all = AsyncMock(return_value=[])

    if error_elements:
        side_effects = [error_elements] + [[] for _ in range(3)]
        page.query_selector_all = AsyncMock(side_effect=side_effects)

    page.on = MagicMock()
    return page


def _make_mock_browser(page):
    browser = AsyncMock()
    browser.new_page = AsyncMock(return_value=page)
    browser.close = AsyncMock()
    return browser


def _make_mock_playwright(browser):
    """Build the full async context manager chain for async_playwright()."""
    pw = AsyncMock()
    pw.chromium.launch = AsyncMock(return_value=browser)

    pw_cm = AsyncMock()
    pw_cm.__aenter__ = AsyncMock(return_value=pw)
    pw_cm.__aexit__ = AsyncMock(return_value=False)
    return pw_cm


# ---------------------------------------------------------------------------
# capture_screenshot tests
# ---------------------------------------------------------------------------

@patch("gradio_tester.screenshot._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.screenshot.async_playwright", create=True)
def test_capture_screenshot_success(mock_async_pw):
    page = _make_mock_page(title="My Gradio App")
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.screenshot import capture_screenshot

    result = capture_screenshot("https://test.gradio.live", output_path="/tmp/shot.png")

    assert isinstance(result, TestResult)
    assert result.passed is True
    assert result.name == "screenshot_capture"
    assert result.details["output_path"] == "/tmp/shot.png"
    assert result.details["page_title"] == "My Gradio App"
    assert result.details["viewport"] == "1280x720"
    assert result.error is None


@patch("gradio_tester.screenshot._PLAYWRIGHT_AVAILABLE", False)
def test_capture_screenshot_no_playwright():
    from gradio_tester.screenshot import capture_screenshot

    result = capture_screenshot("https://test.gradio.live")

    assert result.passed is False
    assert result.name == "screenshot_capture"
    assert "playwright not installed" in result.error
    assert result.duration_ms == 0


@patch("gradio_tester.screenshot._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.screenshot.async_playwright", create=True)
def test_capture_screenshot_navigation_failure(mock_async_pw):
    page = _make_mock_page()
    page.goto = AsyncMock(side_effect=Exception("net::ERR_CONNECTION_REFUSED"))
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.screenshot import capture_screenshot

    result = capture_screenshot("https://unreachable.gradio.live")

    assert result.passed is False
    assert "ERR_CONNECTION_REFUSED" in result.error


@patch("gradio_tester.screenshot._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.screenshot.async_playwright", create=True)
def test_capture_screenshot_selector_timeout_still_succeeds(mock_async_pw):
    """If the Gradio container selector times out, we still take the screenshot."""
    page = _make_mock_page(title="Slow App")
    page.wait_for_selector = AsyncMock(side_effect=TimeoutError("Selector timed out"))
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.screenshot import capture_screenshot

    result = capture_screenshot("https://test.gradio.live")

    assert result.passed is True
    assert result.details["page_title"] == "Slow App"
    page.screenshot.assert_awaited_once()


@patch("gradio_tester.screenshot._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.screenshot.async_playwright", create=True)
def test_capture_screenshot_write_failure(mock_async_pw):
    page = _make_mock_page()
    page.screenshot = AsyncMock(side_effect=OSError("Permission denied"))
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.screenshot import capture_screenshot

    result = capture_screenshot("https://test.gradio.live")

    assert result.passed is False
    assert "Permission denied" in result.error


@patch("gradio_tester.screenshot._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.screenshot.async_playwright", create=True)
def test_capture_screenshot_custom_viewport(mock_async_pw):
    page = _make_mock_page(title="Wide App")
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.screenshot import capture_screenshot

    result = capture_screenshot("https://test.gradio.live", viewport=(1920, 1080))

    assert result.passed is True
    assert result.details["viewport"] == "1920x1080"


# ---------------------------------------------------------------------------
# check_for_errors tests
# ---------------------------------------------------------------------------

@patch("gradio_tester.screenshot._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.screenshot.async_playwright", create=True)
def test_check_for_errors_clean_page(mock_async_pw):
    page = _make_mock_page()
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.screenshot import check_for_errors

    result = check_for_errors("https://test.gradio.live")

    assert result.passed is True
    assert result.name == "screenshot_error_check"
    assert result.details["error_count"] == 0
    assert result.details["errors_found"] == []


@patch("gradio_tester.screenshot._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.screenshot.async_playwright", create=True)
def test_check_for_errors_dom_errors_found(mock_async_pw):
    error_el = AsyncMock()
    error_el.text_content = AsyncMock(return_value="Something went wrong: TypeError")

    page = _make_mock_page(error_elements=[error_el])
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.screenshot import check_for_errors

    result = check_for_errors("https://test.gradio.live")

    assert result.passed is False
    assert result.details["error_count"] == 1
    assert "Something went wrong" in result.details["errors_found"][0]["text"]
    assert "Found 1 DOM error(s) and 0 console error(s)" == result.error


@patch("gradio_tester.screenshot._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.screenshot.async_playwright", create=True)
def test_check_for_errors_multiple_errors(mock_async_pw):
    error_el_1 = AsyncMock()
    error_el_1.text_content = AsyncMock(return_value="Error one")
    error_el_2 = AsyncMock()
    error_el_2.text_content = AsyncMock(return_value="Error two")

    page = _make_mock_page(error_elements=[error_el_1, error_el_2])
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.screenshot import check_for_errors

    result = check_for_errors("https://test.gradio.live")

    assert result.passed is False
    assert result.details["error_count"] == 2


@patch("gradio_tester.screenshot._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.screenshot.async_playwright", create=True)
def test_check_for_errors_empty_text_ignored(mock_async_pw):
    empty_el = AsyncMock()
    empty_el.text_content = AsyncMock(return_value="   ")

    page = _make_mock_page(error_elements=[empty_el])
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.screenshot import check_for_errors

    result = check_for_errors("https://test.gradio.live")

    assert result.passed is True
    assert result.details["error_count"] == 0


@patch("gradio_tester.screenshot._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.screenshot.async_playwright", create=True)
def test_check_for_errors_none_text_ignored(mock_async_pw):
    none_el = AsyncMock()
    none_el.text_content = AsyncMock(return_value=None)

    page = _make_mock_page(error_elements=[none_el])
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.screenshot import check_for_errors

    result = check_for_errors("https://test.gradio.live")

    assert result.passed is True
    assert result.details["error_count"] == 0


@patch("gradio_tester.screenshot._PLAYWRIGHT_AVAILABLE", False)
def test_check_for_errors_no_playwright():
    from gradio_tester.screenshot import check_for_errors

    result = check_for_errors("https://test.gradio.live")

    assert result.passed is False
    assert "playwright not installed" in result.error
    assert result.duration_ms == 0


@patch("gradio_tester.screenshot._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.screenshot.async_playwright", create=True)
def test_check_for_errors_navigation_failure(mock_async_pw):
    page = _make_mock_page()
    page.goto = AsyncMock(side_effect=Exception("Timeout 15000ms exceeded"))
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.screenshot import check_for_errors

    result = check_for_errors("https://test.gradio.live")

    assert result.passed is False
    assert "Timeout" in result.error


@patch("gradio_tester.screenshot._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.screenshot.async_playwright", create=True)
def test_check_for_errors_console_errors_fail_check(mock_async_pw):
    page = _make_mock_page()
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    def register_console_handler(_event, handler):
        msg = MagicMock()
        msg.type = "error"
        msg.text = "Unhandled TypeError"
        handler(msg)

    page.on.side_effect = register_console_handler

    from gradio_tester.screenshot import check_for_errors

    result = check_for_errors("https://test.gradio.live")

    assert result.passed is False
    assert result.details["console_errors"] == ["Unhandled TypeError"]
    assert "console error" in result.error


@patch("gradio_tester.screenshot._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.screenshot.async_playwright", create=True)
def test_check_for_errors_truncates_long_text(mock_async_pw):
    long_el = AsyncMock()
    long_el.text_content = AsyncMock(return_value="X" * 500)

    page = _make_mock_page(error_elements=[long_el])
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.screenshot import check_for_errors

    result = check_for_errors("https://test.gradio.live")

    assert result.passed is False
    assert len(result.details["errors_found"][0]["text"]) == 200


# ---------------------------------------------------------------------------
# run_screenshot_checks tests
# ---------------------------------------------------------------------------

@patch("gradio_tester.screenshot._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.screenshot.async_playwright", create=True)
def test_run_screenshot_checks_returns_both_results(mock_async_pw):
    page = _make_mock_page(title="Orchestration Test")
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.screenshot import run_screenshot_checks

    results = run_screenshot_checks("https://test.gradio.live", output_path="/tmp/test.png")

    assert isinstance(results, list)
    assert len(results) == 2
    assert all(isinstance(r, TestResult) for r in results)
    assert results[0].name == "screenshot_capture"
    assert results[1].name == "screenshot_error_check"


@patch("gradio_tester.screenshot._PLAYWRIGHT_AVAILABLE", False)
def test_run_screenshot_checks_no_playwright():
    from gradio_tester.screenshot import run_screenshot_checks

    results = run_screenshot_checks("https://test.gradio.live")

    assert len(results) == 2
    assert all(r.passed is False for r in results)
    assert all("playwright not installed" in r.error for r in results)
