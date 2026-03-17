"""Gradio app that serves a zigzag square animation for verification testing."""

import gradio as gr

VIDEO_PATH = "test_assets/rgb_test.mp4"

with gr.Blocks(title="Zigzag Square Tracker", css="""
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
    .gradio-container > .main > .wrap > .contain > * { flex-shrink: 0; }
    #video-block {
        flex: 1 1 auto !important;
        min-height: 0 !important;
        overflow: hidden !important;
    }
    #video-block > div { height: 100% !important; }
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
    gr.Markdown("# Zigzag Square Animation")
    gr.Markdown(
        "A cyan square moves right → down → left → down → right across "
        "a 640×360 dark canvas over 20 seconds."
    )

    video_html = gr.HTML(
        """<video id="test-video" controls>
            <source src="/gradio_api/file=test_assets/rgb_test.mp4" type="video/mp4">
        </video>""",
        elem_id="video-block",
    )

if __name__ == "__main__":
    demo.launch(allowed_paths=["test_assets"])
