"""Gradio app for trimming and zooming video with live CSS preview and ffmpeg export."""

import os
import subprocess
import tempfile
import time

import gradio as gr

VIDEO_PATH = "test_assets/quadrant_test.mp4"

# Get video dimensions via ffprobe
_probe = subprocess.run(
    ["ffprobe", "-v", "quiet", "-show_entries", "stream=width,height",
     "-of", "csv=p=0", VIDEO_PATH],
    capture_output=True, text=True,
)
_w, _h = (int(x) for x in _probe.stdout.strip().split(","))
VIDEO_W, VIDEO_H = _w, _h

# Get duration
_dur = subprocess.run(
    ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
     "-of", "csv=p=0", VIDEO_PATH],
    capture_output=True, text=True,
)
VIDEO_DURATION = float(_dur.stdout.strip())

# Single export directory — reused across exports, old files cleaned up
_EXPORT_DIR = tempfile.mkdtemp(prefix="gradio_export_")


def export_video(trim_start, trim_end, zoom, pan_x, pan_y):
    """Export a trimmed and zoomed video using ffmpeg."""
    trim_start = max(0, float(trim_start))
    trim_end = min(VIDEO_DURATION, float(trim_end))
    zoom = max(1.0, min(4.0, float(zoom)))
    pan_x = max(-1.0, min(1.0, float(pan_x)))
    pan_y = max(-1.0, min(1.0, float(pan_y)))

    if trim_end <= trim_start:
        return gr.update(value=None, visible=False), "Error: trim end must be after trim start"

    duration = trim_end - trim_start

    # Compute crop from zoom and pan (same math as VideoCurtain)
    crop_w = int(VIDEO_W / zoom)
    crop_h = int(VIDEO_H / zoom)
    # Pan maps [-1, 1] to the available offset range
    max_offset_x = (VIDEO_W - crop_w) // 2
    max_offset_y = (VIDEO_H - crop_h) // 2
    crop_x = (VIDEO_W - crop_w) // 2 + int(pan_x * max_offset_x)
    crop_y = (VIDEO_H - crop_h) // 2 + int(pan_y * max_offset_y)

    # Clamp to valid range
    crop_x = max(0, min(crop_x, VIDEO_W - crop_w))
    crop_y = max(0, min(crop_y, VIDEO_H - crop_h))

    # Clean old exports and write to the single export directory
    for old in os.listdir(_EXPORT_DIR):
        os.remove(os.path.join(_EXPORT_DIR, old))
    output_path = os.path.join(_EXPORT_DIR, f"export_{int(time.time())}.mp4")

    vf_parts = ["setpts=PTS-STARTPTS"]
    if zoom > 1.0:
        vf_parts.append(f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}")
        vf_parts.append(f"scale={VIDEO_W}:{VIDEO_H}:flags=lanczos")
    vf = ",".join(vf_parts)

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(trim_start), "-t", str(duration),
        "-i", VIDEO_PATH,
        "-vf", vf,
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-an",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        return gr.update(value=None, visible=False), f"Export failed: {result.stderr[-300:]}"

    return gr.update(value=output_path, visible=True), f"Exported {duration:.1f}s video ({crop_w}x{crop_h} crop at {zoom:.1f}x zoom)"


# --- Player JavaScript (injected via head= so it actually executes) ---

_PLAYER_JS = """
<script>
(function() {
    const $ = id => document.getElementById(id);

    function formatTime(sec) {
        if (!isFinite(sec) || sec < 0) return '0:00';
        const m = Math.floor(sec / 60);
        const s = Math.floor(sec % 60);
        return m + ':' + (s < 10 ? '0' : '') + s;
    }

    function fitLayout() {
        const wrapper = $('player-wrapper');
        const canvas = $('preview-canvas');
        if (!wrapper || !canvas) return;
        const wrapperTop = wrapper.getBoundingClientRect().top;
        let controlsHeight = 0;
        let el = wrapper.closest('[id=video-block]');
        if (el) {
            let sib = el.nextElementSibling;
            while (sib) {
                controlsHeight += sib.getBoundingClientRect().height + 4;
                sib = sib.nextElementSibling;
            }
        }
        const available = window.innerHeight - wrapperTop - controlsHeight - 16;
        wrapper.style.maxHeight = Math.max(80, available) + 'px';
        canvas.style.maxHeight = (Math.max(80, available) - 40) + 'px';
    }

    // Render loop — re-queries elements each frame to survive Gradio re-renders
    function renderFrame() {
        const video = $('test-video');
        const canvas = $('preview-canvas');
        if (video && canvas && video.videoWidth > 0) {
            const ctx = canvas.getContext('2d');
            if (canvas.width !== video.videoWidth) canvas.width = video.videoWidth;
            if (canvas.height !== video.videoHeight) canvas.height = video.videoHeight;

            const zoom = parseFloat(canvas.dataset.zoom) || 1.0;
            const px = parseFloat(canvas.dataset.panX) || 0;
            const py = parseFloat(canvas.dataset.panY) || 0;
            const cropW = video.videoWidth / zoom;
            const cropH = video.videoHeight / zoom;
            const maxOffX = (video.videoWidth - cropW) / 2;
            const maxOffY = (video.videoHeight - cropH) / 2;
            const sx = Math.max(0, (video.videoWidth - cropW) / 2 + px * maxOffX);
            const sy = Math.max(0, (video.videoHeight - cropH) / 2 + py * maxOffY);
            ctx.drawImage(video, sx, sy, cropW, cropH, 0, 0, canvas.width, canvas.height);
        }
        requestAnimationFrame(renderFrame);
    }
    // setInterval fallback for headless browsers and background tabs
    setInterval(renderFrame, 33);

    // --- Trim state ---
    let trimStart = 0;
    let trimEnd = 1;  // Will be set to video duration once loaded

    function setGradioInput(elemId, value) {
        const input = document.querySelector('#' + elemId + ' input');
        if (!input) return;
        const nativeSet = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
        nativeSet.call(input, value.toFixed(1));
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function updateTrimUI() {
        const video = $('test-video');
        const track = $('timeline-track');
        const range = $('trim-range');
        const handleIn = $('trim-handle-in');
        const handleOut = $('trim-handle-out');
        const labelIn = $('trim-label-in');
        const labelOut = $('trim-label-out');
        if (!video || !track || !range || !handleIn || !handleOut || !video.duration) return;

        const dur = video.duration;
        const pctIn = (trimStart / dur) * 100;
        const pctOut = (trimEnd / dur) * 100;

        handleIn.style.left = pctIn + '%';
        handleOut.style.left = pctOut + '%';
        range.style.left = pctIn + '%';
        range.style.width = (pctOut - pctIn) + '%';

        if (labelIn) labelIn.textContent = formatTime(trimStart);
        if (labelOut) labelOut.textContent = formatTime(trimEnd);

        // Sync to hidden Gradio inputs
        setGradioInput('trim-start', trimStart);
        setGradioInput('trim-end', trimEnd);
    }

    function updatePlayhead() {
        const video = $('test-video');
        const playhead = $('playhead');
        const timeDisp = $('time-display');
        if (!video || !playhead || !video.duration) return;

        const pct = (video.currentTime / video.duration) * 100;
        playhead.style.left = pct + '%';
        if (timeDisp) {
            timeDisp.textContent = formatTime(video.currentTime) + ' / ' + formatTime(video.duration);
        }
    }

    // --- Event binding ---
    let _bound = false;
    let _draggingHandle = null;  // 'in', 'out', 'seek', or null
    let _playGuard = 0;  // timestamp: ignore trim enforcement briefly after play

    function getTimeFromPointer(e, track) {
        const video = $('test-video');
        if (!video || !video.duration) return 0;
        const rect = track.getBoundingClientRect();
        const x = (e.touches ? e.touches[0].clientX : e.clientX) - rect.left;
        const pct = Math.max(0, Math.min(1, x / rect.width));
        return pct * video.duration;
    }

    // All events bound on document to survive Gradio re-renders of gr.HTML
    let _panEndTime = 0;  // suppress play/pause click right after a pan drag

    function bindEvents() {
        if (_bound) return;
        _bound = true;

        // Play/pause — delegate from document, match by ID
        document.addEventListener('click', (e) => {
            if (e.target.id !== 'play-pause-btn' && e.target.id !== 'preview-canvas') return;
            // Suppress play/pause on canvas if we just finished panning or zoom > 1 (canvas is for pan)
            if (e.target.id === 'preview-canvas' && (Date.now() - _panEndTime < 300)) return;
            const video = $('test-video');
            if (!video) return;
            if (video.paused) {
                // Always start from trim start (or current pos if within range)
                if (video.currentTime < trimStart || video.currentTime >= trimEnd - 0.05) {
                    video.currentTime = trimStart;
                }
                _playGuard = Date.now();  // prevent poll from immediately pausing
                video.play();
            } else {
                video.pause();
            }
        });

        // Trim handle & track dragging — delegate from document
        document.addEventListener('mousedown', (e) => {
            if (e.target.id === 'trim-handle-in') { e.preventDefault(); _draggingHandle = 'in'; }
            else if (e.target.id === 'trim-handle-out') { e.preventDefault(); _draggingHandle = 'out'; }
            else if (e.target.id === 'timeline-track' || e.target.id === 'trim-range' || e.target.id === 'playhead') {
                _draggingHandle = 'seek';
                const track = $('timeline-track');
                const video = $('test-video');
                if (track && video) {
                    video.currentTime = getTimeFromPointer(e, track);
                    updatePlayhead();
                }
            }
        });
        document.addEventListener('touchstart', (e) => {
            if (e.target.id === 'trim-handle-in') { e.preventDefault(); _draggingHandle = 'in'; }
            else if (e.target.id === 'trim-handle-out') { e.preventDefault(); _draggingHandle = 'out'; }
            else if (e.target.id === 'timeline-track' || e.target.id === 'trim-range' || e.target.id === 'playhead') {
                _draggingHandle = 'seek';
                const track = $('timeline-track');
                const video = $('test-video');
                if (track && video) {
                    video.currentTime = getTimeFromPointer(e, track);
                    updatePlayhead();
                }
            }
        }, { passive: false });

        document.addEventListener('mousemove', (e) => {
            if (!_draggingHandle) return;
            const track = $('timeline-track');
            const video = $('test-video');
            if (!track || !video) return;
            const t = getTimeFromPointer(e, track);

            if (_draggingHandle === 'in') {
                trimStart = Math.max(0, Math.min(t, trimEnd - 0.1));
                updateTrimUI();
                video.pause();
                video.currentTime = trimStart;
                updatePlayhead();
            } else if (_draggingHandle === 'out') {
                trimEnd = Math.max(trimStart + 0.1, Math.min(t, video.duration));
                updateTrimUI();
                video.pause();
                video.currentTime = trimEnd;
                updatePlayhead();
            } else if (_draggingHandle === 'seek') {
                video.currentTime = t;
                updatePlayhead();
            }
        });
        document.addEventListener('touchmove', (e) => {
            if (!_draggingHandle) return;
            const track = $('timeline-track');
            const video = $('test-video');
            if (!track || !video) return;
            const t = getTimeFromPointer(e, track);

            if (_draggingHandle === 'in') {
                trimStart = Math.max(0, Math.min(t, trimEnd - 0.1));
                updateTrimUI();
                video.pause();
                video.currentTime = trimStart;
                updatePlayhead();
            } else if (_draggingHandle === 'out') {
                trimEnd = Math.max(trimStart + 0.1, Math.min(t, video.duration));
                updateTrimUI();
                video.pause();
                video.currentTime = trimEnd;
                updatePlayhead();
            } else if (_draggingHandle === 'seek') {
                video.currentTime = t;
                updatePlayhead();
            }
        }, { passive: false });

        document.addEventListener('mouseup', () => {
            if (_draggingHandle === 'pan') _panEndTime = Date.now();
            _draggingHandle = null;
        });
        document.addEventListener('touchend', () => {
            if (_draggingHandle === 'pan') _panEndTime = Date.now();
            _draggingHandle = null;
        });

        // --- Zoom & Pan on canvas ---
        let _currentZoom = 1.0;
        let _currentPanX = 0;
        let _currentPanY = 0;

        function syncZoomPan() {
            const canvas = $('preview-canvas');
            if (canvas) {
                canvas.dataset.zoom = _currentZoom;
                canvas.dataset.panX = _currentPanX;
                canvas.dataset.panY = _currentPanY;
            }
            // Sync to Gradio sliders
            setGradioInput('zoom-slider', _currentZoom);
            setGradioInput('pan-x', _currentPanX);
            setGradioInput('pan-y', _currentPanY);
        }

        // Mouse wheel zoom on canvas
        document.addEventListener('wheel', (e) => {
            if (e.target.id !== 'preview-canvas') return;
            e.preventDefault();
            const step = e.deltaY < 0 ? 0.1 : -0.1;
            _currentZoom = Math.round(Math.max(1.0, Math.min(4.0, _currentZoom + step)) * 10) / 10;
            // Reset pan if zoom returns to 1
            if (_currentZoom <= 1.0) { _currentPanX = 0; _currentPanY = 0; }
            syncZoomPan();
        }, { passive: false });

        // Click-drag pan on canvas
        let _panStartX = 0, _panStartY = 0;
        let _panStartPanX = 0, _panStartPanY = 0;

        document.addEventListener('mousedown', (e) => {
            if (e.target.id === 'preview-canvas' && _currentZoom > 1.0) {
                _draggingHandle = 'pan';
                _panStartX = e.clientX;
                _panStartY = e.clientY;
                _panStartPanX = _currentPanX;
                _panStartPanY = _currentPanY;
                e.preventDefault();
            }
        });
        document.addEventListener('touchstart', (e) => {
            if (e.target.id === 'preview-canvas' && _currentZoom > 1.0 && e.touches.length === 1) {
                _draggingHandle = 'pan';
                _panStartX = e.touches[0].clientX;
                _panStartY = e.touches[0].clientY;
                _panStartPanX = _currentPanX;
                _panStartPanY = _currentPanY;
            }
        }, { passive: true });

        document.addEventListener('mousemove', (e) => {
            if (_draggingHandle !== 'pan') return;
            const canvas = $('preview-canvas');
            if (!canvas) return;
            const rect = canvas.getBoundingClientRect();
            const dx = (e.clientX - _panStartX) / rect.width;
            const dy = (e.clientY - _panStartY) / rect.height;
            // Invert: drag right = pan left (move viewport right)
            _currentPanX = Math.max(-1, Math.min(1, _panStartPanX - dx * 2));
            _currentPanY = Math.max(-1, Math.min(1, _panStartPanY - dy * 2));
            syncZoomPan();
        });
        document.addEventListener('touchmove', (e) => {
            if (_draggingHandle !== 'pan') return;
            const canvas = $('preview-canvas');
            if (!canvas || !e.touches.length) return;
            const rect = canvas.getBoundingClientRect();
            const dx = (e.touches[0].clientX - _panStartX) / rect.width;
            const dy = (e.touches[0].clientY - _panStartY) / rect.height;
            _currentPanX = Math.max(-1, Math.min(1, _panStartPanX - dx * 2));
            _currentPanY = Math.max(-1, Math.min(1, _panStartPanY - dy * 2));
            syncZoomPan();
        }, { passive: true });

    }

    // Poll video state
    let _lastVideoTime = -1;
    function pollVideoState() {
        const video = $('test-video');
        const playBtn = $('play-pause-btn');
        if (!video || !playBtn) return;

        // Force load if needed
        if (video.readyState === 0) {
            video.load();
        }

        // Initialize trimEnd to full duration once loaded
        if (video.duration && trimEnd <= 1 && video.duration > 1) {
            trimEnd = video.duration;
            updateTrimUI();
        }

        // Update playhead
        if (video.duration && video.currentTime !== _lastVideoTime) {
            _lastVideoTime = video.currentTime;
            updatePlayhead();
        }

        // Play/pause icon
        playBtn.textContent = video.paused ? '\\u25b6' : '\\u23f8';

        // Enforce trim range during playback
        // Skip if: dragging a handle, or within 300ms of pressing play
        if (!video.paused && !_draggingHandle && (Date.now() - _playGuard > 300)) {
            if (video.currentTime < trimStart) video.currentTime = trimStart;
            if (video.currentTime >= trimEnd) {
                video.pause();
                video.currentTime = trimStart;  // reset so next play works
            }
        }
    }

    function initPlayer() {
        const canvas = $('preview-canvas');
        const video = $('test-video');
        if (!canvas || !video) {
            setTimeout(initPlayer, 300); return;
        }
        video.load();
        bindEvents();
        fitLayout();
        window.addEventListener('resize', fitLayout);
        new ResizeObserver(fitLayout).observe(document.body);
        renderFrame();
        setInterval(pollVideoState, 50);
    }

    // Wait for DOM to be ready since this runs from <head>
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => setTimeout(initPlayer, 500));
    } else {
        setTimeout(initPlayer, 500);
    }
})();
</script>
"""


# --- Gradio UI ---

with gr.Blocks(title="Video Trim & Zoom", head=_PLAYER_JS, css="""
    * { scrollbar-width: none !important; }
    *::-webkit-scrollbar { display: none !important; }
    .gradio-container p, .gradio-container label, .gradio-container input,
    .gradio-container textarea, .gradio-container button, .gradio-container span,
    .gradio-container .info { font-size: 1.1em !important; }
    .gradio-container h1 { font-size: revert !important; }
    #player-wrapper { max-width: 100%; position: relative; }
    #preview-canvas { width: 100%; cursor: pointer; display: block; }
    #player-controls {
        display: flex; align-items: center; gap: 8px;
        padding: 6px 10px; background: #222; color: #fff;
        border-radius: 0 0 6px 6px;
    }
    #play-pause-btn {
        background: none; border: none; color: #fff; font-size: 1.3em;
        cursor: pointer; padding: 2px 6px; line-height: 1;
    }
    #time-display { font-family: monospace; font-size: 0.9em; white-space: nowrap; }
    /* Timeline */
    #timeline-track {
        flex: 1; position: relative; height: 24px; cursor: pointer;
        background: #444; border-radius: 4px; user-select: none;
        -webkit-user-select: none; touch-action: none;
    }
    #trim-range {
        position: absolute; top: 0; height: 100%;
        background: rgba(66, 133, 244, 0.35); border-radius: 4px;
        pointer-events: none;
    }
    #playhead {
        position: absolute; top: 0; width: 2px; height: 100%;
        background: #fff; pointer-events: none; z-index: 3;
        transform: translateX(-1px);
    }
    .trim-handle {
        position: absolute; top: -2px; width: 14px; height: 28px;
        border-radius: 3px; cursor: ew-resize; z-index: 4;
        transform: translateX(-7px);
        display: flex; align-items: center; justify-content: center;
        font-size: 10px; color: #fff; font-weight: bold;
        user-select: none; -webkit-user-select: none; touch-action: none;
    }
    #trim-handle-in { background: #4285f4; }
    #trim-handle-out { background: #ea4335; }
    .trim-handle::after {
        content: ''; display: block; width: 4px; height: 12px;
        border-left: 1.5px solid rgba(255,255,255,0.6);
        border-right: 1.5px solid rgba(255,255,255,0.6);
    }
    /* Trim time labels */
    #trim-labels {
        display: flex; justify-content: space-between;
        padding: 2px 10px; background: #222; color: #aaa;
        font-family: monospace; font-size: 0.75em;
        border-radius: 0 0 6px 6px; margin-top: -1px;
    }
    #trim-label-in { color: #4285f4; }
    #trim-label-out { color: #ea4335; }
    /* Hide Gradio inputs — synced from JS, used by export */
    #trim-start, #trim-end, #zoom-slider, #pan-x, #pan-y { display: none !important; }
""") as demo:
    gr.Markdown("# Video Trim & Zoom")

    video_html = gr.HTML(
        f"""<div id="player-wrapper">
            <video id="test-video" style="position:absolute; left:-9999px;" preload="auto">
                <source src="/gradio_api/file={VIDEO_PATH}" type="video/mp4">
            </video>
            <canvas id="preview-canvas"></canvas>
            <div id="player-controls">
                <button id="play-pause-btn" title="Play/Pause">&#9654;</button>
                <div id="timeline-track">
                    <div id="trim-range"></div>
                    <div id="playhead"></div>
                    <div id="trim-handle-in" class="trim-handle" title="Trim start"></div>
                    <div id="trim-handle-out" class="trim-handle" title="Trim end" style="left:100%"></div>
                </div>
                <span id="time-display">0:00 / 0:00</span>
            </div>
            <div id="trim-labels">
                <span>In: <span id="trim-label-in">0:00</span></span>
                <span>Out: <span id="trim-label-out">0:00</span></span>
            </div>
        </div>""",
        elem_id="video-block",
    )

    # Hidden trim inputs — synced from JS, used by export
    with gr.Row():
        trim_start = gr.Number(label="Trim Start (s)", value=0, minimum=0,
                               maximum=VIDEO_DURATION, step=0.1, elem_id="trim-start")
        trim_end = gr.Number(label="Trim End (s)", value=VIDEO_DURATION, minimum=0,
                             maximum=VIDEO_DURATION, step=0.1, elem_id="trim-end")

    with gr.Row():
        zoom_slider = gr.Slider(label="Zoom", minimum=1.0, maximum=4.0,
                                step=0.1, value=1.0, elem_id="zoom-slider")
        pan_x_slider = gr.Slider(label="Pan X", minimum=-1.0, maximum=1.0,
                                 step=0.05, value=0.0, elem_id="pan-x")
        pan_y_slider = gr.Slider(label="Pan Y", minimum=-1.0, maximum=1.0,
                                 step=0.05, value=0.0, elem_id="pan-y")

    with gr.Row():
        export_btn = gr.Button("Export", variant="primary")
        status_box = gr.Textbox(label="Status", interactive=False)
        output_file = gr.File(label="Exported Video", visible=False)

    # --- Export ---
    export_btn.click(
        fn=export_video,
        inputs=[trim_start, trim_end, zoom_slider, pan_x_slider, pan_y_slider],
        outputs=[output_file, status_box],
    )


if __name__ == "__main__":
    demo.launch(allowed_paths=["test_assets"], server_name="0.0.0.0")
