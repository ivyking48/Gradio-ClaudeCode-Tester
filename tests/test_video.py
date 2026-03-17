"""Tests for video.py — frame extraction and color verification."""

import os

import pytest

from unittest.mock import patch

from gradio_tester.video import extract_frame_color, verify_color_sequence, _identify_color

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


# --- Edge case tests (no dependency on test_assets/rgb_test.mp4) ---


class TestEdgeCasesNoVideo:
    """Edge case tests that do not require the test video file."""

    pytestmark = []  # Override module-level skipif

    def test_identify_color_unknown(self):
        result = _identify_color(128, 128, 128)
        assert "unknown" in result

    @patch("gradio_tester.video.subprocess.run")
    def test_extract_frame_color_ffmpeg_missing(self, mock_run):
        mock_run.side_effect = FileNotFoundError("ffmpeg not found")
        result = extract_frame_color("/fake/video.mp4", 1.0)
        assert result.passed is False
        assert result.error is not None

    @patch("gradio_tester.video._get_avg_color_ffmpeg")
    def test_verify_color_sequence_empty(self, mock_ffmpeg):
        result = verify_color_sequence("/fake/video.mp4", [])
        assert result.passed is True
        assert result.details["total_count"] == 0
        mock_ffmpeg.assert_not_called()
