"""Gradio Python Client wrapper for endpoint testing."""

from __future__ import annotations

import time
from typing import Any

from gradio_tester.models import TestResult


def list_endpoints(url: str, timeout: float = 30.0) -> TestResult:
    """Connect to a Gradio app and list its API endpoints."""
    start = time.monotonic()
    try:
        from gradio_client import Client

        client = Client(url)
        # view_api returns info dict; print_info=False suppresses stdout
        api_info = client.view_api(print_info=False, return_format="dict")
        elapsed = (time.monotonic() - start) * 1000

        named = api_info.get("named_endpoints", {})
        unnamed = api_info.get("unnamed_endpoints", {})

        endpoint_summary = {}
        for ep_name, ep_info in named.items():
            endpoint_summary[ep_name] = {
                "parameters": [
                    {"label": p.get("label"), "type": p.get("type"), "component": p.get("component")}
                    for p in ep_info.get("parameters", [])
                ],
                "returns": [
                    {"label": r.get("label"), "type": r.get("type"), "component": r.get("component")}
                    for r in ep_info.get("returns", [])
                ],
            }

        return TestResult(
            name="client_list_endpoints",
            passed=True,
            duration_ms=elapsed,
            details={
                "named_endpoints": endpoint_summary,
                "unnamed_endpoint_count": len(unnamed),
            },
        )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return TestResult(
            name="client_list_endpoints",
            passed=False,
            duration_ms=elapsed,
            error=str(e),
        )


def call_endpoint(
    url: str,
    api_name: str = "/predict",
    inputs: list[Any] | None = None,
    expected_output_type: type | None = None,
    timeout: float = 60.0,
) -> TestResult:
    """Call a specific Gradio API endpoint and validate the response."""
    start = time.monotonic()
    try:
        from gradio_client import Client

        client = Client(url)
        args = inputs or []
        result = client.predict(*args, api_name=api_name)
        elapsed = (time.monotonic() - start) * 1000

        details: dict[str, Any] = {
            "api_name": api_name,
            "inputs": args,
            "output": result if _is_serializable(result) else str(result),
            "output_type": type(result).__name__,
        }

        passed = True
        error = None

        if expected_output_type is not None:
            if not isinstance(result, expected_output_type):
                passed = False
                error = f"Expected output type {expected_output_type.__name__}, got {type(result).__name__}"
                details["expected_type"] = expected_output_type.__name__

        return TestResult(
            name="client_call_endpoint",
            passed=passed,
            duration_ms=elapsed,
            details=details,
            error=error,
        )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return TestResult(
            name="client_call_endpoint",
            passed=False,
            duration_ms=elapsed,
            details={"api_name": api_name, "inputs": inputs},
            error=str(e),
        )


def call_all_endpoints(
    url: str,
    endpoint_inputs: dict[str, list[Any]] | None = None,
    timeout: float = 60.0,
) -> list[TestResult]:
    """Call multiple endpoints. If no inputs provided, just lists endpoints."""
    results = []
    endpoints_result = list_endpoints(url, timeout=timeout)
    results.append(endpoints_result)

    if endpoint_inputs and endpoints_result.passed:
        for api_name, inputs in endpoint_inputs.items():
            results.append(call_endpoint(url, api_name=api_name, inputs=inputs, timeout=timeout))

    return results


def check_output_variance(
    url: str,
    api_name: str,
    input_samples: list[list[Any]],
    timeout: float = 60.0,
) -> TestResult:
    """Call an endpoint with multiple inputs and check that outputs vary.

    Catches bugs where an endpoint ignores its input and always returns
    the same value (e.g., a UI default is always sent instead of user input).

    Args:
        url: Gradio app URL.
        api_name: Endpoint name (e.g., "/get_color_at_timestamp").
        input_samples: List of input arg lists to try, e.g. [[0], [5], [9]].
        timeout: Per-call timeout in seconds.
    """
    start = time.monotonic()
    try:
        from gradio_client import Client

        client = Client(url)
        calls = []
        outputs = set()

        for inputs in input_samples:
            result = client.predict(*inputs, api_name=api_name)
            output_str = str(result)
            outputs.add(output_str)
            calls.append({"inputs": inputs, "output": result if _is_serializable(result) else output_str})

        elapsed = (time.monotonic() - start) * 1000
        all_same = len(outputs) == 1
        passed = not all_same

        return TestResult(
            name="client_output_variance",
            passed=passed,
            duration_ms=elapsed,
            details={
                "api_name": api_name,
                "calls": calls,
                "unique_outputs": len(outputs),
                "total_calls": len(input_samples),
            },
            error=(
                f"Endpoint always returns {next(iter(outputs))!r} for {len(input_samples)} "
                f"different inputs — output may be ignoring input"
                if all_same else None
            ),
        )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return TestResult(
            name="client_output_variance",
            passed=False,
            duration_ms=elapsed,
            details={"api_name": api_name},
            error=str(e),
        )


def _is_serializable(obj: Any) -> bool:
    """Check if an object is JSON-serializable."""
    import json

    try:
        json.dumps(obj, default=str)
        return True
    except (TypeError, ValueError):
        return False
