"""Health checks and error detection for Gradio apps (stdlib only)."""

from __future__ import annotations

import time
import urllib.error
import urllib.request

from gradio_tester.models import TestResult

# Common error patterns in Gradio/Colab responses
_ERROR_PATTERNS = {
    "tunnel expired": "Gradio share link has expired",
    "no healthy upstream": "Colab runtime disconnected",
    "runtime disconnected": "Colab runtime disconnected",
    "exceeded the time limit": "Colab session timed out",
}


def check_reachable(url: str, timeout: float = 15.0) -> TestResult:
    """Check if the Gradio app URL is reachable via HTTP GET."""
    start = time.monotonic()
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "gradio-tester/0.1.0")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            body = resp.read(4096).decode("utf-8", errors="replace")
            elapsed = (time.monotonic() - start) * 1000

            # Check for error patterns in the response body
            for pattern, message in _ERROR_PATTERNS.items():
                if pattern in body.lower():
                    return TestResult(
                        name="health_reachable",
                        passed=False,
                        duration_ms=elapsed,
                        details={"status_code": status, "error_pattern": pattern},
                        error=message,
                    )

            is_gradio = "gradio" in body.lower() or "gradio" in str(resp.headers).lower()

            return TestResult(
                name="health_reachable",
                passed=status == 200,
                duration_ms=elapsed,
                details={
                    "status_code": status,
                    "response_time_ms": round(elapsed, 1),
                    "is_gradio_app": is_gradio,
                },
            )
    except urllib.error.HTTPError as e:
        elapsed = (time.monotonic() - start) * 1000
        return TestResult(
            name="health_reachable",
            passed=False,
            duration_ms=elapsed,
            details={"status_code": e.code},
            error=f"HTTP {e.code}: {e.reason}",
        )
    except urllib.error.URLError as e:
        elapsed = (time.monotonic() - start) * 1000
        return TestResult(
            name="health_reachable",
            passed=False,
            duration_ms=elapsed,
            error=f"Connection failed: {e.reason}",
        )
    except TimeoutError:
        elapsed = (time.monotonic() - start) * 1000
        return TestResult(
            name="health_reachable",
            passed=False,
            duration_ms=elapsed,
            error=f"Timeout after {timeout}s",
        )


def check_queue_status(url: str, timeout: float = 10.0) -> TestResult:
    """Check the Gradio queue/status endpoint for app health."""
    endpoint = url.rstrip("/") + "/queue/status"
    start = time.monotonic()
    try:
        import json

        req = urllib.request.Request(endpoint, method="GET")
        req.add_header("User-Agent", "gradio-tester/0.1.0")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = (time.monotonic() - start) * 1000
            data = json.loads(resp.read().decode("utf-8"))
            return TestResult(
                name="health_queue_status",
                passed=True,
                duration_ms=elapsed,
                details={"queue_status": data},
            )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return TestResult(
            name="health_queue_status",
            passed=False,
            duration_ms=elapsed,
            error=str(e),
        )


def run_health_checks(url: str, timeout: float = 15.0) -> list[TestResult]:
    """Run all health checks and return results."""
    results = []
    reachable = check_reachable(url, timeout=timeout)
    results.append(reachable)

    # Only check queue if the app is reachable
    if reachable.passed:
        results.append(check_queue_status(url, timeout=timeout))

    return results
