# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

A Python framework for Claude Code to autonomously test and verify Gradio web applications — primarily those hosted on Google Colab via `*.gradio.live` share URLs. Provides health checks, API introspection, endpoint invocation, Playwright UI interaction, screenshots, video color verification, and output variance detection.

## Build & Run Commands

```bash
# Environment setup
conda env create -f environment.yml
conda activate gradio-tester
pip install -e ".[dev,screenshot]"
playwright install chromium

# Run all tests (101 tests, requires ffmpeg)
pytest tests/ -v

# Run a single test file
pytest tests/test_health.py -v

# Run a single test
pytest tests/test_health.py::test_health_reachable_success -v

# Run the demo Gradio app (serves RGB test video on localhost:7860)
python app.py

# CLI usage
gradio-tester https://abc123.gradio.live
gradio-tester https://abc123.gradio.live --json
```

## Architecture

**Core abstraction**: Every module returns `TestResult` dataclasses (`models.py`) with `.passed`, `.error`, `.details`, and `.to_json()`. Results aggregate into `AppReport`.

**Execution flow** (`runner.py`): Health check runs first; if the app is unreachable, all remaining checks are marked "skipped" (short-circuit pattern). Checks run in order: health → introspect → client → screenshot → interact.

**Modules**:
- `health.py` and `introspect.py` are **stdlib-only** (`urllib.request` + `json`) — no external HTTP libs allowed.
- `client.py` lazy-imports `gradio_client` — returns descriptive error `TestResult` if missing. Includes `check_output_variance()` for detecting endpoints that ignore input.
- `screenshot.py` lazy-imports `playwright` — captures screenshots and checks DOM for error elements.
- `interact.py` lazy-imports `playwright` — drives Gradio UIs: fill inputs, click buttons, seek videos, verify outputs.
- `video.py` shells out to `ffmpeg` via subprocess for frame extraction and raw pixel color analysis.

**CLI** (`cli.py`): Entry point registered as `gradio-tester` in pyproject.toml. Exit code 0 = all passed, 1 = any failed. `--json` flag for machine-parseable output.

## Directing Agents to Test Gradio Apps

The primary use case for this framework is to give AI agents the tools to autonomously QA-test Gradio apps. When directing an agent to test an app, provide:

1. **The app URL** (e.g., `http://localhost:7860` or a `*.gradio.live` share link)
2. **What the app claims to do** — describe the expected behavior in plain language
3. **Do NOT tell the agent what the bugs are** — let it discover them

The agent should use a layered testing strategy:
- **Layer 1 — Infrastructure**: `gradio-tester <url>` for health, introspect, client, screenshot checks
- **Layer 2 — API correctness**: `--call /endpoint '[args]'` to call endpoints directly with known inputs and verify outputs
- **Layer 3 — Output variance**: `--check-variance /endpoint '[[input1], [input2], ...]'` to verify the endpoint doesn't always return the same value
- **Layer 4 — UI interaction**: `--interact '<json>'` to drive the UI as a real user would (fill inputs, click buttons, verify outputs)
- **Layer 5 — Video/visual**: `seek_video` + `read_input` + `verify` to test that video playback state flows through to the UI correctly
- **Layer 6 — Cross-validation**: Compare API results against actual video frame analysis using `verify_color_sequence()`

Each layer catches different failure modes. An app can pass API checks but fail UI checks (e.g., input not wired to video position). Always test multiple layers.

### Interact Actions Reference

```bash
gradio-tester <url> --interact '[
  {"action": "fill", "label": "Input Name", "value": "5.0"},
  {"action": "click", "label": "Button Text"},
  {"action": "verify", "label": "Output Name", "expected": "result"},
  {"action": "seek_video", "timestamp": 5.0, "label": "Video Label", "sync_input": "Input Label"},
  {"action": "read_input", "label": "Input Name"},
  {"action": "wait", "ms": 1000},
  {"action": "screenshot", "path": "debug.png"}
]'
```

## Testing Conventions

- One test file per module (`test_health.py`, `test_client.py`, etc.)
- `tests/conftest.py` provides shared fixtures: `SAMPLE_CONFIG`, `SAMPLE_API_INFO`, `SAMPLE_QUEUE_STATUS`, and a `mock_urlopen` factory
- External calls are mocked with `@patch` on `urllib.request.urlopen` or `gradio_client.Client`
- Playwright mocks use `AsyncMock` with `create=True` on `@patch("...async_playwright", create=True)` since playwright may not be installed
- Video tests require `test_assets/rgb_test.mp4` and system `ffmpeg`
- Each test file often defines a local `_mock_response()` helper for HTTP response mocking

## Key Conventions

- All new verification modules must return `TestResult` instances
- Keep health and introspect modules stdlib-only (no `requests`, no `httpx`)
- Health and introspect try `/gradio_api/` prefixed paths first (Gradio ≥6.x), falling back to legacy paths
- Use `conda activate gradio-tester` for this project's environment
- Python ≥ 3.10 required
- See `GRADIO_NOTES.md` for Gradio-specific patterns, workarounds, and lessons learned
