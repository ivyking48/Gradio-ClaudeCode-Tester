# Gradio Notes & Lessons Learned

Patterns, workarounds, and things that do and don't work when building and testing Gradio apps. Built from real debugging sessions with Gradio 6.x.

## API Path Changes in Gradio 6.x

**What changed**: Gradio 6.x moved API endpoints under `/gradio_api/`:
- `/queue/status` → `/gradio_api/queue/status`
- `/info` → `/gradio_api/info`
- `/config` still works at the old path

**What works**: Try the new path first, fall back to the old one. This is what `health.py` and `introspect.py` do — they iterate candidates and skip on 404.

**What doesn't work**: Hardcoding either path. Apps on older Gradio versions only have the old paths, and 6.x only has the new ones.

## Video Playback Position Sync

### The Problem
`gr.Video` does not expose the video's playback position to Python in a way that other components can use. When a user scrubs a video to a specific timestamp, there is no built-in mechanism to update a `gr.Number` input with that position.

### What Doesn't Work

**`video.pause()` / `video.stop()` events with `playback_position`**:
```python
# This does NOT work reliably in Gradio 6.x
video.pause(fn=lambda v: v["playback_position"], inputs=video, outputs=timestamp_input)
```
The events fire but the `playback_position` value is unreliable or zero.

**JavaScript DOM manipulation to set Gradio input values**:
```javascript
// This does NOT work — Gradio's Svelte state overrides DOM changes
const inputEl = document.querySelector('#my-input input');
inputEl.value = 5.0;
inputEl.dispatchEvent(new Event('input', { bubbles: true }));
```
Gradio 6.x uses Svelte-based internal state management. Setting a DOM element's value and dispatching native events does NOT update Gradio's internal component state. The framework re-renders from its stale internal state, overwriting the JavaScript change.

### What Works

**Use `gr.HTML` for the video + the `js` parameter on button click**:
```python
video_html = gr.HTML('<video id="test-video" controls><source src="..." type="video/mp4"></video>')

check_btn.click(
    fn=my_function,
    inputs=timestamp_input,
    outputs=[output, timestamp_input],
    js="""(timestamp) => {
        const v = document.getElementById('test-video');
        if (v && v.currentTime > 0) return v.currentTime;
        return timestamp;
    }""",
)
```

The `js` parameter on an event handler runs JavaScript **before** the Python function. Its return value replaces the input. This is the correct way to inject browser-side state (like `video.currentTime`) into Gradio's reactive system, because Gradio itself manages the value flow.

Key points:
- Use `gr.HTML` instead of `gr.Video` to get a standard HTML5 `<video>` element with a known `id`
- The `js` function receives the current input values as arguments and returns the modified values
- Return both the output and the updated timestamp to keep the Number input in sync
- Use `allowed_paths=["test_assets"]` in `demo.launch()` so Gradio serves the video file

## Testing Video Apps with Playwright

### What Works

**`seek_video` action with `sync_input`**:
The interact module's `seek_video` action uses JavaScript to set `video.currentTime` directly. However, this alone doesn't update Gradio inputs (see above). The `sync_input` option additionally fills the Gradio input via Playwright's `locator.fill()` + `dispatch_event("input")`, which does work because Playwright simulates real user input that Gradio's event system recognizes.

```bash
gradio-tester http://localhost:7860 --interact '[
  {"action":"seek_video","timestamp":5.0,"label":"Video","sync_input":"Timestamp (seconds)"},
  {"action":"click","label":"Check Color"},
  {"action":"verify","label":"Output","expected":"blue"}
]'
```

**`read_input` for diagnosis**:
Use `read_input` between actions to check what value a component actually has. This is how the agent discovered the video sync bug — it seeked to 5s, then read the input and saw it was still "0".

### Bug Detection Patterns

**Stale input detection**: Seek video → read_input → if value is still "0", the video position isn't wired to the input.

**Output variance**: Call an endpoint with multiple different inputs. If the output never changes, the endpoint is likely ignoring its input (e.g., always receiving a default value from the UI).

**Cross-validation**: Compare API responses against actual video frame analysis. The API might use wrong thresholds that don't match the real video content.

## Gradio Layout & Sizing

### The Problem
Gradio's default layout lets content overflow the viewport. Users have to scroll to see all elements.

### What Works

**Lock the page to viewport height**:
```css
html, body, .gradio-container, .main, .wrap, .contain {
    height: 100vh !important;
    max-height: 100vh !important;
    overflow: hidden !important;
}
```

**Make one element flexible** (e.g., the video):
```css
#video-block {
    flex: 1 1 auto !important;
    min-height: 0 !important;
    overflow: hidden !important;
}
```

**Put controls on one row** to save vertical space:
```python
with gr.Row():
    input = gr.Number(...)
    button = gr.Button(...)
    output = gr.Textbox(...)
```

**Hide all scrollbars** (if overflow:hidden isn't enough):
```css
* { scrollbar-width: none !important; }
*::-webkit-scrollbar { display: none !important; }
```

### What Doesn't Work

- Setting `overflow: hidden` only on `.gradio-container` — Gradio has multiple nested wrappers (`.main`, `.wrap`, `.contain`) that all need it
- Using `max-height` on the video without `min-height: 0` on the flex container — the video won't shrink below its intrinsic size
- Relying on Gradio's `Markdown` component to not overflow — it adds its own scroll containers; hide them with `* { scrollbar-width: none }`

## Browser Caching

Gradio aggressively caches served files (videos, images, etc.) via `/gradio_api/file=` URLs. When you replace a file on disk (e.g., regenerate `test_assets/rgb_test.mp4`), the browser will keep showing the old version even after restarting the app.

**Fix**: Hard refresh with **Cmd+Shift+R** (Mac) or **Ctrl+Shift+R** (Windows/Linux). A normal refresh or closing/reopening the tab is not enough.

You can also clear Gradio's temp file cache:
```bash
rm -rf /private/var/folders/*/T/gradio/   # macOS
```

## CSS Transform Preview for Zoom/Pan

### The Pattern

Use CSS `transform: scale() translate()` on the `<video>` element for instant visual zoom/pan preview, without re-encoding. The actual export uses ffmpeg `crop` + `scale` filters.

```python
# Wrap video in an overflow:hidden container
gr.HTML('<div id="preview-container" style="overflow:hidden"><video id="test-video" ...></div>')

# Wire slider changes to CSS transforms via js=
_preview_js = """(zoom, px, py) => {
    const v = document.getElementById('test-video');
    if (v) v.style.transform = `scale(${zoom}) translate(${-px * 30}%, ${-py * 30}%)`;
    return [zoom, px, py];
}"""
for slider in [zoom_slider, pan_x_slider, pan_y_slider]:
    slider.change(fn=lambda z, px, py: (z, px, py),
                  inputs=[zoom_slider, pan_x_slider, pan_y_slider],
                  outputs=[zoom_slider, pan_x_slider, pan_y_slider], js=_preview_js)
```

**Key**: The container needs `overflow: hidden` so the zoomed video doesn't bleed outside its bounds. Set `transform-origin: center center` on the video.

### Pitfall: Preview vs Export Mismatch

The CSS preview and ffmpeg export use different math. CSS `translate()` uses percentages of the element's own dimensions, while ffmpeg `crop` uses absolute pixel offsets. A common bug is getting the preview to look right but the export to crop differently. Always cross-validate by extracting frames from the exported video.

## ffmpeg Crop-from-Zoom Math

To convert zoom level + normalized pan offsets to ffmpeg crop coordinates:

```python
crop_w = int(video_w / zoom)
crop_h = int(video_h / zoom)

# Pan maps [-1, 1] to the available offset range
max_offset_x = (video_w - crop_w) // 2
max_offset_y = (video_h - crop_h) // 2
crop_x = (video_w - crop_w) // 2 + int(pan_x * max_offset_x)
crop_y = (video_h - crop_h) // 2 + int(pan_y * max_offset_y)

# Clamp
crop_x = max(0, min(crop_x, video_w - crop_w))
crop_y = max(0, min(crop_y, video_h - crop_h))

# ffmpeg filter: crop then scale back to original dimensions
vf = f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale={video_w}:{video_h}:flags=lanczos"
```

At zoom=1.0, crop equals the full frame (no-op). At zoom=2.0, crop is half the frame. Pan=(-1,-1) moves the crop to the top-left corner; pan=(1,1) to the bottom-right. This is the same formula used in VideoCurtain.

## Verifying Exported Video

After an ffmpeg export, use `ffprobe` to verify the output:

```python
from gradio_tester.video import verify_video_duration, verify_video_dimensions

# Check duration matches trim range
result = verify_video_duration("export.mp4", expected_duration=6.0, tolerance=0.5)

# Check dimensions match (should be original size after scale)
result = verify_video_dimensions("export.mp4", expected_width=640, expected_height=360)
```

For zoom verification, extract a frame and check its color. If the source video has 4 colored quadrants and you zoom 2x into the top-left, the exported frame should be entirely the top-left color (e.g., red), not a mix of all 4.

## Testing Slider Components

**`read_slider` interact action**: Reads a Gradio slider's value via the `aria-valuenow` attribute.

```bash
gradio-tester <url> --interact '[
  {"action": "read_slider", "label": "Zoom"}
]'
```

**What works**: Gradio sliders expose their current value via `aria-valuenow` on the slider element. The `read_slider` action reads this attribute.

**What doesn't work**: Using `input_value()` on sliders — they use `<input type="range">` which may not respond to standard value reads in the same way as text inputs.

## Component Behavior Notes

**`gr.Number` defaults**:
- `step=1` by default — stepper buttons only allow integers. Use `step=0.1` for fractional values.
- `value=0` means the input always starts at 0 regardless of video position.

**`gr.Video` vs `gr.HTML` for video**:
- `gr.Video`: Provides upload, webcam, and playback UI. Does NOT expose `currentTime` to Python. Good for simple video display where you don't need to read playback state.
- `gr.HTML` with `<video>`: Full control via JavaScript. Use when you need to read/set `currentTime`. Requires `allowed_paths` in `demo.launch()` to serve the file.

**`gr.Button.click(js=...)` parameter**:
- The `js` function runs in the browser BEFORE the Python `fn`
- It receives current input values as arguments
- Its return value replaces the inputs sent to Python
- This is the bridge between browser state and Gradio's Python backend
