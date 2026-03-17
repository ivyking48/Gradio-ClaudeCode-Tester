"""Gradio app that serves the RGB test video for verification testing."""

import gradio as gr

VIDEO_PATH = "test_assets/rgb_test.mp4"

with gr.Blocks(title="RGB Color Test Video", css="""
    html, body, .gradio-container, .main, .wrap, .contain {
        height: 100vh !important;
        max-height: 100vh !important;
        overflow: hidden !important;
        margin: 0 !important;
    }
    * { scrollbar-width: none !important; }
    *::-webkit-scrollbar { display: none !important; }
    .gradio-container > .main > .wrap > .contain {
        display: flex !important;
        flex-direction: column !important;
        height: 100vh !important;
        padding: 8px 16px !important;
        box-sizing: border-box !important;
        gap: 4px !important;
    }
    .gradio-container > .main > .wrap > .contain > * {
        flex-shrink: 0;
    }
    #video-block {
        flex: 1 1 auto !important;
        min-height: 0 !important;
        overflow: hidden !important;
    }
    #video-block > div {
        height: 100% !important;
    }
    #video-block video {
        max-height: 100% !important;
        max-width: 100% !important;
        display: block !important;
        margin: 0 auto !important;
    }
    .gradio-container p, .gradio-container label, .gradio-container input,
    .gradio-container textarea, .gradio-container button, .gradio-container span,
    .gradio-container .info { font-size: 1.3em !important; }
    .gradio-container h1 { font-size: revert !important; }
""") as demo:
    gr.Markdown("# RGB Color Test Video")
    gr.Markdown(
        "10-second video showing solid colors: "
        "**Red** (0–3.33s), **Blue** (3.33–6.69s), **Green** (6.69–10s)"
    )

    video_html = gr.HTML(
        """<video id="test-video" controls>
            <source src="/gradio_api/file=test_assets/rgb_test.mp4" type="video/mp4">
        </video>""",
        elem_id="video-block",
    )

    with gr.Row():
        timestamp_input = gr.Number(
            label="Timestamp (seconds)", value=0, minimum=0, maximum=10, step=0.1,
            elem_id="timestamp-input",
        )
        check_btn = gr.Button("Check Color at Timestamp")
        color_output = gr.Textbox(label="Dominant Color", interactive=False)

    def get_color_at_timestamp(timestamp: float) -> tuple[str, float]:
        """Return the dominant color and the rounded timestamp."""
        timestamp = round(timestamp, 1)
        if timestamp < 3.33:
            color = "red"
        elif timestamp < 6.69:
            color = "blue"
        else:
            color = "green"
        return color, timestamp

    check_btn.click(
        fn=get_color_at_timestamp,
        inputs=timestamp_input,
        outputs=[color_output, timestamp_input],
        js="""(timestamp) => {
            const v = document.getElementById('test-video');
            if (v && v.currentTime > 0) return v.currentTime;
            return timestamp;
        }""",
    )

if __name__ == "__main__":
    demo.launch(allowed_paths=["test_assets"])
