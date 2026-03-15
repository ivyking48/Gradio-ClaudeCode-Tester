# Gradio-ClaudeCode-Tester

A Python framework for [Claude Code](https://claude.ai/code) to autonomously test, visualize, and verify [Gradio](https://gradio.app) web applications — primarily those hosted on Google Colab.

## Why?

When building Gradio apps in Colab, there's no easy way for an AI coding assistant to verify the app is working correctly. This framework gives Claude Code the tools to:

- **Health check** — verify the app is reachable and responding
- **Introspect the API** — parse `/config` and `/info` endpoints to validate components and endpoints
- **Call endpoints** — use the Gradio Python Client to invoke functions and check outputs
- **Take screenshots** — capture the rendered UI with Playwright for visual verification
- **Analyze video** — extract frames and verify colors/content using ffmpeg

## Installation

```bash
# With conda (recommended)
conda env create -f environment.yml
conda activate gradio-tester
pip install -e .
playwright install chromium

# With pip
pip install -e ".[screenshot]"
playwright install chromium
```

**System requirement:** [ffmpeg](https://ffmpeg.org/) (for video frame analysis)

## Quick Start

### CLI

```bash
# Run all checks against a live Gradio app
gradio-tester https://abc123.gradio.live

# JSON output for machine parsing
gradio-tester https://abc123.gradio.live --json

# Check specific things
gradio-tester https://abc123.gradio.live --checks health,introspect
gradio-tester https://abc123.gradio.live --call /predict '["hello"]'
gradio-tester https://abc123.gradio.live --expect-components '{"Input": "textbox"}'
```

### Python

```python
from gradio_tester.runner import run_all_checks

report = run_all_checks("https://abc123.gradio.live")
print(report.summary())
# PASS: 6/6 checks passed for https://abc123.gradio.live
```

### Video Color Verification

```python
from gradio_tester.video import verify_color_sequence

result = verify_color_sequence("video.mp4", [
    (1.0, "red"),
    (5.0, "blue"),
    (8.0, "green"),
])
assert result.passed
```

## Testing Modules

| Module | Purpose | Dependencies |
|--------|---------|-------------|
| `health` | HTTP reachability, error pattern detection, queue status | stdlib only |
| `introspect` | `/config` + `/info` parsing, component validation | stdlib only |
| `client` | Endpoint listing, invocation, output type checking | `gradio_client` |
| `screenshot` | Headless browser screenshots, DOM error detection | `playwright` (optional) |
| `video` | Frame extraction, dominant color identification | `ffmpeg` (system) |

All modules return `TestResult` objects with `.passed`, `.error`, `.details`, and `.to_json()`.

## Demo App

A sample Gradio app is included for testing the framework:

```bash
python app.py
```

Serves a 10-second RGB test video (red → blue → green) with a color-check endpoint.

## Running Tests

```bash
pytest tests/ -v
```

## License

MIT
