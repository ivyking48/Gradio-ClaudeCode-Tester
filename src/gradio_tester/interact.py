"""Playwright-based UI interaction testing for Gradio apps."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from gradio_tester.models import TestResult

_PLAYWRIGHT_AVAILABLE = True
try:
    from playwright.async_api import async_playwright
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False

_GRADIO_CONTAINER = ".gradio-container"

# Gradio loading/processing indicators
_LOADING_SELECTORS = [
    ".progress-bar",
    ".generating",
    ".pending",
    ".eta-bar",
]


async def _wait_for_gradio_idle(page: Any, timeout_ms: int = 10000) -> None:
    """Wait until Gradio loading indicators disappear."""
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        busy = False
        for selector in _LOADING_SELECTORS:
            if await page.locator(selector).count() > 0:
                busy = True
                break
        if not busy:
            return
        await asyncio.sleep(0.1)
    raise TimeoutError(f"Gradio stayed busy for more than {timeout_ms}ms")


async def _do_fill(page: Any, action: dict, timeout_ms: int) -> TestResult:
    start = time.monotonic()
    label = action["label"]
    value = str(action["value"])
    try:
        locator = page.get_by_label(label)
        if action.get("clear", True):
            await locator.clear(timeout=timeout_ms)
        await locator.fill(value, timeout=timeout_ms)
        # Dispatch change event for Gradio's reactive system
        await locator.dispatch_event("change")
        elapsed = (time.monotonic() - start) * 1000
        return TestResult(
            name=f"interact_fill",
            passed=True,
            duration_ms=elapsed,
            details={"label": label, "value": value},
        )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return TestResult(
            name=f"interact_fill",
            passed=False,
            duration_ms=elapsed,
            details={"label": label, "value": value},
            error=str(e),
        )


async def _do_click(page: Any, action: dict, timeout_ms: int) -> TestResult:
    start = time.monotonic()
    label = action["label"]
    try:
        locator = page.get_by_role("button", name=label)
        await locator.click(timeout=timeout_ms)
        await _wait_for_gradio_idle(page, timeout_ms=timeout_ms)
        elapsed = (time.monotonic() - start) * 1000
        return TestResult(
            name=f"interact_click",
            passed=True,
            duration_ms=elapsed,
            details={"label": label},
        )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return TestResult(
            name=f"interact_click",
            passed=False,
            duration_ms=elapsed,
            details={"label": label},
            error=str(e),
        )


async def _do_verify(page: Any, action: dict, timeout_ms: int) -> TestResult:
    start = time.monotonic()
    label = action["label"]
    expected = str(action["expected"])
    use_contains = action.get("contains", False)
    verify_timeout = action.get("timeout_ms", timeout_ms)
    try:
        locator = page.get_by_label(label)

        # Poll until the output has a non-empty value or timeout
        deadline = time.monotonic() + verify_timeout / 1000
        actual = ""
        while time.monotonic() < deadline:
            # Try input_value first (for input/textarea), fall back to text_content
            try:
                actual = await locator.input_value(timeout=1000)
            except Exception:
                actual = await locator.text_content(timeout=1000) or ""
            actual = actual.strip()
            if actual:
                break
            await asyncio.sleep(0.2)

        elapsed = (time.monotonic() - start) * 1000

        if use_contains:
            passed = expected in actual
        else:
            passed = actual == expected

        return TestResult(
            name=f"interact_verify",
            passed=passed,
            duration_ms=elapsed,
            details={"label": label, "expected": expected, "actual": actual, "contains": use_contains},
            error=(
                f"Expected {'to contain ' if use_contains else ''}\"{expected}\", got \"{actual}\""
                if not passed else None
            ),
        )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return TestResult(
            name=f"interact_verify",
            passed=False,
            duration_ms=elapsed,
            details={"label": label, "expected": expected},
            error=str(e),
        )


async def _do_seek_video(page: Any, action: dict, timeout_ms: int) -> TestResult:
    """Seek a <video> element to a specific timestamp and pause it.

    Simulates what a user does when they scrub through a video and stop
    at a particular point. Uses JavaScript to set video.currentTime and
    dispatch pause/seeked events.
    """
    start = time.monotonic()
    timestamp = float(action["timestamp"])
    label = action.get("label")  # Optional: find video by Gradio label
    try:
        # Find the video element
        if label:
            # Look for video inside a labeled Gradio component
            selector = f'label:has-text("{label}")'
            container = page.locator(selector).locator("..").locator("..")
            video_el = container.locator("video").first
        else:
            video_el = page.locator("video").first

        await video_el.wait_for(state="attached", timeout=timeout_ms)

        # Seek and pause via JavaScript
        await video_el.evaluate(
            """(el, ts) => {
                el.currentTime = ts;
                el.pause();
                el.dispatchEvent(new Event('seeked'));
                el.dispatchEvent(new Event('pause'));
            }""",
            timestamp,
        )

        # Also update any Number input linked to timestamp via Gradio's
        # internal event system. Find inputs with labels containing
        # "timestamp" and set their value + trigger input/change events
        # so Gradio picks up the change.
        if action.get("sync_input"):
            sync_label = action["sync_input"]
            input_locator = page.get_by_label(sync_label)
            await input_locator.clear(timeout=timeout_ms)
            await input_locator.fill(str(timestamp), timeout=timeout_ms)
            await input_locator.dispatch_event("input")
            await input_locator.dispatch_event("change")

        # Small wait for Gradio to react to events
        await asyncio.sleep(0.5)

        # Read back the actual currentTime
        actual_time = await video_el.evaluate("el => el.currentTime")
        elapsed = (time.monotonic() - start) * 1000

        return TestResult(
            name="interact_seek_video",
            passed=True,
            duration_ms=elapsed,
            details={
                "requested_timestamp": timestamp,
                "actual_timestamp": round(actual_time, 2),
                "label": label,
            },
        )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return TestResult(
            name="interact_seek_video",
            passed=False,
            duration_ms=elapsed,
            details={"timestamp": timestamp, "label": label},
            error=str(e),
        )


async def _do_read_input(page: Any, action: dict, timeout_ms: int) -> TestResult:
    """Read the current value of an input component and report it.

    Useful for debugging: check what value a Number/Textbox has before
    clicking a button, to see if video seek updated it or not.
    """
    start = time.monotonic()
    label = action["label"]
    try:
        locator = page.get_by_label(label)
        try:
            value = await locator.input_value(timeout=timeout_ms)
        except Exception:
            value = await locator.text_content(timeout=timeout_ms) or ""
        value = value.strip()
        elapsed = (time.monotonic() - start) * 1000

        return TestResult(
            name="interact_read_input",
            passed=True,
            duration_ms=elapsed,
            details={"label": label, "value": value},
        )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return TestResult(
            name="interact_read_input",
            passed=False,
            duration_ms=elapsed,
            details={"label": label},
            error=str(e),
        )


async def _do_read_slider(page: Any, action: dict, timeout_ms: int) -> TestResult:
    """Read the current value of a slider by its label."""
    start = time.monotonic()
    label = action["label"]
    try:
        locator = page.get_by_label(label)
        # Sliders use aria-valuenow or an input[type=range]
        value = await locator.get_attribute("aria-valuenow", timeout=timeout_ms)
        if value is None:
            # Try reading as input value
            value = await locator.input_value(timeout=timeout_ms)
        elapsed = (time.monotonic() - start) * 1000
        return TestResult(
            name="interact_read_slider",
            passed=True,
            duration_ms=elapsed,
            details={"label": label, "value": value},
        )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return TestResult(
            name="interact_read_slider",
            passed=False,
            duration_ms=elapsed,
            details={"label": label},
            error=str(e),
        )


async def _do_download_file(page: Any, action: dict, timeout_ms: int) -> TestResult:
    """Find a download link in a gr.File component and return its URL."""
    start = time.monotonic()
    label = action.get("label", "")
    try:
        # Look for download link near the label
        if label:
            container = page.get_by_label(label).locator("..").locator("..")
            link = container.locator("a[download], a[href*='/file=']").first
        else:
            link = page.locator("a[download], a[href*='/file=']").first

        href = await link.get_attribute("href", timeout=timeout_ms)
        elapsed = (time.monotonic() - start) * 1000

        return TestResult(
            name="interact_download_file",
            passed=href is not None and len(href) > 0,
            duration_ms=elapsed,
            details={"label": label, "url": href},
            error=None if href else "No download link found",
        )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return TestResult(
            name="interact_download_file",
            passed=False,
            duration_ms=elapsed,
            details={"label": label},
            error=str(e),
        )


async def _do_wait(page: Any, action: dict, timeout_ms: int) -> TestResult:
    ms = action.get("ms", 1000)
    await asyncio.sleep(ms / 1000)
    return TestResult(
        name="interact_wait",
        passed=True,
        duration_ms=ms,
        details={"ms": ms},
    )


async def _do_screenshot(page: Any, action: dict, timeout_ms: int) -> TestResult:
    start = time.monotonic()
    path = action.get("path", "interact_screenshot.png")
    try:
        await page.screenshot(path=path, full_page=True)
        elapsed = (time.monotonic() - start) * 1000
        return TestResult(
            name="interact_screenshot",
            passed=True,
            duration_ms=elapsed,
            details={"path": path},
        )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return TestResult(
            name="interact_screenshot",
            passed=False,
            duration_ms=elapsed,
            details={"path": path},
            error=str(e),
        )


_ACTION_HANDLERS = {
    "fill": _do_fill,
    "click": _do_click,
    "verify": _do_verify,
    "seek_video": _do_seek_video,
    "read_input": _do_read_input,
    "read_slider": _do_read_slider,
    "download_file": _do_download_file,
    "wait": _do_wait,
    "screenshot": _do_screenshot,
}


async def _execute_actions_async(
    url: str,
    actions: list[dict[str, Any]],
    timeout_ms: int = 15000,
    viewport: tuple[int, int] = (1280, 720),
) -> list[TestResult]:
    """Execute a sequence of UI actions against a Gradio app."""
    results: list[TestResult] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})

        try:
            await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            try:
                await page.wait_for_selector(_GRADIO_CONTAINER, timeout=timeout_ms)
            except Exception:
                pass  # Continue even if container not found immediately
        except Exception as e:
            # Navigation failed — skip all actions
            for i, action in enumerate(actions):
                results.append(TestResult(
                    name=f"interact_step_{i}_{action.get('action', 'unknown')}",
                    passed=False,
                    duration_ms=0,
                    details={"step": i, "action": action},
                    error=f"Navigation failed: {e}",
                ))
            await browser.close()
            return results

        failed = False
        for i, action in enumerate(actions):
            action_type = action.get("action", "unknown")

            if failed:
                results.append(TestResult(
                    name=f"interact_step_{i}_{action_type}",
                    passed=False,
                    duration_ms=0,
                    details={"step": i, "action": action},
                    error="Skipped: previous step failed",
                ))
                continue

            handler = _ACTION_HANDLERS.get(action_type)
            if handler is None:
                results.append(TestResult(
                    name=f"interact_step_{i}_{action_type}",
                    passed=False,
                    duration_ms=0,
                    details={"step": i, "action": action},
                    error=f"Unknown action: {action_type}",
                ))
                failed = True
                continue

            result = handler(page, action, timeout_ms)
            result = await result
            # Enrich with step info
            result.details["step"] = i
            result.details["action"] = action
            # Override name to include step index
            result.name = f"interact_step_{i}_{action_type}"
            results.append(result)

            if not result.passed:
                failed = True

        await browser.close()

    return results


def execute_actions(
    url: str,
    actions: list[dict[str, Any]],
    timeout_ms: int = 15000,
    viewport: tuple[int, int] = (1280, 720),
) -> list[TestResult]:
    """Execute UI actions against a Gradio app.

    Returns one TestResult per action. Short-circuits on failure.
    Returns error results if Playwright is not installed.
    """
    if not _PLAYWRIGHT_AVAILABLE:
        return [
            TestResult(
                name=f"interact_step_{i}_{a.get('action', 'unknown')}",
                passed=False,
                duration_ms=0,
                details={"step": i, "action": a},
                error="playwright not installed — install with: pip install playwright && playwright install chromium",
            )
            for i, a in enumerate(actions)
        ]
    if not actions:
        return []
    return asyncio.run(
        _execute_actions_async(url, actions, timeout_ms, viewport)
    )


def run_interaction_checks(
    url: str,
    actions: list[dict[str, Any]],
    timeout_ms: int = 15000,
    viewport: tuple[int, int] = (1280, 720),
) -> list[TestResult]:
    """Entry point for runner.py integration."""
    return execute_actions(url, actions, timeout_ms, viewport)
