"""Tests for video.py — frame extraction and color verification."""

import os

import pytest

from unittest.mock import patch

from gradio_tester.video import extract_frame_color, verify_color_sequence, _identify_color

VIDEO_PATH = os.path.join(os.path.dirname(__file__), "..", "test_assets", "quadrant_test.mp4")
pytestmark = pytest.mark.skipif(
    not os.path.exists(VIDEO_PATH), reason="Test video not found"
)


# quadrant_test.mp4: 20s, 640x360, 4 colored quadrants per segment
# Segment 1 (0-6.67s): TL=red, TR=blue, BL=green, BR=yellow
# Segment 2 (6.67-13.33s): TL=cyan, TR=magenta, BL=orange, BR=purple
# Segment 3 (13.33-20s): TL=white, TR=navy, BL=lime, BR=crimson
# Full-frame average colors vary by segment (mixed quadrants)


def test_extract_frame_color_segment1():
    """Segment 1 full-frame average is a mix of red+blue+green+yellow."""
    result = extract_frame_color(VIDEO_PATH, 3.0)
    assert result.passed is True
    assert result.details["identified_color"] is not None


def test_extract_frame_color_segment2():
    """Segment 2 has different quadrant colors than segment 1."""
    result = extract_frame_color(VIDEO_PATH, 10.0)
    assert result.passed is True


def test_extract_frame_color_segment3():
    result = extract_frame_color(VIDEO_PATH, 17.0)
    assert result.passed is True


def test_verify_segments_differ():
    """Different segments should produce different average colors."""
    r1 = extract_frame_color(VIDEO_PATH, 3.0)
    r2 = extract_frame_color(VIDEO_PATH, 10.0)
    assert r1.passed and r2.passed
    assert r1.details["avg_rgb"] != r2.details["avg_rgb"]


def test_verify_wrong_color_fails():
    result = verify_color_sequence(
        VIDEO_PATH,
        [(3.0, "cyan")],  # Segment 1 avg is not cyan
    )
    assert result.passed is False


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
