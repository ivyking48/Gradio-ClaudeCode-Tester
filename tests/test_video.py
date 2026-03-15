"""Tests for video.py — frame extraction and color verification."""

import os

import pytest

from gradio_tester.video import extract_frame_color, verify_color_sequence

VIDEO_PATH = os.path.join(os.path.dirname(__file__), "..", "test_assets", "rgb_test.mp4")
pytestmark = pytest.mark.skipif(
    not os.path.exists(VIDEO_PATH), reason="Test video not found"
)


def test_extract_red_frame():
    result = extract_frame_color(VIDEO_PATH, 1.0)
    assert result.passed is True
    assert result.details["identified_color"] == "red"


def test_extract_blue_frame():
    result = extract_frame_color(VIDEO_PATH, 5.0)
    assert result.passed is True
    assert result.details["identified_color"] == "blue"


def test_extract_green_frame():
    result = extract_frame_color(VIDEO_PATH, 8.0)
    assert result.passed is True
    assert result.details["identified_color"] == "green"


def test_verify_full_sequence_passes():
    result = verify_color_sequence(
        VIDEO_PATH,
        [(1.0, "red"), (5.0, "blue"), (8.0, "green")],
    )
    assert result.passed is True
    assert result.details["passed_count"] == 3


def test_verify_wrong_color_fails():
    result = verify_color_sequence(
        VIDEO_PATH,
        [(1.0, "blue")],  # It's actually red at 1s
    )
    assert result.passed is False
    assert result.details["checks"][0]["actual"] == "red"


def test_extract_at_invalid_timestamp():
    result = extract_frame_color(VIDEO_PATH, 999.0)
    assert result.passed is False
