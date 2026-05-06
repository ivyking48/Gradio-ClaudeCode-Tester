# Gradio Notes & Lessons Learned

Patterns, workarounds, and things that do and don't work when building and testing Gradio apps. Built from real debugging sessions with Gradio 6.x.

## Injecting Page-Level JavaScript in Gradio 6.9.0

### What Doesn't Work

**`demo.load(js=...)`**: The JS callback never fires in Gradio 6.9.0.

**`<script>` inside `gr.HTML()`**: Gradio renders `gr.HTML` content via `innerHTML`, and per the HTML spec, `<script>` tags inserted via innerHTML do **not** execute. The `<script>` tag will appear in the DOM but its code never runs. Controls rendered in the HTML will look interactive (buttons click, range inputs slide) but won't be wired to any logic.

### What Works

**`gr.Blocks(head="<script>...</script>")`**: The `head=` parameter injects content into the real `<head>` of the document, where `<script>` tags execute normally.

```python
_PLAYER_JS = """
<script>
(function() {
    // Wait for DOM since this runs from <head>
    function init() {
        const el = document.getElementById('my-element');
        if (!el) { setTimeout(init, 300); return; }
        // ... setup code ...
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => setTimeout(init, 500));
    } else {
        setTimeout(init, 500);
    }
})();
</script>
"""

with gr.Blocks(head=_PLAYER_JS) as demo:
    gr.HTML('<div id="my-element">...</div>')
```

Key points:
- Since `head=` scripts run before the body, use `setTimeout` or `DOMContentLoaded` to wait for elements
- Re-query elements by ID in loops/handlers (don't cache references) — Gradio may re-render `gr.HTML`, replacing DOM nodes
- Inline `js=` on component events (`slider.change(js=...)`, `button.click(js=...)`) still works fine

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

**Use `gr.HTML` for the video markup + `head=` for the player JS + `js=` on button click to bridge browser state into Python**:

```python
# Player JS in head= (see "Injecting Page-Level JavaScript" section above)
_PLAYER_JS = """<script>
(function() {
    function init() {
        const v = document.getElementById('test-video');
        if (!v) { setTimeout(init, 300); return; }
        v.load();  // required — innerHTML-inserted <video> won't auto-load
        // ... render loop, controls, etc.
    }
    document.addEventListener('DOMContentLoaded', () => setTimeout(init, 500));
})();
</script>"""

with gr.Blocks(head=_PLAYER_JS) as demo:
    # Video markup only — no <script> (it won't execute in gr.HTML)
    gr.HTML('<div><video id="test-video"><source src="/gradio_api/file=video.mp4"></video></div>')

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
- Use `gr.HTML` for video markup, but put all JavaScript in `gr.Blocks(head=...)` — see "Injecting Page-Level JavaScript" section
- Call `video.load()` explicitly — `<video>` sources injected via innerHTML don't auto-load
- Re-query elements by ID in render loops — Gradio may re-render `gr.HTML`, replacing DOM nodes with new ones
- The `js=` function on events receives current input values as arguments and returns modified values
- Use `allowed_paths=["test_assets"]` in `demo.launch()` so Gradio serves the video file

## Event Delegation for gr.HTML Components

Gradio may re-render `gr.HTML` content at any time, replacing DOM elements. Event listeners attached to specific elements (e.g., a wrapper div) become stale after re-render.

**What doesn't work**: Binding events to elements found by ID, then caching the reference:
```javascript
const wrapper = document.getElementById('player-wrapper');
wrapper.addEventListener('click', handler);  // dies after Gradio re-renders
```

**What works**: Delegate all events from `document`, matching by target ID:
```javascript
document.addEventListener('click', (e) => {
    if (e.target.id !== 'play-pause-btn') return;
    // ... handle click
});
```
This survives any number of re-renders since `document` is never replaced. Use the same pattern for `mousedown`, `touchstart`, `wheel`, etc.

## Custom Timeline with Trim Handles

Instead of using `gr.Number` inputs for trim start/end, the demo app uses draggable handles on a custom HTML timeline. The handles update hidden `gr.Number` components via the native setter pattern (see "Canvas-Based Zoom/Pan Preview").

**Race condition when dragging trim-out handle then pressing play**: Dragging the out handle seeks the video to `trimEnd`. The trim enforcement poll sees `currentTime >= trimEnd` and immediately pauses. Fix:
1. Add a `_playGuard = Date.now()` timestamp when play is pressed
2. Skip trim enforcement for 300ms after play (`Date.now() - _playGuard > 300`)
3. Skip trim enforcement while a handle is being dragged (`!_draggingHandle`)
4. After trim range ends, reset `currentTime` to `trimStart` so next play works

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

## Canvas-Based Zoom/Pan Preview

### The Pattern

Use a `<canvas>` element with `drawImage()` crop parameters for instant zoom/pan preview, without re-encoding. The render loop reads `data-*` attributes from the canvas element. The actual export uses ffmpeg `crop` + `scale` filters.

**Mouse/touch interactions** (all handled in `head=` JS, no Gradio sliders needed):
- **Scroll wheel on canvas** → zoom in/out (updates `canvas.dataset.zoom`)
- **Click-drag on canvas** (when zoomed) → pan (updates `canvas.dataset.panX/panY`)
- Hidden `gr.Slider` components stay in the DOM for export, synced from JS via the native value setter pattern

**Syncing JS state to hidden Gradio inputs**:
```javascript
function setGradioInput(elemId, value) {
    const input = document.querySelector('#' + elemId + ' input');
    if (!input) return;
    const nativeSet = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    nativeSet.call(input, value.toFixed(1));
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
}
```
The native setter bypasses Gradio's Svelte state management, and the dispatched `input`/`change` events trigger Gradio's internal handlers to update its state.

### Pitfall: Preview vs Export Mismatch

The canvas `drawImage` preview and ffmpeg export use different coordinate systems. `drawImage(video, sx, sy, sw, sh, 0, 0, cw, ch)` uses source pixel coordinates, while ffmpeg `crop` uses absolute pixel offsets with `scale` to resize. Always cross-validate by extracting frames from the exported video.

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

## Using `eval_js` for Canvas/DOM Verification

The `verify` action can only check labeled Gradio components. For anything else — canvas dimensions, CSS properties, video `readyState`, arbitrary DOM state — use the `eval_js` interact action.

**Diagnostic mode** (no `expected`) — evaluate once, always passes, result in details:
```bash
gradio-tester <url> --interact '[
  {"action": "eval_js", "expression": "document.getElementById(\"preview-canvas\").width"}
]'
```

**Assertion mode** (with `expected`) — polls until match or timeout:
```bash
gradio-tester <url> --interact '[
  {"action": "eval_js", "expression": "document.getElementById(\"test-video\").readyState", "expected": 4}
]'
```

Use `timeout_ms` per-action to override the default poll duration.

**Use cases**:
- Check if a canvas has non-zero dimensions after rendering
- Verify a video element's `readyState` is `4` (HAVE_ENOUGH_DATA) before seeking
- Read computed CSS properties (`getComputedStyle(el).transform`)
- Count child elements, check visibility, read `data-*` attributes
- Any DOM state that isn't exposed through Gradio's labeled component system

## Custom HTML Components (gr.HTML with html_template/css_template/js_on_load)

Gradio now supports custom HTML components that eliminate the need for iframe srcdoc workarounds or `head=` script injection for many use cases.

### The API

```python
grid = gr.HTML(
    value={"html": "<div>...</div>", "media": [...]},
    html_template="""${value && value.html ? value.html : '<div>Empty</div>'}""",
    css_template=".card { border-radius: 8px; }",
    js_on_load="""
        // Runs ONCE on first render
        let data = props.value.media;

        // Watch for value changes from Python event handlers
        watch('value', () => {
            data = props.value.media;
        });

        // Event delegation survives template re-renders
        element.addEventListener('click', (e) => {
            const card = e.target.closest('.card');
            if (card) { /* handle click */ }
        });
    """,
    apply_default_css=False,
)
```

### Key Lifecycle Details

- **`html_template`**: Supports `${expr}` (JS expressions) and `{{var}}` (Handlebars). Default is `${value}`. Re-evaluates on every value change.
- **`css_template`**: Scoped to the component. Styles apply to all elements inside `element`, including dynamically appended ones.
- **`js_on_load`**: Runs **only once** on first render. Has access to `element`, `props`, `trigger()`, `watch()`, `upload()`, and `server`.
- **`watch('value', callback)`**: Fires when the value changes (from Python returning a new value). Use this instead of re-running `js_on_load`.
- **`props.value`**: Read/write the component's current value. Setting it triggers template re-render.
- **`trigger('event_name')`**: Fire custom events that Python listeners can handle.
- **`server.fn_name(args)`**: Call Python functions passed via `server_functions=[]` parameter.

### What This Replaces

| Old pattern | New pattern |
|---|---|
| `gr.Blocks(head="<script>...")` + `setTimeout(init)` polling | `js_on_load` with `element` reference |
| iframe srcdoc (for arbitrary JS) | `js_on_load` (runs unrestricted JS) |
| `document.addEventListener` with ID matching | Event delegation on `element` |
| Re-query elements after re-render | `watch('value', ...)` for reactive updates |
| `gr.HTML("<script>...")` (doesn't execute) | `js_on_load` (always executes) |

### Gotchas

- **`js_on_load` runs once**: Don't put re-render logic in it. Use `watch()`.
- **Template re-renders replace innerHTML**: Dynamically appended children (e.g., a lightbox overlay) get removed on value change. Use `watch` to clean up state.
- **`position: fixed` inside component**: Works for fullscreen overlays (lightbox). The scoped CSS still applies as long as the element is a child of `element`.
- **Structured values**: Python dicts serialize as JS objects via JSON. Access with `props.value.key`. HTML strings work with the default `${value}` template.
- **Custom props**: Pass arbitrary kwargs to `gr.HTML(size=40, max_stars=10)` — accessible in templates and `js_on_load` via `props.size`, `props.max_stars`.

## Component Behavior Notes

**`gr.Number` defaults**:
- `step=1` by default — stepper buttons only allow integers. Use `step=0.1` for fractional values.
- `value=0` means the input always starts at 0 regardless of video position.

**`gr.Video` vs `gr.HTML` for video**:
- `gr.Video`: Provides upload, webcam, and playback UI. Does NOT expose `currentTime` to Python. Good for simple video display where you don't need to read playback state.
- `gr.HTML` with `<video>`: Full control via JavaScript. Use when you need to read/set `currentTime`. Requires `allowed_paths` in `demo.launch()` to serve the file. **Important**: `<script>` tags inside `gr.HTML` do not execute (innerHTML limitation) — put all JS in `gr.Blocks(head=...)` instead. Also call `video.load()` from the head script since innerHTML-inserted `<video>` sources don't auto-load.

**`gr.Button.click(js=...)` parameter**:
- The `js` function runs in the browser BEFORE the Python `fn`
- It receives current input values as arguments
- Its return value replaces the inputs sent to Python
- This is the bridge between browser state and Gradio's Python backend
