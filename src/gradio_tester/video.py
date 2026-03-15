"""Video frame extraction and color verification.

Extracts frames from videos (local or URL) using ffmpeg, analyzes
dominant colors, and verifies against expected color sequences.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
from typing import Any

from gradio_tester.models import TestResult

# Named color RGB ranges — (min_r, max_r, min_g, max_g, min_b, max_b)
COLOR_RANGES: dict[str, tuple[int, int, int, int, int, int]] = {
    "red":     (180, 255, 0, 80, 0, 80),
    "green":   (0, 80, 100, 255, 0, 80),
    "blue":    (0, 80, 0, 80, 180, 255),
    "white":   (200, 255, 200, 255, 200, 255),
    "black":   (0, 55, 0, 55, 0, 55),
    "yellow":  (180, 255, 180, 255, 0, 80),
    "cyan":    (0, 80, 180, 255, 180, 255),
    "magenta": (180, 255, 0, 80, 180, 255),
}


def _identify_color(r: float, g: float, b: float) -> str:
    """Identify the closest named color from RGB values."""
    for name, (r_min, r_max, g_min, g_max, b_min, b_max) in COLOR_RANGES.items():
        if r_min <= r <= r_max and g_min <= g <= g_max and b_min <= b <= b_max:
            return name
    return f"unknown(r={r:.0f},g={g:.0f},b={b:.0f})"


def _get_avg_color_ffmpeg(video_path: str, timestamp: float) -> tuple[float, float, float]:
    """Extract a single frame at `timestamp` and compute its average RGB color.

    Uses ffmpeg to extract the frame as raw RGB pixels and averages them.
    """
    cmd = [
        "ffmpeg", "-ss", str(timestamp), "-i", video_path,
        "-vframes", "1", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-v", "quiet", "-"
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=15)
    if result.returncode != 0 or len(result.stdout) == 0:
        raise RuntimeError(f"ffmpeg failed to extract frame at {timestamp}s")

    raw = result.stdout
    pixel_count = len(raw) // 3
    r_sum = g_sum = b_sum = 0
    for i in range(0, len(raw), 3):
        r_sum += raw[i]
        g_sum += raw[i + 1]
        b_sum += raw[i + 2]

    return r_sum / pixel_count, g_sum / pixel_count, b_sum / pixel_count


def _download_video(url: str, dest_dir: str) -> str:
    """Download a video from a URL to a local temp file."""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "gradio-tester/0.1.0")
    local_path = os.path.join(dest_dir, "downloaded_video.mp4")
    with urllib.request.urlopen(req, timeout=60) as resp:
        with open(local_path, "wb") as f:
            shutil.copyfileobj(resp, f)
    return local_path


def extract_frame_color(
    video_path: str,
    timestamp: float,
) -> TestResult:
    """Extract a frame at `timestamp` and identify its dominant color.

    Args:
        video_path: Local file path or URL to a video.
        timestamp: Time in seconds to extract the frame.
    """
    start = time.monotonic()
    tmp_dir = None
    try:
        # If it's a URL, download first
        actual_path = video_path
        if video_path.startswith(("http://", "https://")):
            tmp_dir = tempfile.mkdtemp(prefix="gradio_tester_")
            actual_path = _download_video(video_path, tmp_dir)

        r, g, b = _get_avg_color_ffmpeg(actual_path, timestamp)
        color = _identify_color(r, g, b)
        elapsed = (time.monotonic() - start) * 1000

        return TestResult(
            name="video_frame_color",
            passed=True,
            duration_ms=elapsed,
            details={
                "timestamp": timestamp,
                "avg_rgb": [round(r, 1), round(g, 1), round(b, 1)],
                "identified_color": color,
            },
        )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return TestResult(
            name="video_frame_color",
            passed=False,
            duration_ms=elapsed,
            details={"timestamp": timestamp},
            error=str(e),
        )
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def verify_color_sequence(
    video_path: str,
    expected_sequence: list[tuple[float, str]],
) -> TestResult:
    """Verify that a video shows the expected colors at given timestamps.

    Args:
        video_path: Local file path or URL to a video.
        expected_sequence: List of (timestamp_seconds, expected_color_name).
            Example: [(1.0, "red"), (5.0, "blue"), (8.0, "green")]
    """
    start = time.monotonic()
    tmp_dir = None
    try:
        # Download once if URL
        actual_path = video_path
        if video_path.startswith(("http://", "https://")):
            tmp_dir = tempfile.mkdtemp(prefix="gradio_tester_")
            actual_path = _download_video(video_path, tmp_dir)

        checks = []
        all_passed = True
        for timestamp, expected_color in expected_sequence:
            r, g, b = _get_avg_color_ffmpeg(actual_path, timestamp)
            actual_color = _identify_color(r, g, b)
            matched = actual_color == expected_color
            if not matched:
                all_passed = False
            checks.append({
                "timestamp": timestamp,
                "expected": expected_color,
                "actual": actual_color,
                "avg_rgb": [round(r, 1), round(g, 1), round(b, 1)],
                "passed": matched,
            })

        elapsed = (time.monotonic() - start) * 1000
        passed_count = sum(1 for c in checks if c["passed"])
        failed = [c for c in checks if not c["passed"]]

        return TestResult(
            name="video_color_sequence",
            passed=all_passed,
            duration_ms=elapsed,
            details={
                "checks": checks,
                "passed_count": passed_count,
                "total_count": len(checks),
            },
            error=(
                f"{len(failed)} color mismatch(es): "
                + ", ".join(f'{c["timestamp"]}s expected {c["expected"]} got {c["actual"]}' for c in failed)
                if failed else None
            ),
        )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return TestResult(
            name="video_color_sequence",
            passed=False,
            duration_ms=elapsed,
            error=str(e),
        )
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
