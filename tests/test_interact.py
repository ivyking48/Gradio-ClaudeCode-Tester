"""Tests for interact.py — UI interaction testing."""

from unittest.mock import AsyncMock, MagicMock, patch

from gradio_tester.models import TestResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_locator(input_value="", text_content=""):
    """Create a mock Playwright locator."""
    loc = AsyncMock()
    loc.fill = AsyncMock()
    loc.clear = AsyncMock()
    loc.click = AsyncMock()
    loc.dispatch_event = AsyncMock()
    loc.input_value = AsyncMock(return_value=input_value)
    loc.text_content = AsyncMock(return_value=text_content)
    loc.count = AsyncMock(return_value=0)
    return loc


def _make_mock_page(locator=None):
    """Create a mock Playwright page with locator support."""
    page = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.screenshot = AsyncMock()

    loc = locator or _make_mock_locator()
    page.get_by_label = MagicMock(return_value=loc)
    page.get_by_role = MagicMock(return_value=loc)
    page.locator = MagicMock(return_value=_make_mock_locator())  # For loading checks
    page.on = MagicMock()
    return page, loc


def _make_mock_browser(page):
    browser = AsyncMock()
    browser.new_page = AsyncMock(return_value=page)
    browser.close = AsyncMock()
    return browser


def _make_mock_playwright(browser):
    pw = AsyncMock()
    pw.chromium.launch = AsyncMock(return_value=browser)
    pw_cm = AsyncMock()
    pw_cm.__aenter__ = AsyncMock(return_value=pw)
    pw_cm.__aexit__ = AsyncMock(return_value=False)
    return pw_cm


# ---------------------------------------------------------------------------
# Playwright not installed
# ---------------------------------------------------------------------------

@patch("gradio_tester.interact._PLAYWRIGHT_AVAILABLE", False)
def test_playwright_not_installed():
    from gradio_tester.interact import execute_actions

    actions = [
        {"action": "fill", "label": "Name", "value": "test"},
        {"action": "click", "label": "Submit"},
    ]
    results = execute_actions("https://test.gradio.live", actions)

    assert len(results) == 2
    assert all(r.passed is False for r in results)
    assert all("playwright not installed" in r.error for r in results)


# ---------------------------------------------------------------------------
# Empty actions
# ---------------------------------------------------------------------------

@patch("gradio_tester.interact._PLAYWRIGHT_AVAILABLE", True)
def test_empty_actions_list():
    from gradio_tester.interact import execute_actions

    results = execute_actions("https://test.gradio.live", [])
    assert results == []


# ---------------------------------------------------------------------------
# Fill action
# ---------------------------------------------------------------------------

@patch("gradio_tester.interact._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.interact.async_playwright", create=True)
def test_fill_action_success(mock_async_pw):
    page, loc = _make_mock_page()
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.interact import execute_actions

    results = execute_actions("https://test.gradio.live", [
        {"action": "fill", "label": "Timestamp", "value": "5.0"},
    ])

    assert len(results) == 1
    assert results[0].passed is True
    assert results[0].name == "interact_step_0_fill"
    page.get_by_label.assert_called_with("Timestamp")
    loc.fill.assert_awaited_once_with("5.0", timeout=15000)


# ---------------------------------------------------------------------------
# Click action
# ---------------------------------------------------------------------------

@patch("gradio_tester.interact._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.interact.async_playwright", create=True)
def test_click_action_success(mock_async_pw):
    page, loc = _make_mock_page()
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.interact import execute_actions

    results = execute_actions("https://test.gradio.live", [
        {"action": "click", "label": "Check Color"},
    ])

    assert len(results) == 1
    assert results[0].passed is True
    assert results[0].name == "interact_step_0_click"
    page.get_by_role.assert_called_with("button", name="Check Color")
    loc.click.assert_awaited_once()


@patch("gradio_tester.interact._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.interact.async_playwright", create=True)
def test_click_action_fails_when_app_never_goes_idle(mock_async_pw):
    page, loc = _make_mock_page()
    busy_loc = _make_mock_locator()
    busy_loc.count = AsyncMock(return_value=1)
    page.locator = MagicMock(return_value=busy_loc)
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.interact import execute_actions

    results = execute_actions(
        "https://test.gradio.live",
        [{"action": "click", "label": "Check Color"}],
        timeout_ms=10,
    )

    assert len(results) == 1
    assert results[0].passed is False
    assert "stayed busy" in results[0].error
    loc.click.assert_awaited_once()


# ---------------------------------------------------------------------------
# Verify action
# ---------------------------------------------------------------------------

@patch("gradio_tester.interact._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.interact.async_playwright", create=True)
def test_verify_action_exact_match(mock_async_pw):
    page, loc = _make_mock_page(_make_mock_locator(input_value="blue"))
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.interact import execute_actions

    results = execute_actions("https://test.gradio.live", [
        {"action": "verify", "label": "Dominant Color", "expected": "blue"},
    ])

    assert len(results) == 1
    assert results[0].passed is True
    assert results[0].details["actual"] == "blue"


@patch("gradio_tester.interact._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.interact.async_playwright", create=True)
def test_verify_action_mismatch(mock_async_pw):
    page, loc = _make_mock_page(_make_mock_locator(input_value="red"))
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.interact import execute_actions

    results = execute_actions("https://test.gradio.live", [
        {"action": "verify", "label": "Dominant Color", "expected": "blue"},
    ])

    assert len(results) == 1
    assert results[0].passed is False
    assert results[0].details["actual"] == "red"
    assert results[0].details["expected"] == "blue"
    assert '"blue"' in results[0].error
    assert '"red"' in results[0].error


@patch("gradio_tester.interact._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.interact.async_playwright", create=True)
def test_verify_action_contains(mock_async_pw):
    page, loc = _make_mock_page(_make_mock_locator(input_value="the color is blue today"))
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.interact import execute_actions

    results = execute_actions("https://test.gradio.live", [
        {"action": "verify", "label": "Output", "expected": "blue", "contains": True},
    ])

    assert len(results) == 1
    assert results[0].passed is True


# ---------------------------------------------------------------------------
# Full sequence: fill → click → verify
# ---------------------------------------------------------------------------

@patch("gradio_tester.interact._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.interact.async_playwright", create=True)
def test_full_sequence_fill_click_verify(mock_async_pw):
    loc = _make_mock_locator(input_value="blue")
    page, _ = _make_mock_page(loc)
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.interact import execute_actions

    results = execute_actions("https://test.gradio.live", [
        {"action": "fill", "label": "Timestamp (seconds)", "value": "5.0"},
        {"action": "click", "label": "Check Color at Timestamp"},
        {"action": "verify", "label": "Dominant Color", "expected": "blue"},
    ])

    assert len(results) == 3
    assert all(r.passed for r in results)
    assert results[0].name == "interact_step_0_fill"
    assert results[1].name == "interact_step_1_click"
    assert results[2].name == "interact_step_2_verify"


# ---------------------------------------------------------------------------
# Short-circuit on failure
# ---------------------------------------------------------------------------

@patch("gradio_tester.interact._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.interact.async_playwright", create=True)
def test_short_circuit_on_failure(mock_async_pw):
    loc = _make_mock_locator()
    loc.click = AsyncMock(side_effect=Exception("Button not found"))
    page, _ = _make_mock_page(loc)
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.interact import execute_actions

    results = execute_actions("https://test.gradio.live", [
        {"action": "click", "label": "Missing Button"},
        {"action": "verify", "label": "Output", "expected": "something"},
    ])

    assert len(results) == 2
    assert results[0].passed is False
    assert "Button not found" in results[0].error
    assert results[1].passed is False
    assert "Skipped: previous step failed" in results[1].error


# ---------------------------------------------------------------------------
# Unknown action
# ---------------------------------------------------------------------------

@patch("gradio_tester.interact._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.interact.async_playwright", create=True)
def test_unknown_action_fails(mock_async_pw):
    page, _ = _make_mock_page()
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.interact import execute_actions

    results = execute_actions("https://test.gradio.live", [
        {"action": "dance", "label": "something"},
    ])

    assert len(results) == 1
    assert results[0].passed is False
    assert "Unknown action: dance" in results[0].error


# ---------------------------------------------------------------------------
# Navigation failure
# ---------------------------------------------------------------------------

@patch("gradio_tester.interact._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.interact.async_playwright", create=True)
def test_navigation_failure(mock_async_pw):
    page, _ = _make_mock_page()
    page.goto = AsyncMock(side_effect=Exception("net::ERR_CONNECTION_REFUSED"))
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.interact import execute_actions

    results = execute_actions("https://unreachable.gradio.live", [
        {"action": "fill", "label": "Input", "value": "test"},
        {"action": "click", "label": "Submit"},
    ])

    assert len(results) == 2
    assert all(r.passed is False for r in results)
    assert "Navigation failed" in results[0].error


# ---------------------------------------------------------------------------
# Wait action
# ---------------------------------------------------------------------------

@patch("gradio_tester.interact._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.interact.async_playwright", create=True)
def test_wait_action(mock_async_pw):
    page, _ = _make_mock_page()
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.interact import execute_actions

    results = execute_actions("https://test.gradio.live", [
        {"action": "wait", "ms": 100},
    ])

    assert len(results) == 1
    assert results[0].passed is True
    assert results[0].name == "interact_step_0_wait"


# ---------------------------------------------------------------------------
# Screenshot action
# ---------------------------------------------------------------------------

@patch("gradio_tester.interact._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.interact.async_playwright", create=True)
def test_screenshot_action(mock_async_pw):
    page, _ = _make_mock_page()
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.interact import execute_actions

    results = execute_actions("https://test.gradio.live", [
        {"action": "screenshot", "path": "/tmp/test.png"},
    ])

    assert len(results) == 1
    assert results[0].passed is True
    page.screenshot.assert_awaited_once()


# ---------------------------------------------------------------------------
# Seek video action
# ---------------------------------------------------------------------------

@patch("gradio_tester.interact._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.interact.async_playwright", create=True)
def test_seek_video_action(mock_async_pw):
    page, _ = _make_mock_page()

    # Mock a video locator
    video_loc = AsyncMock()
    video_loc.wait_for = AsyncMock()
    video_loc.evaluate = AsyncMock(return_value=5.0)

    # page.locator("video").first returns video_loc
    video_chain = MagicMock()
    video_chain.first = video_loc
    page.locator = MagicMock(return_value=video_chain)

    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.interact import execute_actions

    results = execute_actions("https://test.gradio.live", [
        {"action": "seek_video", "timestamp": 5.0},
    ])

    assert len(results) == 1
    assert results[0].passed is True
    assert results[0].name == "interact_step_0_seek_video"
    assert results[0].details["requested_timestamp"] == 5.0
    # evaluate called twice: once to seek, once to read back
    assert video_loc.evaluate.await_count == 2


# ---------------------------------------------------------------------------
# Read input action
# ---------------------------------------------------------------------------

@patch("gradio_tester.interact._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.interact.async_playwright", create=True)
def test_read_input_action(mock_async_pw):
    loc = _make_mock_locator(input_value="5.0")
    page, _ = _make_mock_page(loc)
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.interact import execute_actions

    results = execute_actions("https://test.gradio.live", [
        {"action": "read_input", "label": "Timestamp (seconds)"},
    ])

    assert len(results) == 1
    assert results[0].passed is True
    assert results[0].details["value"] == "5.0"


# ---------------------------------------------------------------------------
# Seek + click + verify sequence (simulates the video-timestamp bug)
# ---------------------------------------------------------------------------

@patch("gradio_tester.interact._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.interact.async_playwright", create=True)
def test_seek_then_verify_detects_stale_input(mock_async_pw):
    """After seeking video, if the input still has '0', verify catches the bug."""
    # The verify action reads input_value which returns "red" (the buggy output)
    loc = _make_mock_locator(input_value="red")
    page, _ = _make_mock_page(loc)

    video_loc = AsyncMock()
    video_loc.wait_for = AsyncMock()
    video_loc.evaluate = AsyncMock(return_value=5.0)
    video_chain = MagicMock()
    video_chain.first = video_loc

    # Loading indicator locator (returns count=0 = not busy)
    loading_loc = AsyncMock()
    loading_loc.count = AsyncMock(return_value=0)

    def smart_locator(selector):
        if selector == "video":
            return video_chain
        return loading_loc

    page.locator = MagicMock(side_effect=smart_locator)

    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.interact import execute_actions

    results = execute_actions("https://test.gradio.live", [
        {"action": "seek_video", "timestamp": 5.0},
        {"action": "click", "label": "Check Color at Timestamp"},
        {"action": "verify", "label": "Dominant Color", "expected": "blue"},
    ])

    assert len(results) == 3
    assert results[0].passed is True   # seek succeeded
    assert results[1].passed is True   # click succeeded
    assert results[2].passed is False  # verify caught the bug
    assert '"blue"' in results[2].error
    assert '"red"' in results[2].error


# ---------------------------------------------------------------------------
# Read slider action
# ---------------------------------------------------------------------------

@patch("gradio_tester.interact._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.interact.async_playwright", create=True)
def test_read_slider_action(mock_async_pw):
    loc = _make_mock_locator()
    loc.get_attribute = AsyncMock(return_value="2.5")
    page, _ = _make_mock_page(loc)
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.interact import execute_actions

    results = execute_actions("https://test.gradio.live", [
        {"action": "read_slider", "label": "Zoom"},
    ])

    assert len(results) == 1
    assert results[0].passed is True
    assert results[0].details["value"] == "2.5"


# ---------------------------------------------------------------------------
# Download file action
# ---------------------------------------------------------------------------

@patch("gradio_tester.interact._PLAYWRIGHT_AVAILABLE", True)
@patch("gradio_tester.interact.async_playwright", create=True)
def test_download_file_action(mock_async_pw):
    # Mock a download link
    link_loc = AsyncMock()
    link_loc.get_attribute = AsyncMock(return_value="/gradio_api/file=/tmp/export.mp4")

    loc = _make_mock_locator()
    container = AsyncMock()
    container.locator = MagicMock(return_value=AsyncMock(first=link_loc))
    loc_parent = AsyncMock()
    loc_parent.locator = MagicMock(return_value=container)
    loc.locator = MagicMock(return_value=loc_parent)

    page, _ = _make_mock_page(loc)
    page.get_by_label = MagicMock(return_value=loc)
    browser = _make_mock_browser(page)
    mock_async_pw.return_value = _make_mock_playwright(browser)

    from gradio_tester.interact import execute_actions

    results = execute_actions("https://test.gradio.live", [
        {"action": "download_file", "label": "Exported Video"},
    ])

    assert len(results) == 1
    assert results[0].passed is True
    assert "file" in results[0].details.get("url", "")
