# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

A Python framework for Claude Code to autonomously test and verify Gradio web applications — primarily those hosted on Google Colab via `*.gradio.live` share URLs. Provides health checks, API introspection, endpoint invocation, Playwright screenshots, and ffmpeg-based video color verification.

## Build & Run Commands

```bash
# Environment setup
conda env create -f environment.yml
conda activate gradio-tester
pip install -e .
playwright install chromium

# Run all tests (28 tests, requires ffmpeg)
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

**Execution flow** (`runner.py`): Health check runs first; if the app is unreachable, all remaining checks are marked "skipped" (short-circuit pattern). Checks run in order: health → introspect → client → screenshot.

**Dependency tiers**:
- `health.py` and `introspect.py` are **stdlib-only** (`urllib.request` + `json`) — no external HTTP libs allowed.
- `client.py` lazy-imports `gradio_client` — returns descriptive error `TestResult` if missing.
- `screenshot.py` lazy-imports `playwright` — same pattern, optional dependency.
- `video.py` shells out to `ffmpeg` via subprocess for frame extraction and raw pixel color analysis.

**CLI** (`cli.py`): Entry point registered as `gradio-tester` in pyproject.toml. Exit code 0 = all passed, 1 = any failed. `--json` flag for machine-parseable output.

## Testing Conventions

- One test file per module (`test_health.py`, `test_client.py`, etc.)
- `tests/conftest.py` provides shared fixtures: `SAMPLE_CONFIG`, `SAMPLE_API_INFO`, `SAMPLE_QUEUE_STATUS`, and a `mock_urlopen` factory
- External calls are mocked with `@patch` on `urllib.request.urlopen` or `gradio_client.Client`
- Video tests require `test_assets/rgb_test.mp4` and system `ffmpeg`
- Each test file often defines a local `_mock_response()` helper for HTTP response mocking

## Key Conventions

- All new verification modules must return `TestResult` instances
- Keep health and introspect modules stdlib-only (no `requests`, no `httpx`)
- Use `conda activate gradio-tester` for this project's environment
- Python ≥ 3.10 required
