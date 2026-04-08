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

## Snap Media Browser

The repo also includes a single-cell-style media browser app for local folders or Colab-mounted Drive media:

```bash
conda run -n gradio-tester python snap_media_browser.py
```

Useful environment overrides:

```bash
SNAP_MEDIA_ROOT=/path/to/media
SNAP_THUMB_DIR=/path/to/thumb-cache
SNAP_SHARE=0
GRADIO_SERVER_PORT=8905
```

Current behavior:

- Images and videos render in the same grid
- Clicking a tile opens a lightbox with next/prev controls
- Video thumbnails are cached under `THUMB_DIR`
- Files can be deleted from the lightbox
- Delete is limited to files under `MEDIA_ROOT`
- Deleting a video also removes its cached thumbnail
- A browser refresh now reloads the media listing from disk, so deleted items do not come back as stale placeholders

Automated coverage for this app lives in `tests/test_snap_media_browser.py` and includes launch checks, browser click flow, delete API coverage, and stale-session regression coverage.

Manual and automated test protocol used during debugging:

```bash
# Launch against a local fixture folder
SNAP_MEDIA_ROOT=/absolute/path/to/media \
SNAP_THUMB_DIR=/absolute/path/to/thumb-cache \
SNAP_SHARE=0 \
GRADIO_SERVER_PORT=8905 \
conda run -n gradio-tester python snap_media_browser.py

# App-specific tests
PYTHONPATH=src conda run -n gradio-tester pytest -q tests/test_snap_media_browser.py

# Full suite
PYTHONPATH=src conda run -n gradio-tester pytest -q
```

During browser debugging, use a real Playwright click flow against the live app. Endpoint checks alone were not enough to catch the original lightbox click bug.

## Running Tests

```bash
PYTHONPATH=src pytest tests/ -v
```

## License

MIT
