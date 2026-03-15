"""Gradio app testing framework for Claude Code."""

from gradio_tester.models import AppReport, TestResult
from gradio_tester.video import extract_frame_color, verify_color_sequence

__all__ = ["TestResult", "AppReport", "extract_frame_color", "verify_color_sequence"]
__version__ = "0.1.0"
