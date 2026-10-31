"""Irodori Audio: generate SentenceAudio for selected notes with a local Irodori-TTS server."""
import html
import json
import os
import re
import unicodedata
import urllib.request

from aqt import mw, gui_hooks
from aqt.operations import CollectionOp, QueryOp
from aqt.qt import QAction
from aqt.utils import askUser, showInfo, showWarning, tooltip

from . import selector

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
        showWarning(
            f"The Irodori server is not responding at {c['SERVER_URL']}. No notes were changed.\n"
            "Start it first (see the add-on description for instructions)."
        )
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

    def work(col):
        done, failed = [], []
        total = len(todo)
        for i, (nid, text) in enumerate(todo):
            if mw.progress.want_cancel():
                break
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

    QueryOp(parent=browser, op=work, success=on_done).with_progress("Generating audio with Irodori...").run_in_background()


def setup_menu(browser):
    action = QAction("Generate Sentence Audio (Irodori)", browser)
    action.triggered.connect(lambda: run_irodori(browser))
    browser.form.menu_Cards.addSeparator()
    browser.form.menu_Cards.addAction(action)


gui_hooks.browser_will_show.append(setup_menu)
