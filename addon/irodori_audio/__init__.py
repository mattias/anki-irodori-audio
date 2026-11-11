"""Irodori Audio: generate SentenceAudio for selected notes with a local Irodori-TTS server."""
import html
import json
import os
import re
import time
import unicodedata
import urllib.request

import atexit
import shutil

from aqt import mw, gui_hooks
from aqt.operations import CollectionOp, QueryOp
from aqt.qt import (
    QAction,
    QDesktopServices,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTimer,
    QUrl,
    QVBoxLayout,
    qconnect,
)
from aqt.utils import askUser, showInfo, showWarning, tooltip

from . import selector
from . import server_manager as sm

SOUND_RE = re.compile(r"\[sound:([^\]]+)\]")


def cfg():
    return mw.addonManager.getConfig(__name__)


def clean_html(raw):
    text = re.sub(r"<[^>]*>", "", raw or "")
    return html.unescape(text).replace("\xa0", " ").strip()


def classify(existing, c):
    """Return 'ok' if the note may get new audio, otherwise the reason it is skipped."""
    existing = (existing or "").strip()
    if not existing:
        return "ok"
    rest = SOUND_RE.sub("", existing).strip()
    names = SOUND_RE.findall(existing)
    if rest or not names:
        return "other"  # text or unknown content: never touched
    if all(n.startswith("irodori_") for n in names):
        return "ok" if c["OVERWRITE"] else "irodori"
    return "recorded"  # recorded audio is never replaced


def server_ok(c):
    try:
        with urllib.request.urlopen(c["SERVER_URL"] + "/health", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def mp3_seconds(data):
    """Duration of an MPEG-1 Layer III file from its Xing/Info frame count, else from the first frame header (0 if unknown)."""
    bitrates = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
    rates = [44100, 48000, 32000]
    i = data.find(b"\xff")
    while 0 <= i < len(data) - 4 and (data[i + 1] & 0xE0) != 0xE0:
        i = data.find(b"\xff", i + 1)
    if i < 0 or i >= len(data) - 4:
        return 0.0
    rate_idx = (data[i + 2] >> 2) & 3
    if rate_idx == 3:
        return 0.0
    rate = rates[rate_idx]
    for tag in (b"Xing", b"Info"):
        t = data.find(tag, i, i + 200)
        if t >= 0 and len(data) >= t + 12 and data[t + 7] & 1:
            frames = int.from_bytes(data[t + 8 : t + 12], "big")
            return frames * 1152 / rate
    idx = (data[i + 2] >> 4) & 15
    if idx == 0 or idx == 15:
        return 0.0
    return len(data) * 8 / (bitrates[idx] * 1000)


def synthesize_once(c, plan, seed):
    irodori = {"seed": seed}
    if plan["caption"]:
        irodori["caption"] = plan["caption"]
    body = json.dumps(
        {
            "model": c["MODEL"],
            "input": plan["text"],
            "voice": plan["voice"],
            "response_format": c["AUDIO_FORMAT"],
            "irodori": irodori,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        c["SERVER_URL"] + "/v1/audio/speech", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=c["TIMEOUT_SECONDS"]) as r:
        return r.read()


def synthesize(c, plan):
    """Synthesize, retrying with other seeds when the clip is far too long for its text.

    TTS models occasionally keep "speaking" after the sentence ends (a stray cry or breath).
    Such clips are much longer than normal, so the shortest of a few attempts is kept.
    """
    limit = c["MAX_SECONDS_PER_CHAR"] * len(plan["text"]) + c["MAX_SECONDS_BASE"]
    best = None
    for attempt in range(1 + c["RETRIES"]):
        data = synthesize_once(c, plan, c["SEED"] + attempt)
        seconds = mp3_seconds(data) if c["AUDIO_FORMAT"] == "mp3" else 0.0
        if best is None or (seconds and seconds < best[0]):
            best = (seconds or 1e9, data)
        if not seconds or seconds <= limit:
            return data
    return best[1]


def run_irodori(browser):
    c = cfg()
    nids = list(browser.selected_notes())
    if not nids:
        tooltip("No notes selected.")
        return
    if not server_ok(c):
        offer_server(browser, c)
        return

    todo = []
    skipped = {"recorded": 0, "other": 0, "irodori": 0, "empty": 0, "field": 0}
    for nid in nids:
        note = mw.col.get_note(nid)
        if c["SOURCE_FIELD"] not in note or c["TARGET_FIELD"] not in note:
            skipped["field"] += 1
            continue
        status = classify(note[c["TARGET_FIELD"]], c)
        if status != "ok":
            skipped[status] += 1
            continue
        text = clean_html(note[c["SOURCE_FIELD"]])
        if not text:
            skipped["empty"] += 1
            continue
        todo.append((nid, text))

    summary = (
        f"Skipped: recorded audio {skipped['recorded']}, other content {skipped['other']}, "
        f"already Irodori {skipped['irodori']}, "
        f"empty sentence {skipped['empty']}, missing field {skipped['field']}."
    )
    if not todo:
        showInfo("No notes to generate audio for.\n" + summary)
        return
    if not askUser(
        f"Generate audio for {len(todo)} notes with Irodori?\n\n{summary}\n"
        "Old audio files are not deleted. You can undo with Edit > Undo."
    ):
        return

    media_dir = mw.col.media.dir()
    ext = c["AUDIO_FORMAT"]
    global _busy
    _busy += 1  # keeps the idle timer from stopping the server during the run
    touch()

    def work(col):
        try:
            return generate()
        finally:
            touch()

    def generate():
        done, failed = [], []
        total = len(todo)
        for i, (nid, text) in enumerate(todo):
            if mw.progress.want_cancel():
                break
            touch()
            mw.taskman.run_on_main(
                lambda i=i: mw.progress.update(label=f"Irodori: {i + 1} of {total}", value=i, max=total)
            )
            try:
                plan = selector.make_plan(c, text, str(nid))
                data = synthesize(c, plan)
                # Anki normalizes media names (NFKC, lowercase), so do the same to keep the field and file in sync
                safe = re.sub(r"[^\w]", "", unicodedata.normalize("NFKC", text)).lower()[:20]
                filename = f"irodori_{nid}_{safe}.{ext}"
                with open(os.path.join(media_dir, filename), "wb") as f:
                    f.write(data)
                done.append((nid, filename))
            except Exception as e:
                print(f"Irodori error for note {nid}: {e}")
                failed.append(nid)
        return done, failed

    def on_done(result):
        global _busy
        _busy -= 1
        done, failed = result
        if not done:
            showWarning(f"No audio was created. {len(failed)} notes failed (see the console).")
            return

        def write(col):
            notes = []
            for nid, filename in done:
                note = col.get_note(nid)
                note[c["TARGET_FIELD"]] = f"[sound:{filename}]"
                if c["TAG"]:
                    note.add_tag(c["TAG"])
                notes.append(note)
            return col.update_notes(notes)

        def finished(_changes):
            showInfo(f"Done! Created audio for {len(done)} notes, {len(failed)} failed.")

        CollectionOp(browser, write).success(finished).run_in_background()

    def on_failure(err):
        global _busy
        _busy -= 1
        showWarning(f"Irodori audio failed: {err}")

    QueryOp(parent=browser, op=work, success=on_done).failure(on_failure).with_progress(
        "Generating audio with Irodori..."
    ).run_in_background()


def setup_menu(browser):
    action = QAction("Generate Sentence Audio (Irodori)", browser)
    action.triggered.connect(lambda: run_irodori(browser))
    browser.form.menu_Cards.addSeparator()
    browser.form.menu_Cards.addAction(action)


# ---- Local server: set up, start, stop ----

_server_proc = None  # the server process this add-on started (None if it did not start one)
_last_use = 0.0  # time.time() of the last audio generation (or server start)
_busy = 0  # generations running right now; the server is never stopped while one runs
_idle_timer = None
GITHUB_URL = "https://github.com/mattias/anki-irodori-audio"


def server_root(c):
    return c.get("SERVER_DIR") or sm.default_dir()


def can_manage(c):
    return sm.is_local(c["SERVER_URL"])


def voices_src():
    return os.path.join(os.path.dirname(__file__), "voices")


def free_space(path):
    while path and not os.path.exists(path):
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return shutil.disk_usage(path or os.path.expanduser("~")).free


def stop_server():
    global _server_proc
    sm.stop(_server_proc)
    _server_proc = None


def touch():
    global _last_use
    _last_use = time.time()


def set_server(proc):
    """Remember a server process this add-on started (None: another server already answered)."""
    global _server_proc
    if proc is not None:
        _server_proc = proc
    touch()


def idle_minutes(c):
    try:
        return max(0.0, float(c.get("IDLE_MINUTES", 10) or 0))
    except (TypeError, ValueError):
        return 10.0


def check_idle():
    """Stop the server this add-on started when no audio was made for IDLE_MINUTES, to free the GPU memory.

    A server started by someone else is never touched (_server_proc is None then).
    """
    global _server_proc
    if _server_proc is None or _busy:
        return
    if _server_proc.poll() is not None:  # it ended by itself
        _server_proc = None
        return
    minutes = idle_minutes(cfg())
    if not minutes or time.time() - _last_use < minutes * 60:
        return
    stop_server()
    print(f"Irodori server stopped after {minutes:g} idle minutes.")
    tooltip("Irodori server stopped to free GPU memory. It starts again when you generate audio.")


def start_idle_timer():
    global _idle_timer
    if _idle_timer is None:
        _idle_timer = QTimer(mw)
        qconnect(_idle_timer.timeout, check_idle)
        _idle_timer.start(30 * 1000)


def offer_server(browser, c):
    """Called when generation is requested but no server answers: offer to start or set it up."""
    if not can_manage(c):
        showWarning(
            f"The Irodori server is not responding at {c['SERVER_URL']}. No notes were changed.\n"
            "Start it first (see the add-on description for instructions)."
        )
        return
    if sm.is_installed(server_root(c)):
        # installed but not running (stopped when idle, or not started with Anki): start it without asking
        start_server_op(browser, c, then=lambda: run_irodori(browser))
        return
    if askUser(
        "Irodori Audio needs a voice server that runs on your own computer, and it is not set up yet.\n\n"
        "Set it up now? (One time, about 8 GB of downloads.)"
    ):
        open_setup(browser, c)
    else:
        showInfo(f"You can set it up later from Tools > Irodori Audio > Set up local server.\nInstructions: {GITHUB_URL}")


def start_server_op(parent, c, then=None):
    def op(_col):
        return sm.start(server_root(c), c["SERVER_URL"], print, mw.progress.want_cancel)

    def success(proc):
        set_server(proc)
        if then:
            then()
        else:
            tooltip("Irodori server is running.")

    def failure(err):
        if isinstance(err, sm.Cancelled):
            return
        showWarning(f"Could not start the Irodori server.\n\n{err}\n\nLog: {sm.Paths(server_root(c)).log}")

    QueryOp(parent=parent, op=op, success=success).failure(failure).with_progress(
        "Starting the Irodori server (loading the voice model)..."
    ).run_in_background()


def auto_start():
    c = cfg()
    if not (c["AUTO_START_SERVER"] and can_manage(c) and sm.is_installed(server_root(c))):
        return

    def task():
        if sm.health(c["SERVER_URL"]):
            return None
        return sm.start(server_root(c), c["SERVER_URL"], print, lambda: False)

    def done(future):
        try:
            proc = future.result()
        except Exception as e:
            print(f"Irodori server did not start: {e}")
            tooltip("Irodori server could not start. See Tools > Irodori Audio > Open server log.")
            return
        set_server(proc)
        if proc is not None:
            tooltip("Irodori server is ready.")

    tooltip("Starting the Irodori server in the background...")
    mw.taskman.run_in_background(task, done, uses_collection=False)


def welcome():
    c = cfg()
    if c.get("ONBOARDING_SHOWN") or not can_manage(c) or sm.is_installed(server_root(c)) or server_ok(c):
        return
    c["ONBOARDING_SHOWN"] = True
    mw.addonManager.writeConfig(__name__, c)
    if askUser(
        "Welcome to Irodori Audio!\n\n"
        "It creates natural-sounding Japanese sentence audio with a voice model that runs on your own computer. "
        "To use it, a local voice server must be installed first (one time, about 8 GB of downloads).\n\n"
        "Set it up now? You can also do it later from Tools > Irodori Audio."
    ):
        open_setup(mw, c)


class SetupDialog(QDialog):
    def __init__(self, parent, c):
        super().__init__(parent)
        self.c = c
        self.root = server_root(c)
        self.cancel = False
        self.setWindowTitle("Set up the Irodori server")
        self.resize(640, 480)
        layout = QVBoxLayout(self)
        self.extra = sm.detect_extra(c["BACKEND"])
        gpu = (
            "An NVIDIA GPU was found, so generation will be fast."
            if self.extra == "cu128"
            else f"The server will use the CPU, which works but is slow (many seconds per sentence): {sm.describe_backend(self.extra)}."
        )
        self.info = QLabel(
            "This installs a local voice server that only your computer can reach (127.0.0.1).\n\n"
            "What happens:\n"
            "  1. Gets uv, a Python package manager (github.com/astral-sh/uv)\n"
            "  2. Downloads the server code (github.com/Aratako/Irodori-TTS-Server)\n"
            "  3. Installs Python packages including PyTorch, about 5 GB\n"
            "  4. Installs ffmpeg and the six bundled voices\n"
            "  5. Starts the server and downloads the voice model (huggingface.co, about 3 GB)\n\n"
            f"Install folder: {self.root}\nYou need about 10 GB of free disk space and a few minutes.\n{gpu}\n\n"
            "You can cancel and run it again later; it continues where it stopped."
        )
        self.info.setWordWrap(True)
        layout.addWidget(self.info)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setVisible(False)
        layout.addWidget(self.log, 1)
        self.bar = QProgressBar()
        self.bar.setVisible(False)
        layout.addWidget(self.bar)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.go = QPushButton("Install and start")
        self.close_button = QPushButton("Cancel")
        buttons.addWidget(self.go)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)
        qconnect(self.go.clicked, self.begin)
        qconnect(self.close_button.clicked, self.reject)

    def reject(self):
        self.cancel = True
        super().reject()

    def begin(self):
        free = free_space(self.root)
        if free < 10 * (1 << 30) and not askUser(f"Only {free // (1 << 30)} GB of disk space is free. Continue anyway?"):
            return
        self.go.setEnabled(False)
        self.log.setVisible(True)
        self.bar.setVisible(True)
        self.bar.setRange(0, sm.INSTALL_STEPS)
        self.info.setText("Installing... Do not close Anki until this is finished.")
        c = self.c

        def log(line):
            mw.taskman.run_on_main(lambda: self.log.appendPlainText(line))

        def step(n, total, label):
            def ui():
                self.log.appendPlainText(f"\n== Step {n} of {total}: {label} ==")
                self.bar.setValue(n - 1)
                self.info.setText(f"Step {n} of {total}: {label}")

            mw.taskman.run_on_main(ui)

        def task():
            if not sm.is_installed(self.root) or sm.installed_extra(self.root) != self.extra:
                sm.install(self.root, voices_src(), log, lambda: self.cancel, step, extra=self.extra)
            mw.taskman.run_on_main(
                lambda: self.info.setText("Starting the server and loading the voice model (the first time it is downloaded)...")
            )
            log("Starting the server. The first start downloads the voice model (about 3 GB).")
            return sm.start(self.root, c["SERVER_URL"], log, lambda: self.cancel, timeout=1800)

        def done(future):
            self.close_button.setText("Close")
            try:
                proc = future.result()
            except sm.Cancelled:
                self.info.setText("Cancelled. You can run the setup again from Tools > Irodori Audio.")
                self.go.setEnabled(True)
                return
            except Exception as e:
                self.log.appendPlainText(f"\nERROR: {e}")
                self.info.setText(
                    "Something went wrong (see the log below). You can run the setup again; it continues where it stopped. "
                    f"If it keeps failing, please open an issue at {GITHUB_URL}/issues and paste the log."
                )
                self.go.setEnabled(True)
                return
            set_server(proc)
            self.bar.setValue(self.bar.maximum())
            self.info.setText(
                "Done! The server is running.\n\nNow select a few notes in the card browser and use "
                "Cards > Generate Sentence Audio (Irodori). Listen to the result before running it on many notes.\n"
                "From now on the server starts by itself when needed and stops after a while without use, "
                "so the GPU memory is free for other programs (see IDLE_MINUTES in the add-on config)."
            )

        mw.taskman.run_in_background(task, done, uses_collection=False)


_setup_dialog = None


def open_setup(parent, c):
    global _setup_dialog
    _setup_dialog = SetupDialog(parent, c)
    _setup_dialog.show()


def show_status():
    c = cfg()
    root = server_root(c)
    showInfo(
        f"Server address: {c['SERVER_URL']}\n"
        f"Installed by this add-on: {'yes' if sm.is_installed(root) else 'no'}\n"
        f"Running: {'yes' if sm.health(c['SERVER_URL']) else 'no'}"
        f"{' (started by this add-on)' if _server_proc is not None else ''}\n"
        f"{idle_text(c)}"
        f"Install folder: {root}"
    )


def idle_text(c):
    minutes = idle_minutes(c)
    if not minutes:
        return "Stops when idle: never\n"
    left = ""
    if _server_proc is not None and not _busy:
        rest = minutes * 60 - (time.time() - _last_use)
        left = f" (in about {max(0, round(rest / 60))} min)"
    return f"Stops when idle: after {minutes:g} minutes without audio{left}\n"


def open_path(path):
    if os.path.exists(path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    else:
        tooltip("Nothing there yet.")


def uninstall():
    root = server_root(cfg())
    paths = sm.Paths(root)
    if not os.path.exists(paths.marker):
        showInfo("The server was not installed by this add-on.")
        return
    if not askUser(
        f"Remove the Irodori server from {root}? This frees several GB. "
        "The voice model stays in the Hugging Face cache (.cache/huggingface in your home folder); delete it there if you want it gone."
    ):
        return
    stop_server()
    for path in (paths.server, paths.bin, paths.uv_dir):
        shutil.rmtree(path, ignore_errors=True)
    for path in (paths.marker, paths.log):
        if os.path.exists(path):
            os.remove(path)
    showInfo("The server was removed.")


def setup_main_menu():
    menu = QMenu("Irodori Audio", mw)
    mw.form.menuTools.addMenu(menu)
    for text, fn in (
        ("Set up local server...", lambda: open_setup(mw, cfg())),
        ("Start server", lambda: start_server_op(mw, cfg())),
        ("Stop server", lambda: (stop_server(), tooltip("Server stopped (if this add-on started it)."))),
        ("Server status", show_status),
        ("Open server log", lambda: open_path(sm.Paths(server_root(cfg())).log)),
        ("Open server folder", lambda: open_path(server_root(cfg()))),
        ("Remove local server...", uninstall),
    ):
        action = QAction(text, mw)
        qconnect(action.triggered, fn)
        menu.addAction(action)


def on_profile_open():
    start_idle_timer()
    auto_start()
    QTimer.singleShot(2000, welcome)


setup_main_menu()
gui_hooks.browser_will_show.append(setup_menu)
gui_hooks.profile_did_open.append(on_profile_open)
gui_hooks.profile_will_close.append(stop_server)
atexit.register(stop_server)
