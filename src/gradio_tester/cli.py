"""CLI entry point for gradio-tester."""

from __future__ import annotations

import argparse
import json
import sys

from gradio_tester.runner import ALL_CHECKS, run_all_checks


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="gradio-tester",
        description="Test and verify Gradio web applications",
    )
    parser.add_argument("url", help="Gradio app URL (e.g., https://abc123.gradio.live)")
    parser.add_argument(
        "--checks",
        default=",".join(ALL_CHECKS),
        help=f"Comma-separated checks to run (default: {','.join(ALL_CHECKS)})",
    )
    parser.add_argument(
        "--call",
        nargs=2,
        action="append",
        metavar=("ENDPOINT", "ARGS_JSON"),
        help='Call an endpoint: --call /predict \'["arg1", "arg2"]\'',
    )
    parser.add_argument(
        "--check-variance",
        nargs=2,
        action="append",
        metavar=("ENDPOINT", "SAMPLES_JSON"),
        help='Check output varies across inputs: --check-variance /predict \'[[0], [5], [9]]\'',
    )
    parser.add_argument(
        "--expect-components",
        type=str,
        default=None,
        help='JSON dict of expected components: \'{"Location": "textbox"}\'',
    )
    parser.add_argument(
        "--screenshot",
        default="screenshot.png",
        help="Screenshot output path (default: screenshot.png)",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="Per-check timeout in seconds")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output only JSON")

    args = parser.parse_args(argv)

    checks = [c.strip() for c in args.checks.split(",")]

    # Parse endpoint inputs
    endpoint_inputs = None
    if args.call:
        endpoint_inputs = {}
        for ep_name, args_json in args.call:
            endpoint_inputs[ep_name] = json.loads(args_json)

    # Parse variance checks
    variance_checks = None
    if args.check_variance:
        variance_checks = {}
        for ep_name, samples_json in args.check_variance:
            variance_checks[ep_name] = json.loads(samples_json)

    # Parse expected components
    expected_components = None
    if args.expect_components:
        expected_components = json.loads(args.expect_components)

    if not args.json_output:
        print(f"Testing: {args.url}")
        print(f"Checks: {', '.join(checks)}")
        print()

    report = run_all_checks(
        url=args.url,
        checks=checks,
        endpoint_inputs=endpoint_inputs,
        expected_components=expected_components,
        variance_checks=variance_checks,
        screenshot_path=args.screenshot,
        timeout=args.timeout,
    )

    if args.json_output:
        print(report.to_json())
    else:
        # Human-readable output
        for result in report.results:
            status = "PASS" if result.passed else "FAIL"
            line = f"  [{status}] {result.name}"
            if result.error:
                line += f" — {result.error}"
            elif result.duration_ms:
                line += f" ({result.duration_ms:.0f}ms)"
            print(line)
        print()
        print(report.summary())
        print()
        print("JSON output:")
        print(report.to_json())

    sys.exit(0 if all(r.passed for r in report.results) else 1)


if __name__ == "__main__":
    main()
