"""Gradio app that serves the RGB test video for verification testing."""

import gradio as gr

VIDEO_PATH = "test_assets/rgb_test.mp4"

with gr.Blocks(title="RGB Color Test Video") as demo:
    gr.Markdown("# RGB Color Test Video")
    gr.Markdown(
        "10-second video showing solid colors: "
        "**Red** (0–3.3s), **Blue** (3.3–6.7s), **Green** (6.7–10s)"
    )
    video = gr.Video(value=VIDEO_PATH, label="Test Video")

    with gr.Row():
        timestamp_input = gr.Number(
            label="Timestamp (seconds)", value=0, minimum=0, maximum=10,
            info="Updates automatically when you pause the video",
        )
        check_btn = gr.Button("Check Color at Timestamp")

    color_output = gr.Textbox(label="Dominant Color", interactive=False)

    def get_color_at_timestamp(timestamp: float) -> str:
        """Return the expected color at a given timestamp."""
        if timestamp < 3.333:
            return "red"
        elif timestamp < 6.667:
            return "blue"
        else:
            return "green"

    # Sync video playback position to the timestamp input when paused
    video.pause(fn=lambda v: v["playback_position"], inputs=video, outputs=timestamp_input)
    video.stop(fn=lambda v: v["playback_position"], inputs=video, outputs=timestamp_input)

    check_btn.click(fn=get_color_at_timestamp, inputs=timestamp_input, outputs=color_output)

if __name__ == "__main__":
    demo.launch()
