"""API introspection via Gradio /info and /config endpoints."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from gradio_tester.models import TestResult


def _fetch_json(url: str, timeout: float = 10.0) -> tuple[dict[str, Any], float]:
    """Fetch a JSON endpoint and return (data, elapsed_ms)."""
    start = time.monotonic()
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", "gradio-tester/0.1.0")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        elapsed = (time.monotonic() - start) * 1000
        data = json.loads(resp.read().decode("utf-8"))
        return data, elapsed


def get_config(url: str, timeout: float = 10.0) -> TestResult:
    """Fetch and parse the /config endpoint.

    Returns component inventory: list of {id, type, label, props}.
    """
    endpoint = url.rstrip("/") + "/config"
    try:
        data, elapsed = _fetch_json(endpoint, timeout=timeout)

        # Extract components from the config
        components = []
        for comp in data.get("components", []):
            components.append({
                "id": comp.get("id"),
                "type": comp.get("type"),
                "label": comp.get("props", {}).get("label"),
                "props": comp.get("props", {}),
            })

        return TestResult(
            name="introspect_config",
            passed=True,
            duration_ms=elapsed,
            details={
                "gradio_version": data.get("version"),
                "mode": data.get("mode"),
                "title": data.get("title", data.get("app_id")),
                "component_count": len(components),
                "components": components,
                "dependencies_count": len(data.get("dependencies", [])),
            },
        )
    except Exception as e:
        return TestResult(
            name="introspect_config",
            passed=False,
            duration_ms=0,
            error=str(e),
        )


def get_api_info(url: str, timeout: float = 10.0) -> TestResult:
    """Fetch and parse the /info endpoint.

    Returns API schema: endpoints with their parameters and return types.
    """
    endpoint = url.rstrip("/") + "/info"
    try:
        data, elapsed = _fetch_json(endpoint, timeout=timeout)

        # Parse named endpoints
        endpoints = {}
        named = data.get("named_endpoints", {})
        for ep_name, ep_info in named.items():
            endpoints[ep_name] = {
                "parameters": [
                    {
                        "label": p.get("label"),
                        "type": p.get("type", {}).get("type") if isinstance(p.get("type"), dict) else p.get("type"),
                        "component": p.get("component"),
                    }
                    for p in ep_info.get("parameters", [])
                ],
                "returns": [
                    {
                        "label": r.get("label"),
                        "type": r.get("type", {}).get("type") if isinstance(r.get("type"), dict) else r.get("type"),
                        "component": r.get("component"),
                    }
                    for r in ep_info.get("returns", [])
                ],
            }

        return TestResult(
            name="introspect_api_info",
            passed=True,
            duration_ms=elapsed,
            details={
                "endpoint_count": len(endpoints),
                "endpoints": endpoints,
                "unnamed_endpoint_count": len(data.get("unnamed_endpoints", {})),
            },
        )
    except Exception as e:
        return TestResult(
            name="introspect_api_info",
            passed=False,
            duration_ms=0,
            error=str(e),
        )


def validate_components(
    url: str,
    expected: dict[str, str],
    timeout: float = 10.0,
) -> TestResult:
    """Validate that the app contains expected components.

    Args:
        url: Gradio app URL.
        expected: Dict of {label: component_type}, e.g. {"Location": "textbox"}.
    """
    config_result = get_config(url, timeout=timeout)
    if not config_result.passed:
        return TestResult(
            name="introspect_validate_components",
            passed=False,
            duration_ms=config_result.duration_ms,
            error=f"Could not fetch config: {config_result.error}",
        )

    components = config_result.details.get("components", [])
    missing = []
    wrong_type = []

    for label, expected_type in expected.items():
        matches = [c for c in components if c.get("label") == label]
        if not matches:
            missing.append(label)
        elif matches[0].get("type", "").lower() != expected_type.lower():
            wrong_type.append({
                "label": label,
                "expected": expected_type,
                "actual": matches[0].get("type"),
            })

    passed = len(missing) == 0 and len(wrong_type) == 0
    return TestResult(
        name="introspect_validate_components",
        passed=passed,
        duration_ms=config_result.duration_ms,
        details={
            "missing": missing,
            "wrong_type": wrong_type,
            "checked": len(expected),
        },
        error=None if passed else f"Missing: {missing}, Wrong type: {wrong_type}",
    )


def run_introspection(
    url: str,
    expected_components: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> list[TestResult]:
    """Run all introspection checks."""
    results = [
        get_config(url, timeout=timeout),
        get_api_info(url, timeout=timeout),
    ]
    if expected_components:
        results.append(validate_components(url, expected_components, timeout=timeout))
    return results
