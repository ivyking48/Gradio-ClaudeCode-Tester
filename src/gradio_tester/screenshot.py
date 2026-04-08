"""Playwright-based screenshot capture and visual error detection."""

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


# CSS selectors for common Gradio error indicators
_ERROR_SELECTORS = [
    ".error",                    # Generic error class
    ".toast-body.error",         # Gradio toast errors
    "[data-testid='error']",     # Test-id based errors
    ".message.error",            # Error messages
]

_GRADIO_CONTAINER = ".gradio-container"


async def _capture_screenshot_async(
    url: str,
    output_path: str = "screenshot.png",
    wait_for: str = _GRADIO_CONTAINER,
    timeout_ms: int = 15000,
    viewport: tuple[int, int] = (1280, 720),
) -> TestResult:
    """Async implementation of screenshot capture."""
    start = time.monotonic()
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})

            await page.goto(url, wait_until="networkidle", timeout=timeout_ms)

            # Wait for the Gradio container to appear
            try:
                await page.wait_for_selector(wait_for, timeout=timeout_ms)
            except Exception:
                pass  # Still capture screenshot even if selector not found

            await page.screenshot(path=output_path, full_page=True)
            elapsed = (time.monotonic() - start) * 1000

            # Get page title
            title = await page.title()

            await browser.close()

            return TestResult(
                name="screenshot_capture",
                passed=True,
                duration_ms=elapsed,
                details={
                    "output_path": output_path,
                    "viewport": f"{viewport[0]}x{viewport[1]}",
                    "page_title": title,
                },
            )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return TestResult(
            name="screenshot_capture",
            passed=False,
            duration_ms=elapsed,
            details={"output_path": output_path},
            error=str(e),
        )


async def _check_for_errors_async(
    url: str,
    timeout_ms: int = 15000,
    viewport: tuple[int, int] = (1280, 720),
) -> TestResult:
    """Check the rendered page for visible error elements."""
    start = time.monotonic()
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
            console_errors = []
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
            )

            await page.goto(url, wait_until="networkidle", timeout=timeout_ms)

            try:
                await page.wait_for_selector(_GRADIO_CONTAINER, timeout=timeout_ms)
            except Exception:
                pass

            errors_found = []
            for selector in _ERROR_SELECTORS:
                elements = await page.query_selector_all(selector)
                for el in elements:
                    text = await el.text_content()
                    if text and text.strip():
                        errors_found.append({
                            "selector": selector,
                            "text": text.strip()[:200],
                        })

            await browser.close()
            elapsed = (time.monotonic() - start) * 1000
            failure_count = len(errors_found) + len(console_errors)

            return TestResult(
                name="screenshot_error_check",
                passed=failure_count == 0,
                duration_ms=elapsed,
                details={
                    "errors_found": errors_found,
                    "error_count": len(errors_found),
                    "console_errors": console_errors[:10],
                },
                error=(
                    f"Found {len(errors_found)} DOM error(s) and {len(console_errors)} console error(s)"
                    if failure_count
                    else None
                ),
            )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return TestResult(
            name="screenshot_error_check",
            passed=False,
            duration_ms=elapsed,
            error=str(e),
        )


def capture_screenshot(
    url: str,
    output_path: str = "screenshot.png",
    wait_for: str = _GRADIO_CONTAINER,
    timeout_ms: int = 15000,
    viewport: tuple[int, int] = (1280, 720),
) -> TestResult:
    """Capture a screenshot of a Gradio app.

    Returns a skipped TestResult if playwright is not installed.
    """
    if not _PLAYWRIGHT_AVAILABLE:
        return TestResult(
            name="screenshot_capture",
            passed=False,
            duration_ms=0,
            error="playwright not installed — install with: pip install playwright && playwright install chromium",
        )
    return asyncio.run(
        _capture_screenshot_async(url, output_path, wait_for, timeout_ms, viewport)
    )


def check_for_errors(
    url: str,
    timeout_ms: int = 15000,
    viewport: tuple[int, int] = (1280, 720),
) -> TestResult:
    """Check the rendered page for visible errors.

    Returns a skipped TestResult if playwright is not installed.
    """
    if not _PLAYWRIGHT_AVAILABLE:
        return TestResult(
            name="screenshot_error_check",
            passed=False,
            duration_ms=0,
            error="playwright not installed — install with: pip install playwright && playwright install chromium",
        )
    return asyncio.run(
        _check_for_errors_async(url, timeout_ms, viewport)
    )


def run_screenshot_checks(
    url: str,
    output_path: str = "screenshot.png",
    timeout_ms: int = 15000,
    viewport: tuple[int, int] = (1280, 720),
) -> list[TestResult]:
    """Run all screenshot-based checks."""
    return [
        capture_screenshot(url, output_path, timeout_ms=timeout_ms, viewport=viewport),
        check_for_errors(url, timeout_ms=timeout_ms, viewport=viewport),
    ]
