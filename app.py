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


# --- Gradio UI ---

with gr.Blocks(title="Video Trim & Zoom", css="""
    * { scrollbar-width: none !important; }
    *::-webkit-scrollbar { display: none !important; }
    .gradio-container p, .gradio-container label, .gradio-container input,
    .gradio-container textarea, .gradio-container button, .gradio-container span,
    .gradio-container .info { font-size: 1.1em !important; }
    .gradio-container h1 { font-size: revert !important; }
    #video-crop { overflow: hidden; }
    #test-video { display: block; max-width: 100%; transform-origin: center center; }
""") as demo:
    gr.Markdown("# Video Trim & Zoom")

    video_html = gr.HTML(
        f"""<div id="preview-container">
            <div id="video-crop" style="overflow:hidden; position:relative;">
                <video id="test-video" controls
                       style="transform-origin:center center; display:block; width:100%;">
                    <source src="/gradio_api/file={VIDEO_PATH}" type="video/mp4">
                </video>
            </div>
        </div>""",
        elem_id="video-block",
    )

    with gr.Row():
        trim_start = gr.Number(label="Trim Start (s)", value=0, minimum=0,
                               maximum=VIDEO_DURATION, step=0.1, elem_id="trim-start")
        btn_set_start = gr.Button("Set Start ◀", size="sm")
        trim_end = gr.Number(label="Trim End (s)", value=VIDEO_DURATION, minimum=0,
                             maximum=VIDEO_DURATION, step=0.1, elem_id="trim-end")
        btn_set_end = gr.Button("Set End ▶", size="sm")

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

    # --- Set Trim Start/End from video position (js= pattern) ---
    btn_set_start.click(
        fn=lambda ts: round(ts, 1),
        inputs=trim_start,
        outputs=trim_start,
        js="""(ts) => {
            const v = document.getElementById('test-video');
            return (v && typeof v.currentTime === 'number') ? v.currentTime : ts;
        }""",
    )
    btn_set_end.click(
        fn=lambda ts: round(ts, 1),
        inputs=trim_end,
        outputs=trim_end,
        js="""(ts) => {
            const v = document.getElementById('test-video');
            return (v && typeof v.currentTime === 'number') ? v.currentTime : ts;
        }""",
    )

    # --- Live CSS preview for zoom/pan ---
    _preview_js = """
    (zoom, px, py) => {
        const v = document.getElementById('test-video');
        const crop = document.getElementById('video-crop');
        if (v && crop) {
            // Scale the video but keep the container at original size (clips the overflow)
            v.style.transform = `scale(${zoom}) translate(${-px * (1 - 1/zoom) * 50}%, ${-py * (1 - 1/zoom) * 50}%)`;
            // Fix container height so controls stay below
            if (!crop.dataset.origHeight) {
                crop.dataset.origHeight = crop.offsetHeight;
            }
            crop.style.height = crop.dataset.origHeight + 'px';
        }
        return [zoom, px, py];
    }
    """

    for slider in [zoom_slider, pan_x_slider, pan_y_slider]:
        slider.change(
            fn=lambda z, px, py: (z, px, py),
            inputs=[zoom_slider, pan_x_slider, pan_y_slider],
            outputs=[zoom_slider, pan_x_slider, pan_y_slider],
            js=_preview_js,
        )

    # --- Export ---
    export_btn.click(
        fn=export_video,
        inputs=[trim_start, trim_end, zoom_slider, pan_x_slider, pan_y_slider],
        outputs=[output_file, status_box],
    )

    demo.load(js="""
    () => {
        function fitLayout() {
            const video = document.getElementById('test-video');
            const crop = document.getElementById('video-crop');
            if (!video || !crop) { setTimeout(fitLayout, 300); return; }

            function resize() {
                // Measure space taken by everything except the video
                const cropRect = crop.getBoundingClientRect();
                const usedBelow = window.innerHeight - cropRect.top;
                let controlsHeight = 0;
                // Walk siblings after the video block to measure controls
                let el = crop.closest('[id=video-block]');
                if (el) {
                    let sib = el.nextElementSibling;
                    while (sib) {
                        controlsHeight += sib.getBoundingClientRect().height + 4;
                        sib = sib.nextElementSibling;
                    }
                }
                const available = window.innerHeight - cropRect.top - controlsHeight - 16;
                crop.style.maxHeight = Math.max(80, available) + 'px';
                video.style.maxHeight = crop.style.maxHeight;
            }

            resize();
            window.addEventListener('resize', resize);
            new ResizeObserver(resize).observe(document.body);
        }
        fitLayout();

        // Enforce trim range on video playback
        setInterval(() => {
            const v = document.getElementById('test-video');
            const startEl = document.querySelector('#trim-start input');
            const endEl = document.querySelector('#trim-end input');
            if (v && startEl && endEl && !v.paused) {
                const start = parseFloat(startEl.value) || 0;
                const end = parseFloat(endEl.value) || v.duration;
                if (v.currentTime < start) v.currentTime = start;
                if (v.currentTime > end) { v.pause(); v.currentTime = end; }
            }
        }, 200);
    }
    """)

if __name__ == "__main__":
    demo.launch(allowed_paths=["test_assets"])
