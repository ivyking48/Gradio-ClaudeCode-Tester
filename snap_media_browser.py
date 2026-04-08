"""
Snap Media Browser v11 — ONE Colab cell
Uses gr.HTML custom component (html_template + css_template + js_on_load)
for the media grid with full lightbox. No iframe srcdoc workaround needed.

Changes from v10:
- Replaces iframe srcdoc with gr.HTML custom component (html_template/css_template/js_on_load)
- js_on_load runs once; uses watch('value') + event delegation for dynamic content
- Fixes: gr.update() → gr.Dropdown(), bare except → except Exception, path traversal guard
- Guarded google.colab import so it can also run locally for development
"""

import os, sys, time, subprocess, hashlib, base64, io, json, html as html_mod

# --- Colab drive mount (guarded for local dev) ---
try:
    from google.colab import drive
    drive.mount("/content/drive", force_remount=False)
    MEDIA_ROOT = "/content/drive/MyDrive/SnapInsta_Downloads"
    THUMB_DIR = "/content/_snap_thumbs"
except ImportError:
    MEDIA_ROOT = os.path.expanduser("~/SnapInsta_Downloads")
    THUMB_DIR = os.path.join("/tmp", "_snap_thumbs")

MEDIA_ROOT = os.environ.get("SNAP_MEDIA_ROOT", MEDIA_ROOT)
THUMB_DIR = os.environ.get("SNAP_THUMB_DIR", THUMB_DIR)

PAGE_SIZE = 60
ENABLE_SHARE = os.environ.get("SNAP_SHARE", "1").lower() not in {"0", "false", "no"}

os.makedirs(MEDIA_ROOT, exist_ok=True)
os.makedirs(THUMB_DIR, exist_ok=True)
print(f"[DEBUG] MEDIA_ROOT={MEDIA_ROOT}  items={len(os.listdir(MEDIA_ROOT))}")

# On Colab, ensure latest packages; skip locally if already installed
try:
    import google.colab  # noqa: F401
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "--upgrade", "--force-reinstall", "gradio>=6.0", "Pillow>=11.0,<12"])
except ImportError:
    pass  # local dev — assume gradio & Pillow already installed
import gradio as gr
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ============================================================
# HELPERS
# ============================================================
IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}
VID_EXT = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v"}


def ftype(n):
    e = Path(n).suffix.lower()
    return "image" if e in IMG_EXT else "video" if e in VID_EXT else "other"


def get_duration(vp):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", vp],
            capture_output=True, text=True, timeout=10,
        )
        return float(r.stdout.strip())
    except Exception:
        return 0


def fmt_dur(s):
    s = int(s)
    if s < 3600:
        return f"{s // 60}:{s % 60:02d}"
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def pil_to_b64(img, size=220, quality=65):
    img = img.convert("RGB")
    img.thumbnail((size, size))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def thumb_cache_path(video_path):
    return os.path.join(
        THUMB_DIR, hashlib.md5(video_path.encode()).hexdigest()[:12] + ".jpg"
    )


def make_video_thumb_pil(video_path):
    cached = thumb_cache_path(video_path)
    if not os.path.exists(cached):
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", video_path, "-vframes", "1",
                 "-vf", "scale=240:-1", "-q:v", "6", cached],
                capture_output=True, timeout=15,
            )
        except Exception:
            pass
    if os.path.exists(cached):
        try:
            img = Image.open(cached).convert("RGBA")
        except Exception:
            img = Image.new("RGBA", (240, 180), (25, 25, 35, 255))
    else:
        img = Image.new("RGBA", (240, 180), (25, 25, 35, 255))
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    w, h = img.size
    cx, cy = w // 2, h // 2
    sz = min(w, h) // 6
    d.ellipse(
        [cx - sz - 5, cy - sz - 5, cx + sz + 5, cy + sz + 5], fill=(0, 0, 0, 130)
    )
    d.polygon(
        [(cx - sz // 2, cy - sz), (cx - sz // 2, cy + sz), (cx + sz, cy)],
        fill=(255, 255, 255, 210),
    )
    dur = get_duration(video_path)
    if dur > 0:
        dt = fmt_dur(dur)
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13
            )
        except Exception:
            font = ImageFont.load_default()
        bb = d.textbbox((0, 0), dt, font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        p = 4
        rx, ry = w - tw - p * 2 - 5, 5
        d.rounded_rectangle(
            [rx, ry, rx + tw + p * 2, ry + th + p * 2], radius=4, fill=(0, 0, 0, 180)
        )
        d.text((rx + p, ry + p), dt, fill=(255, 255, 255, 240), font=font)
    return Image.alpha_composite(img, ov).convert("RGB")


def delete_media_file(path):
    """Delete a media file under MEDIA_ROOT and its cached thumbnail if present."""
    real = os.path.realpath(path)
    root = os.path.realpath(MEDIA_ROOT)
    if not (real == root or real.startswith(root + os.sep)):
        raise ValueError("Refusing to delete path outside media root")
    if not os.path.exists(real):
        raise FileNotFoundError("File not found")
    if os.path.isdir(real):
        raise IsADirectoryError("Delete only supports files")

    if Path(real).suffix.lower() in VID_EXT:
        cached = thumb_cache_path(real)
        if os.path.exists(cached):
            os.remove(cached)

    os.remove(real)
    return f"Deleted {os.path.basename(real)}"


# ============================================================
# STATE
# ============================================================
class State:
    def __init__(self):
        self.current_path = MEDIA_ROOT
        self.page = 0
        self.all_entries = []
        self.refresh()

    def _is_under_root(self, path):
        real = os.path.realpath(path)
        root = os.path.realpath(MEDIA_ROOT)
        return real == root or real.startswith(root + os.sep)

    def refresh(self):
        self.page = 0
        try:
            items = os.listdir(self.current_path)
        except Exception:
            items = []
        entries = []
        for n in items:
            if n.startswith("."):
                continue
            f = os.path.join(self.current_path, n)
            isd = os.path.isdir(f)
            entries.append((n, f, isd, ftype(n) if not isd else "folder"))
        entries.sort(key=lambda x: (not x[2], x[0].lower()))
        self.all_entries = entries
        print(f"[DEBUG] {self.current_path}: {len(entries)} items")

    def navigate(self, name):
        p = os.path.realpath(os.path.join(self.current_path, name))
        if os.path.isdir(p) and self._is_under_root(p):
            self.current_path = p
            self.refresh()

    def go_up(self):
        parent = os.path.dirname(self.current_path)
        if self._is_under_root(parent):
            self.current_path = parent
            self.refresh()

    def go_home(self):
        self.current_path = MEDIA_ROOT
        self.refresh()

    @property
    def rel(self):
        r = os.path.relpath(self.current_path, MEDIA_ROOT)
        return r if r != "." else "(root)"

    @property
    def pages(self):
        return max(1, -(-len(self.all_entries) // PAGE_SIZE))

    @property
    def page_entries(self):
        return self.all_entries[self.page * PAGE_SIZE : (self.page + 1) * PAGE_SIZE]

    @property
    def folders(self):
        return [e for e in self.all_entries if e[2]]

    def counts(self):
        d = sum(1 for e in self.all_entries if e[2])
        i = sum(1 for e in self.all_entries if e[3] == "image")
        v = sum(1 for e in self.all_entries if e[3] == "video")
        return d, i, v


def new_state():
    return State()

# ============================================================
# gr.HTML CUSTOM COMPONENT — template, css, js
# ============================================================

# Template: value is {"html": "<grid markup>", "media": [...]}
# Python builds the HTML (proper escaping), JS reads props.value.media
GRID_TEMPLATE = """${value && value.html ? value.html : '<div class="empty">Loading\u2026</div>'}"""

GRID_CSS = """\
/* --- Grid --- */
.sg { display: grid; grid-template-columns: repeat(auto-fill, minmax(155px, 1fr)); gap: 7px; padding: 8px; }
.c { position: relative; border-radius: 8px; overflow: hidden; cursor: pointer;
     background: #1a1d27; border: 1px solid #2a2d3a; transition: .15s; }
.c:hover { border-color: #7c6cf0; transform: translateY(-2px); }
.c img { width: 100%; aspect-ratio: 1; object-fit: cover; display: block; }
.c .ph { width: 100%; aspect-ratio: 1; display: flex; align-items: center; justify-content: center;
         background: linear-gradient(135deg, #242837, #171a23); color: #7f859c; font-size: 11px; }
.c .nm { padding: 3px 6px; font-size: 10px; color: #aaa;
         white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* --- Lightbox overlay (position:fixed escapes any parent container) --- */
.lb { position: fixed; inset: 0; z-index: 99999; background: rgba(0,0,0,.95);
      display: flex; flex-direction: column; font-family: system-ui, sans-serif; }
.lb .tp { display: flex; align-items: center; padding: 8px 12px; gap: 8px; }
.lb .tp .ti { flex: 1; color: #fff; font-size: 13px;
              overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lb .tp .b { background: none; border: 1px solid rgba(255,255,255,.25); color: #fff;
             width: 34px; height: 34px; border-radius: 7px; cursor: pointer;
             font-size: 16px; display: flex; align-items: center; justify-content: center; }
.lb .tp .b:hover { background: rgba(255,255,255,.1); }
.lb .bd { flex: 1; display: flex; align-items: center; justify-content: center;
          overflow: hidden; position: relative; padding: 0 50px; }
.lb .bd img { max-width: 100%; max-height: 100%; object-fit: contain; }
.lb .bd video { max-width: 100%; max-height: 100%; background: #000; }
.nv { position: absolute; top: 50%; transform: translateY(-50%);
      background: rgba(255,255,255,.1); border: none; color: #fff;
      width: 42px; height: 42px; border-radius: 50%; cursor: pointer;
      font-size: 20px; display: flex; align-items: center; justify-content: center; }
.nv:hover { background: rgba(255,255,255,.22); }
.nv.p { left: 6px; }
.nv.n { right: 6px; }
.ct { text-align: center; padding: 6px; font-size: 11px; color: #777; }
.empty { text-align: center; padding: 40px; color: #555;
         font-family: system-ui, sans-serif; }
"""

# js_on_load runs ONCE on first render.
# - Uses watch('value', ...) to track data changes from navigation/pagination
# - Event delegation on `element` persists across template re-renders
# - Lightbox is appended inside `element` (scoped CSS applies, position:fixed goes fullscreen)
GRID_JS = """\
(function() {
    var idx = -1;
    var blobs = [];

    /* Debug marker — verify js_on_load executed */
    element.dataset.snapReady = '1';

    /* Always read media from props.value (live reference), never a stale closure.
       props.value may not be populated yet when js_on_load first runs. */
    function getMedia() {
        return props.value && props.value.media ? props.value.media : [];
    }
    element.dataset.snapMediaCount = getMedia().length;

    /* --- Helpers --- */
    function esc(s) {
        var d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    function eventTouchesElement(event) {
        var path = event.composedPath ? event.composedPath() : [];
        for (var i = 0; i < path.length; i++) {
            if (path[i] === element) return true;
        }
        return element.contains(event.target);
    }

    function handleAction(action) {
        var media = getMedia();
        if (action === 'x') closeLB();
        else if (action === 'p') { idx = (idx - 1 + media.length) % media.length; openLB(); }
        else if (action === 'n') { idx = (idx + 1) % media.length; openLB(); }
        else if (action === 'del' && media[idx]) {
            if (!window.confirm('Delete "' + media[idx].n + '"?')) return;
            fetch('/gradio_api/run/delete_file', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ data: [media[idx].u] })
            }).then(function(resp) {
                if (!resp.ok) throw new Error('Delete request failed: ' + resp.status);
                return resp.json();
            }).then(function() {
                window.location.reload();
            }).catch(function(err) {
                window.alert('Delete failed: ' + err.message);
            });
        }
        else if (action === 'd' && media[idx]) {
            var dl = document.createElement('a');
            dl.href = '/gradio_api/file=' + media[idx].u.split('/').map(encodeURIComponent).join('/');
            dl.download = media[idx].n;
            dl.click();
        }
    }

    function wireGridCards() {
        element.querySelectorAll('[data-i]').forEach(function(card) {
            if (card.dataset.snapBound === '1') return;
            card.dataset.snapBound = '1';
            card.addEventListener('click', function(event) {
                if (!eventTouchesElement(event)) return;
                element.dataset.snapLastClick = card.dataset.i;
                idx = parseInt(card.dataset.i, 10);
                openLB();
            });
        });
    }

    function wireLightboxControls(lb) {
        lb.querySelectorAll('[data-a]').forEach(function(btn) {
            if (btn.dataset.snapBound === '1') return;
            btn.dataset.snapBound = '1';
            btn.addEventListener('click', function(event) {
                if (!eventTouchesElement(event)) return;
                handleAction(btn.dataset.a);
            });
        });
    }

    function loadBlob(path) {
        var encodedPath = path.split('/').map(encodeURIComponent).join('/');
        var urls = [
            '/gradio_api/file=' + encodedPath,
            '/file=' + encodedPath,
            '/file/' + encodedPath
        ];
        function tryNext(i) {
            if (i >= urls.length) return Promise.resolve('/gradio_api/file=' + encodedPath);
            return fetch(urls[i], { credentials: 'include' }).then(function(r) {
                if (r.ok) return r.blob().then(function(b) {
                    var u = URL.createObjectURL(b);
                    blobs.push(u);
                    return u;
                });
                return tryNext(i + 1);
            }).catch(function() { return tryNext(i + 1); });
        }
        return tryNext(0);
    }

    /* --- Lightbox --- */
    function closeLB() {
        var lb = element.querySelector('.lb');
        if (lb) {
            lb.querySelectorAll('img,video').forEach(function(el) {
                if (el.src && el.src.startsWith('blob:')) URL.revokeObjectURL(el.src);
            });
            lb.remove();
        }
        idx = -1;
        element.dataset.snapLbOpen = '0';
    }

    function openLB() {
        var targetIdx = idx;
        closeLB();
        var media = getMedia();
        idx = targetIdx;
        if (idx < 0 || idx >= media.length) return;
        var m = media[idx];
        var lb = document.createElement('div');
        lb.className = 'lb';
        var hasNav = media.length > 1;
        var navP = hasNav ? '<div class="nv p" data-a="p">&#8249;</div>' : '';
        var navN = hasNav ? '<div class="nv n" data-a="n">&#8250;</div>' : '';
        lb.innerHTML =
            '<div class="tp"><div class="ti">' + esc(m.n) + '</div>' +
            '<div class="b" data-a="p">&#9664;</div>' +
            '<div class="b" data-a="n">&#9654;</div>' +
            '<div class="b" data-a="del">&#128465;</div>' +
            '<div class="b" data-a="d">&#11015;</div>' +
            '<div class="b" data-a="x">&#10005;</div></div>' +
            '<div class="bd">' + navP +
            '<div style="color:#888">Loading\\u2026</div>' + navN + '</div>' +
            '<div class="ct">' + (idx + 1) + '/' + media.length + '</div>';
        element.appendChild(lb);
        wireLightboxControls(lb);
        var bd = lb.querySelector('.bd');
        element.dataset.snapLbOpen = '1';
        loadBlob(m.u).then(function(src) {
            if (m.t === 'i') {
                bd.innerHTML = navP + '<img src="' + src + '">' + navN;
            } else {
                bd.innerHTML = navP +
                    '<video src="' + src + '" controls autoplay playsinline></video>' + navN;
            }
            wireLightboxControls(lb);
        });
    }

    /* --- Keyboard navigation --- */
    document.addEventListener('keydown', function(e) {
        if (idx < 0) return;
        var media = getMedia();
        if (e.key === 'Escape') { closeLB(); e.preventDefault(); }
        else if (e.key === 'ArrowLeft') {
            idx = (idx - 1 + media.length) % media.length; openLB(); e.preventDefault();
        } else if (e.key === 'ArrowRight') {
            idx = (idx + 1) % media.length; openLB(); e.preventDefault();
        }
    });

    /* --- React to value changes (navigation / pagination) ---
       watch() may not be available in all Gradio versions, so guard it.
       Without it, lightbox still works but media data won't update on navigation
       until the page reloads. */
    try {
        if (typeof watch === 'function') {
            watch('value', function() {
                closeLB();
                blobs.forEach(function(u) { URL.revokeObjectURL(u); });
                blobs = [];
                element.dataset.snapMediaCount = getMedia().length;
                wireGridCards();
            });
        }
    } catch(e) {
        console.warn('[SNAP] watch() not available:', e.message);
    }
    new MutationObserver(function() {
        wireGridCards();
    }).observe(element, { childList: true, subtree: true });
    setTimeout(wireGridCards, 0);
})();
"""

# ============================================================
# GRID VALUE BUILDER
# ============================================================
def build_grid_value(state):
    t0 = time.time()
    items = state.page_entries
    cards_html = ""
    media_list = []

    for name, full, is_dir, ft in items:
        if is_dir or ft == "other":
            continue
        idx = len(media_list)
        thumb = ""
        if ft == "image":
            try:
                thumb = pil_to_b64(Image.open(full))
            except Exception:
                pass
            media_list.append({"t": "i", "n": name, "u": full})
        elif ft == "video":
            try:
                thumb = pil_to_b64(make_video_thumb_pil(full))
            except Exception:
                pass
            media_list.append({"t": "v", "n": name, "u": full})
        lbl = html_mod.escape(name) if ft == "image" else "\U0001f3ac " + html_mod.escape(name)
        preview_html = (
            f'<img src="{thumb}">' if thumb else f'<div class="ph">{ft.upper()}</div>'
        )
        cards_html += (
            f'<div class="c" data-i="{idx}">'
            f"{preview_html}"
            f'<div class="nm">{lbl}</div>'
            f'</div>'
        )

    elapsed = time.time() - t0
    print(f"[DEBUG] Grid: {len(media_list)} media, {elapsed:.1f}s")

    if not media_list:
        html = '<div class="empty">No media files in this folder</div>'
    else:
        html = f'<div class="sg">{cards_html}</div>'

    return {"html": html, "media": media_list}


# ============================================================
# EVENTS
# ============================================================
def full_refresh(state):
    d, i, v = state.counts()
    status = (
        f"\U0001f4c2 **{state.rel}** \u2014 {len(state.all_entries)} items "
        f"({d} folders, {i} images, {v} videos) \u2014 "
        f"Page {state.page + 1}/{state.pages}"
    )
    folders = gr.Dropdown(choices=[f[0] for f in state.folders], value=None)
    grid_val = build_grid_value(state)
    return status, folders, grid_val, state


def on_nav(state, name):
    if name:
        state.navigate(name)
    return full_refresh(state)


def on_up(state):
    state.go_up()
    return full_refresh(state)


def on_home(state):
    state.go_home()
    return full_refresh(state)


def on_prev(state):
    if state.page > 0:
        state.page -= 1
    return full_refresh(state)


def on_next(state):
    if state.page < state.pages - 1:
        state.page += 1
    return full_refresh(state)


def api_delete_file(path):
    return delete_media_file(path)


def init_session(_state=None):
    return full_refresh(new_state())


# ============================================================
# UI
# ============================================================
def build_demo(initial_state=None):
    """Create the Gradio demo without launching it."""
    print("[DEBUG] Building UI...")
    initial_state = initial_state or new_state()
    initial_status = "\U0001f4c2 **Loading...**"

    with gr.Blocks(title="Snap Media Browser") as demo:
        gr.Markdown("# \u26a1 Snap Media Browser")
        browser_state = gr.State(None)
        delete_path = gr.Textbox(visible=False)
        delete_result = gr.Textbox(visible=False)

        with gr.Row():
            btn_home = gr.Button("\U0001f3e0 Home", size="sm", scale=0)
            btn_up = gr.Button("\u2b06\ufe0f Up", size="sm", scale=0)
            status = gr.Markdown(initial_status)

        folder_dd = gr.Dropdown(
            label="\U0001f4c1 Open folder",
            choices=[],
            value=None,
            interactive=True,
        )

        with gr.Row():
            btn_p = gr.Button("\u25c0 Prev Page", size="sm")
            btn_n = gr.Button("Next Page \u25b6", size="sm")

        grid = gr.HTML(
            value={"html": '<div class="empty">Loading\u2026</div>', "media": []},
            html_template=GRID_TEMPLATE,
            css_template=GRID_CSS,
            js_on_load=GRID_JS,
            apply_default_css=False,
            container=False,
            padding=False,
            show_label=False,
        )

        outs = [status, folder_dd, grid, browser_state]
        folder_dd.input(on_nav, inputs=[browser_state, folder_dd], outputs=outs)
        btn_up.click(on_up, inputs=[browser_state], outputs=outs)
        btn_home.click(on_home, inputs=[browser_state], outputs=outs)
        btn_p.click(on_prev, inputs=[browser_state], outputs=outs)
        btn_n.click(on_next, inputs=[browser_state], outputs=outs)
        delete_path.submit(
            api_delete_file,
            inputs=[delete_path],
            outputs=[delete_result],
            api_name="delete_file",
            queue=False,
        )
        demo.load(fn=init_session, inputs=[browser_state], outputs=outs)

    return demo


def launch_app():
    """Launch the browser app."""
    print("[DEBUG] Launching...")
    demo = build_demo()
    demo.launch(
        debug=True, share=ENABLE_SHARE, quiet=False, height=900,
        allowed_paths=[MEDIA_ROOT, THUMB_DIR],
        theme=gr.themes.Base(primary_hue="purple", neutral_hue="slate"),
        css="footer{display:none!important}",
    )


if __name__ == "__main__":
    launch_app()
