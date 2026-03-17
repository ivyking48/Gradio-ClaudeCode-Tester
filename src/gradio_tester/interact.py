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
