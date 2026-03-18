"""BUG VARIANT C: Pan X works correctly but Pan Y is hardcoded to 0
in the export function. The CSS preview shows pan Y correctly,
making this a subtle visual-vs-export mismatch."""

import os
import subprocess
import tempfile
import time

import gradio as gr

VIDEO_PATH = "test_assets/quadrant_test.mp4"

_probe = subprocess.run(
    ["ffprobe", "-v", "quiet", "-show_entries", "stream=width,height",
     "-of", "csv=p=0", VIDEO_PATH], capture_output=True, text=True)
VIDEO_W, VIDEO_H = (int(x) for x in _probe.stdout.strip().split(","))
_dur = subprocess.run(
    ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
     "-of", "csv=p=0", VIDEO_PATH], capture_output=True, text=True)
VIDEO_DURATION = float(_dur.stdout.strip())


def export_video(trim_start, trim_end, zoom, pan_x, pan_y):
    trim_start = max(0, float(trim_start))
    trim_end = min(VIDEO_DURATION, float(trim_end))
    zoom = max(1.0, min(4.0, float(zoom)))
    pan_x = max(-1.0, min(1.0, float(pan_x)))
    # BUG: pan_y is received but hardcoded to 0
    pan_y = 0.0

    if trim_end <= trim_start:
        return None, "Error: trim end must be after trim start"

    duration = trim_end - trim_start
    crop_w = int(VIDEO_W / zoom)
    crop_h = int(VIDEO_H / zoom)
    max_offset_x = (VIDEO_W - crop_w) // 2
    max_offset_y = (VIDEO_H - crop_h) // 2
    crop_x = (VIDEO_W - crop_w) // 2 + int(pan_x * max_offset_x)
    crop_y = (VIDEO_H - crop_h) // 2 + int(pan_y * max_offset_y)
    crop_x = max(0, min(crop_x, VIDEO_W - crop_w))
    crop_y = max(0, min(crop_y, VIDEO_H - crop_h))

    output_dir = tempfile.mkdtemp(prefix="gradio_export_")
    output_path = os.path.join(output_dir, f"export_{int(time.time())}.mp4")

    vf_parts = ["setpts=PTS-STARTPTS"]
    if zoom > 1.0:
        vf_parts.append(f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}")
        vf_parts.append(f"scale={VIDEO_W}:{VIDEO_H}:flags=lanczos")
    vf = ",".join(vf_parts)

    cmd = [
        "ffmpeg", "-y", "-ss", str(trim_start), "-t", str(duration),
        "-i", VIDEO_PATH, "-vf", vf,
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        return None, f"Export failed: {result.stderr[-300:]}"
    return output_path, f"Exported {duration:.1f}s video at {zoom:.1f}x zoom"


with gr.Blocks(title="Video Trim & Zoom", css="""
    html, body, .gradio-container, .main, .wrap, .contain {
        height: 100vh !important; max-height: 100vh !important;
        overflow: hidden !important; margin: 0 !important;
    }
    * { scrollbar-width: none !important; }
    *::-webkit-scrollbar { display: none !important; }
    .gradio-container > .main > .wrap > .contain {
        display: flex !important; flex-direction: column !important;
        height: 100vh !important; padding: 8px 16px !important;
        box-sizing: border-box !important; gap: 4px !important;
    }
    .gradio-container > .main > .wrap > .contain > * { flex-shrink: 0; }
    #video-block { flex: 1 1 auto !important; min-height: 0 !important; overflow: hidden !important; }
    #video-block > div { height: 100% !important; display: flex !important; justify-content: center !important; }
    #preview-container { position: relative; overflow: hidden; max-height: 100%; display: inline-block; }
    #test-video { display: block; max-height: 100%; transform-origin: center center; }
""") as demo:
    gr.Markdown("# Video Trim & Zoom")
    video_html = gr.HTML(
        f'<div id="preview-container"><video id="test-video" controls>'
        f'<source src="/gradio_api/file={VIDEO_PATH}" type="video/mp4"></video></div>',
        elem_id="video-block",
    )
    with gr.Row():
        trim_start_inp = gr.Number(label="Trim Start (s)", value=0, minimum=0,
                                   maximum=VIDEO_DURATION, step=0.1, elem_id="trim-start")
        btn_set_start = gr.Button("Set Start ◀", size="sm")
        trim_end_inp = gr.Number(label="Trim End (s)", value=VIDEO_DURATION, minimum=0,
                                 maximum=VIDEO_DURATION, step=0.1, elem_id="trim-end")
        btn_set_end = gr.Button("Set End ▶", size="sm")
    with gr.Row():
        zoom_slider = gr.Slider(label="Zoom", minimum=1.0, maximum=4.0, step=0.1, value=1.0)
        pan_x_slider = gr.Slider(label="Pan X", minimum=-1.0, maximum=1.0, step=0.05, value=0.0)
        pan_y_slider = gr.Slider(label="Pan Y", minimum=-1.0, maximum=1.0, step=0.05, value=0.0)
    with gr.Row():
        export_btn = gr.Button("Export", variant="primary")
        status_box = gr.Textbox(label="Status", interactive=False)
    output_file = gr.File(label="Exported Video")

    btn_set_start.click(fn=lambda ts: round(ts, 1), inputs=trim_start_inp, outputs=trim_start_inp,
        js="(ts) => { const v = document.getElementById('test-video'); return (v && v.currentTime > 0) ? v.currentTime : ts; }")
    btn_set_end.click(fn=lambda ts: round(ts, 1), inputs=trim_end_inp, outputs=trim_end_inp,
        js="(ts) => { const v = document.getElementById('test-video'); return (v && v.currentTime > 0) ? v.currentTime : ts; }")

    # CSS preview shows pan Y correctly (the bug is only in the export)
    _preview_js = """(zoom, px, py) => {
        const v = document.getElementById('test-video');
        if (v) v.style.transform = `scale(${zoom}) translate(${-px * 30}%, ${-py * 30}%)`;
        return [zoom, px, py];
    }"""
    for s in [zoom_slider, pan_x_slider, pan_y_slider]:
        s.change(fn=lambda z, px, py: (z, px, py),
                 inputs=[zoom_slider, pan_x_slider, pan_y_slider],
                 outputs=[zoom_slider, pan_x_slider, pan_y_slider], js=_preview_js)

    export_btn.click(fn=export_video,
                     inputs=[trim_start_inp, trim_end_inp, zoom_slider, pan_x_slider, pan_y_slider],
                     outputs=[output_file, status_box])

if __name__ == "__main__":
    demo.launch(allowed_paths=["test_assets"])
