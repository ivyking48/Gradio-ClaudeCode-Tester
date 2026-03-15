# CLAUDE.md — Gradio-ClaudeCode-Tester

## What This Project Does

A Python framework for Claude Code to autonomously test, visualize, and verify Gradio web applications — primarily those hosted on Google Colab via `*.gradio.live` share URLs.

## Quick Start

```bash
# Environment setup
conda env create -f environment.yml
conda activate gradio-tester
pip install -e .
playwright install chromium

# Run tests
pytest tests/ -v

# Run the demo Gradio app
python app.py
```

## Project Structure

```
src/gradio_tester/
├── models.py       # TestResult + AppReport dataclasses (foundation for all modules)
├── health.py       # HTTP reachability, queue status, error detection (stdlib only)
├── introspect.py   # /config and /info endpoint parsing, component validation
├── client.py       # gradio_client wrapper — list/call endpoints, type-check outputs
├── screenshot.py   # Playwright headless screenshots + DOM error detection
├── video.py        # ffmpeg frame extraction + color verification
├── runner.py       # Orchestrator — sequences checks, short-circuits on failure
└── cli.py          # CLI entry point: gradio-tester <URL> [options]

app.py              # Demo Gradio app serving an RGB test video
test_assets/        # Test fixtures (rgb_test.mp4)
tests/              # pytest suite (28 tests)
```

## CLI Usage

```bash
# Run all checks against a Gradio app
gradio-tester https://abc123.gradio.live

# JSON-only output (machine-parseable for Claude Code)
gradio-tester https://abc123.gradio.live --json

# Selective checks
gradio-tester https://abc123.gradio.live --checks health,introspect

# Call a specific API endpoint
gradio-tester https://abc123.gradio.live --call /predict '["input_value"]'

# Validate expected UI components
gradio-tester https://abc123.gradio.live --expect-components '{"Location": "textbox"}'
```

## Library Usage

```python
from gradio_tester.runner import run_all_checks
from gradio_tester.video import verify_color_sequence

# Full app check
report = run_all_checks("https://abc123.gradio.live")
print(report.to_json())

# Video color verification
result = verify_color_sequence("test_assets/rgb_test.mp4", [
    (1.0, "red"), (5.0, "blue"), (8.0, "green")
])
print(result.passed)  # True
```

## Architecture Decisions

- **All modules return `TestResult` objects** — consistent interface, always JSON-serializable, always has `.passed` and `.error`.
- **Runner short-circuits on health failure** — if the app is unreachable, remaining checks are skipped with clear "skipped" results instead of confusing timeout errors.
- **Lazy imports for optional deps** — `gradio_client` and `playwright` are imported inside functions so the framework doesn't crash if they're missing; those modules return descriptive error results instead.
- **ffmpeg for video analysis** — no Python image library dependency; uses raw pixel output from ffmpeg to compute average frame colors.
- **stdlib for health/introspect** — `urllib.request` + `json` only, keeping these modules dependency-free.

## Testing

```bash
pytest tests/ -v
```

28 tests covering all modules. Video tests require `test_assets/rgb_test.mp4` and `ffmpeg`. Client and runner tests use mocked HTTP/gradio_client responses.

## Dependencies

- **Required**: `gradio_client>=1.0.0`
- **Optional**: `playwright>=1.40.0` (for screenshots), `gradio>=4.0.0` (for demo app)
- **System**: `ffmpeg` (for video frame extraction)
- **Dev**: `pytest`, `pytest-asyncio`, `responses`

## Conventions

- Use `conda activate gradio-tester` for this project's environment
- Test with `pytest tests/ -v` before committing
- All new test/verification modules should return `TestResult` instances
- Keep health and introspect modules stdlib-only (no external HTTP libs)
