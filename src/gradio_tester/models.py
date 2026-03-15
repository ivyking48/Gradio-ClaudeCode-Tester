"""Structured result types for all test modules."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class TestResult:
    """Result of a single test check.

    Every module in the framework returns one or more TestResult instances.
    The `details` dict carries module-specific data (component lists,
    screenshot paths, response payloads, etc.).
    """

    name: str
    passed: bool
    duration_ms: float
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


@dataclass
class AppReport:
    """Aggregated report for all checks run against a Gradio app."""

    url: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reachable: bool = False
    results: list[TestResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "timestamp": self.timestamp,
            "reachable": self.reachable,
            "results": [r.to_dict() for r in self.results],
            "summary": self.summary(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)

    def summary(self) -> str:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        if passed == total and total > 0:
            return f"PASS: {passed}/{total} checks passed for {self.url}"
        failed_names = [r.name for r in self.results if not r.passed]
        return f"FAIL: {passed}/{total} checks passed (failed: {', '.join(failed_names)})"
