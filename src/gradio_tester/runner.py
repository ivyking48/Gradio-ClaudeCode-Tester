"""Orchestrator that runs all checks and aggregates results."""

from __future__ import annotations

from typing import Any

from gradio_tester.models import AppReport, TestResult

ALL_CHECKS = ["health", "introspect", "client", "screenshot"]


def run_all_checks(
    url: str,
    checks: list[str] | None = None,
    endpoint_inputs: dict[str, list[Any]] | None = None,
    expected_components: dict[str, str] | None = None,
    variance_checks: dict[str, list[list[Any]]] | None = None,
    interact_actions: list[dict[str, Any]] | None = None,
    screenshot_path: str = "screenshot.png",
    timeout: float = 30.0,
) -> AppReport:
    """Run selected checks against a Gradio app URL.

    Args:
        url: Gradio share URL.
        checks: List of check names to run. Defaults to all.
        endpoint_inputs: Dict of {api_name: [inputs]} for client checks.
        expected_components: Dict of {label: component_type} for validation.
        variance_checks: Dict of {api_name: [[inputs1], [inputs2], ...]} to
            verify that an endpoint produces different outputs for different inputs.
        screenshot_path: Where to save screenshots.
        timeout: Per-check timeout in seconds.

    Returns:
        AppReport with all results.
    """
    checks = checks or ALL_CHECKS
    report = AppReport(url=url)

    # Health checks always run first
    if "health" in checks:
        from gradio_tester.health import run_health_checks

        health_results = run_health_checks(url, timeout=timeout)
        report.results.extend(health_results)

        # Check if app is reachable
        reachable_result = next(
            (r for r in health_results if r.name == "health_reachable"), None
        )
        report.reachable = reachable_result is not None and reachable_result.passed

        # Short-circuit if not reachable
        if not report.reachable:
            for check_name in checks:
                if check_name != "health":
                    report.results.append(
                        TestResult(
                            name=f"{check_name}_skipped",
                            passed=False,
                            duration_ms=0,
                            error="Skipped: app not reachable",
                        )
                    )
            return report
    else:
        report.reachable = True  # Assume reachable if health checks skipped

    # Introspection
    if "introspect" in checks:
        from gradio_tester.introspect import run_introspection

        report.results.extend(
            run_introspection(url, expected_components=expected_components, timeout=timeout)
        )

    # Client endpoint calls
    if "client" in checks:
        from gradio_tester.client import call_all_endpoints

        report.results.extend(
            call_all_endpoints(url, endpoint_inputs=endpoint_inputs, timeout=timeout)
        )

    # Output variance checks
    if variance_checks:
        from gradio_tester.client import check_output_variance

        for api_name, input_samples in variance_checks.items():
            report.results.append(
                check_output_variance(url, api_name=api_name, input_samples=input_samples, timeout=timeout)
            )

    # Screenshots
    if "screenshot" in checks:
        from gradio_tester.screenshot import run_screenshot_checks

        report.results.extend(
            run_screenshot_checks(url, output_path=screenshot_path, timeout_ms=int(timeout * 1000))
        )

    # UI interaction
    if interact_actions:
        from gradio_tester.interact import run_interaction_checks

        report.results.extend(
            run_interaction_checks(url, actions=interact_actions, timeout_ms=int(timeout * 1000))
        )

    return report
