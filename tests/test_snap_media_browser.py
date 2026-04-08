"""Tests for snap_media_browser.py."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from PIL import Image
from playwright.sync_api import expect, sync_playwright


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "snap_media_browser.py"


def _load_module(module_name: str = "snap_media_browser_under_test"):
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_test_image(path: Path, color: tuple[int, int, int]) -> None:
    img = Image.new("RGB", (24, 24), color)
    img.save(path)


def _find_free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_http(url: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:  # pragma: no cover - only used while polling
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def _choice_values(choices):
    return [choice[1] if isinstance(choice, tuple) else choice for choice in choices]


@contextmanager
def _running_app(media_root: Path, thumb_dir: Path):
    port = _find_free_port()
    env = os.environ.copy()
    env["SNAP_MEDIA_ROOT"] = str(media_root)
    env["SNAP_THUMB_DIR"] = str(thumb_dir)
    env["SNAP_SHARE"] = "0"
    env["GRADIO_SERVER_PORT"] = str(port)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")

    proc = subprocess.Popen(
        [sys.executable, str(MODULE_PATH)],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        base_url = f"http://127.0.0.1:{port}"
        _wait_for_http(base_url)
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def test_build_grid_value_and_refresh_keep_session_state_isolated(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    subdir = media_root / "album one"
    subdir.mkdir(parents=True)
    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()
    _write_test_image(media_root / "root image.jpg", (255, 0, 0))
    _write_test_image(subdir / "nested'image.jpg", (0, 255, 0))

    monkeypatch.setenv("SNAP_MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("SNAP_THUMB_DIR", str(thumb_dir))
    snap = _load_module("snap_media_browser_state_test")

    state_a = snap.new_state()
    state_b = snap.new_state()

    status_a, folder_a, grid_a, returned_a = snap.full_refresh(state_a)
    assert "(root)" in status_a
    assert _choice_values(folder_a.choices) == ["album one"]
    assert grid_a["media"][0]["n"] == "root image.jpg"
    assert "root image.jpg" in grid_a["html"]
    assert returned_a is state_a

    state_a.navigate("album one")
    status_nested, folder_nested, grid_nested, returned_nested = snap.full_refresh(state_a)
    status_root, folder_root, grid_root, returned_root = snap.full_refresh(state_b)

    assert "album one" in status_nested
    assert _choice_values(folder_nested.choices) == []
    assert grid_nested["media"][0]["n"] == "nested'image.jpg"
    assert returned_nested is state_a

    assert "(root)" in status_root
    assert _choice_values(folder_root.choices) == ["album one"]
    assert grid_root["media"][0]["n"] == "root image.jpg"
    assert returned_root is state_b


def test_delete_media_file_removes_video_thumb_and_blocks_outside_root(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    media_root.mkdir()
    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()
    video_path = media_root / "clip name.mp4"
    video_path.write_bytes(b"fake video")

    monkeypatch.setenv("SNAP_MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("SNAP_THUMB_DIR", str(thumb_dir))
    snap = _load_module("snap_media_browser_delete_test")

    cached = Path(snap.thumb_cache_path(str(video_path)))
    cached.write_bytes(b"thumb")

    message = snap.delete_media_file(str(video_path))
    assert message == "Deleted clip name.mp4"
    assert not video_path.exists()
    assert not cached.exists()

    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"x")
    try:
        snap.delete_media_file(str(outside))
    except ValueError:
        pass
    else:  # pragma: no cover - explicit failure branch
        raise AssertionError("delete_media_file should reject paths outside MEDIA_ROOT")


def test_init_session_reloads_from_disk_after_delete(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    media_root.mkdir()
    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()
    target = media_root / "reload me.jpg"
    _write_test_image(target, (255, 0, 0))

    monkeypatch.setenv("SNAP_MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("SNAP_THUMB_DIR", str(thumb_dir))
    snap = _load_module("snap_media_browser_init_test")

    status_before, _, grid_before, state_before = snap.init_session()
    assert "1 images" in status_before
    assert len(grid_before["media"]) == 1

    snap.delete_media_file(str(target))

    status_after, _, grid_after, state_after = snap.init_session()
    assert "0 images" in status_after
    assert grid_after["media"] == []
    assert state_before is not state_after


def test_snap_media_browser_launch_serves_fixture_media(tmp_path):
    media_root = tmp_path / "media"
    media_root.mkdir()
    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()
    _write_test_image(media_root / " leading space.jpg", (255, 0, 0))
    _write_test_image(media_root / "quote'image.jpg", (0, 255, 0))
    _write_test_image(media_root / "plain.jpg", (0, 0, 255))

    with _running_app(media_root, thumb_dir) as base_url:
        with urllib.request.urlopen(f"{base_url}/config", timeout=5) as resp:
            config = json.loads(resp.read().decode("utf-8"))
        assert config["title"] == "Snap Media Browser"

        with urllib.request.urlopen(f"{base_url}/gradio_api/info", timeout=5) as resp:
            info = json.loads(resp.read().decode("utf-8"))
        assert "/init_session" in info["named_endpoints"]

        with urllib.request.urlopen(base_url, timeout=5) as resp:
            html = resp.read().decode("utf-8")
        assert "Snap Media Browser" in html

        encoded_names = [
            " leading space.jpg".replace(" ", "%20"),
            "quote'image.jpg".replace("'", "%27"),
            "plain.jpg",
        ]
        for encoded_name in encoded_names:
            url = f"{base_url}/gradio_api/file={media_root.as_posix()}/{encoded_name}"
            with urllib.request.urlopen(url, timeout=5) as resp:
                assert resp.status == 200
                assert resp.headers["content-type"].startswith("image/")


def test_snap_media_browser_delete_api_removes_file(tmp_path):
    media_root = tmp_path / "media"
    media_root.mkdir()
    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()
    target = media_root / "delete me.jpg"
    _write_test_image(target, (255, 0, 0))

    with _running_app(media_root, thumb_dir) as base_url:
        req = urllib.request.Request(
            f"{base_url}/gradio_api/run/delete_file",
            data=json.dumps({"data": [str(target)]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        assert resp.status == 200
        assert payload["data"][0] == "Deleted delete me.jpg"
        assert not target.exists()


def test_snap_media_browser_lightbox_click_flow(tmp_path):
    media_root = tmp_path / "media"
    media_root.mkdir()
    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()
    _write_test_image(media_root / " leading space.jpg", (255, 0, 0))
    _write_test_image(media_root / "quote'image.jpg", (0, 255, 0))
    _write_test_image(media_root / "plain.jpg", (0, 0, 255))

    with _running_app(media_root, thumb_dir) as base_url:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(base_url, wait_until="domcontentloaded")
            expect(page.locator(".c").first).to_be_visible()

            cards = page.locator(".c")
            expect(cards).to_have_count(3)

            cards.nth(0).click()
            host = page.locator('[data-snap-ready]')
            expect(host).to_have_attribute('data-snap-last-click', '0')
            expect(host).to_have_attribute('data-snap-lb-open', '1')
            expect(page.locator(".lb")).to_be_visible()
            expect(page.locator(".lb .ti")).to_have_text(" leading space.jpg")
            expect(page.locator(".lb .ct")).to_have_text("1/3")
            expect(page.locator(".lb .bd img")).to_have_attribute("src", re.compile(r"^blob:"))

            page.locator('.lb [data-a="n"]').first.click()
            expect(page.locator(".lb .ti")).to_have_text("plain.jpg")
            expect(page.locator(".lb .ct")).to_have_text("2/3")

            page.locator('.lb [data-a="n"]').first.click()
            expect(page.locator(".lb .ti")).to_have_text("quote'image.jpg")
            expect(page.locator(".lb .ct")).to_have_text("3/3")

            page.locator('.lb [data-a="p"]').first.click()
            expect(page.locator(".lb .ti")).to_have_text("plain.jpg")
            expect(page.locator(".lb .ct")).to_have_text("2/3")

            page.locator('.lb [data-a="x"]').click()
            expect(page.locator(".lb")).to_have_count(0)

            browser.close()
