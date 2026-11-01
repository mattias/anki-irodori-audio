# Irodori Audio for Anki

An Anki add-on that creates natural-sounding Japanese **sentence audio** with [Irodori-TTS](https://github.com/Aratako/Irodori-TTS), running on your own computer. It picks a female or male voice and an emotion for every sentence, writes the audio to your `SentenceAudio` field, and never touches recorded audio.

Tested with the Kiku note type (fields `Sentence` and `SentenceAudio`), Anki 26.9.3, Windows 11 and an NVIDIA RTX 4080.

## What it does

- Menu in the card browser: **Cards > Generate Sentence Audio (Irodori)**.
- Six voices (3 female, 3 male) and seven emotions: neutral, happy, sad, angry, scared, whisper, joking.
- Voice and emotion are chosen by simple rules from the sentence (speech style such as 俺, ぼく, だぜ, わよ; keywords; punctuation). No AI model besides the TTS is needed. When unsure it uses neutral and a pseudo-random voice.
- Safe by default: notes with recorded audio are skipped, your `Sentence` field is never changed, old audio files are kept, and a whole run can be undone with *Edit > Undo*. Nothing changes if the server is down.
- Runs in the background with progress and a cancel button.

## Quick start (Windows)

Four steps: install the tools, set up the server, install the add-on, generate audio. Allow about 15 minutes and 10 GB of disk space. Everything runs on your own computer.

### What you need

- Windows 10/11 with an **NVIDIA GPU** (about 6 GB of free VRAM, a recent driver). Without a GPU it works on the CPU, but slowly (see "No NVIDIA GPU" below).
- Anki 2.1.50 or newer (tested on 26.9.3) and a note type with a sentence field and an audio field (default names: `Sentence` and `SentenceAudio`, as in Kiku).

### 1. Install the tools

Open **PowerShell** and run these three commands (answer yes if asked), then **close PowerShell and open a new one** so the tools are found:

```powershell
winget install --id Git.Git -e
winget install --id astral-sh.uv -e
winget install --id Gyan.FFmpeg -e
```

Check: `git --version`, `uv --version` and `ffmpeg -version` should each print a version.

### 2. Set up the Irodori server

In the new PowerShell window:

```powershell
cd $HOME
git clone https://github.com/Aratako/Irodori-TTS-Server.git
git clone https://github.com/mattias/anki-irodori-audio.git
cd Irodori-TTS-Server
uv sync --extra cu128
Copy-Item ..\anki-irodori-audio\voices\*.wav voices\
```

`uv sync` downloads about 5 GB (PyTorch with CUDA) and takes a few minutes. The last line copies the six voice files (`female_calm`, `female_bright`, `female_cool`, `male_calm`, `male_young`, `male_deep`) into the server. The add-on needs exactly these names.

### 3. Start the server

Still in the `Irodori-TTS-Server` folder:

```powershell
uv run --no-sync python -m irodori_openai_tts --host 127.0.0.1 --port 8088
```

Leave this window open. The server only runs while it is open, so **start it again like this every time you have restarted the computer** and want to generate audio (open PowerShell, then `cd $HOME\Irodori-TTS-Server`, then the command above).

Check that it works: open <http://127.0.0.1:8088/health> in a browser. You should see `"status":"ok"`. The very first sentence you generate downloads the model (about 3 GB) and loads it, which takes one to several minutes. After that it is fast (about 1 s per sentence on an RTX 4080, 4-5 GB of VRAM).

`--host 127.0.0.1` keeps the server reachable only from your own computer. Do not change it to `0.0.0.0`.

### 4. Install the add-on

In Anki: *Tools > Add-ons > Get Add-ons...*, paste the code `2078760911`, click OK and restart Anki. ([AnkiWeb page](https://ankiweb.net/shared/info/2078760911).) You can also download `irodori_audio.ankiaddon` from the [releases page](https://github.com/mattias/anki-irodori-audio/releases) and open it with Anki.

### 5. Generate audio

1. Make sure the server is running (step 3).
2. In the card browser, select **3-5 notes** first and run **Cards > Generate Sentence Audio (Irodori)**. A dialog shows how many notes get audio and how many are skipped. Confirm.
3. The first run is slow because the model loads (see step 3). Listen to the result. If you like it, select more notes.
4. Notes with new audio get the tag `irodori`. *Edit > Undo* reverts a whole run.

Settings are in *Tools > Add-ons > Irodori Audio > Config*: field names, audio format, overwrite behavior, voices and emotion captions.

### Other systems

- **No NVIDIA GPU:** use `uv sync --extra cpu` instead of `--extra cu128`. It works but is much slower (many seconds per sentence), so try a few notes first.
- **AMD GPU on Linux:** `uv sync --extra rocm`.
- **Linux/macOS:** install git, uv and ffmpeg with your package manager (for example `brew install git uv ffmpeg`) and run the same commands. On a Mac without CUDA use `--extra cpu`. Untested by me.
- **Starting with a script:** `server/start-irodori.ps1 -ServerDir <your Irodori-TTS-Server folder>` (Windows) or `server/start-irodori.sh <folder>` (Linux/macOS) runs the same start command.

## Troubleshooting

| Problem | What to do |
|---|---|
| "The Irodori server is not responding" | The server is not running. Start it (step 3) and check <http://127.0.0.1:8088/health>. |
| `No module named irodori_openai_tts` | You are in the wrong folder. Run `cd $HOME\Irodori-TTS-Server` first. |
| `uv`, `git` or `ffmpeg` "is not recognized" | Close PowerShell and open a new window after installing. If it still fails, restart the computer. |
| The first note takes minutes or the dialog seems stuck | The model is downloading and loading the first time. Watch the server window. Next time it is fast. |
| Error about ffmpeg in the server window | ffmpeg is not found by the server. Reopen PowerShell, check `ffmpeg -version`, restart the server. Or set `AUDIO_FORMAT` to `wav` in the add-on config (bigger files). |
| "CUDA out of memory" or the server crashes | Close other GPU programs (games, other AI tools) or use `--extra cpu`. |
| Notes are skipped | Notes that already have recorded audio are never replaced. The dialog shows the reasons. Check that the field names in the config match your note type. |
| The voice reads a name or word wrongly | Pronunciation cannot be corrected. Leave that note alone or keep your own audio. |
| Port 8088 is already in use | Another server is running. Close it, or use another port in both the start command and the add-on config (`SERVER_URL`). |

## Tips and known limits

- **Pronunciation is not controllable.** Unlike VOICEVOX there is no kana to correct. Rare names and unusual readings can be wrong. Listen first.
- **Laughs and breaths are not guaranteed.** The model sometimes adds a stray cry or breath after a sentence. The add-on detects clips that are far too long and regenerates them with another seed.
- **Whisper** is the least reliable emotion, especially for the male voices.
- **Emoji** in the text gave breathing artefacts in some tests, so emotions are set with a caption instead. The only exception is whisper, which also wraps the text in 🤫 and …. This only changes what is sent to the model, never your note.
- **Reference voices should be short** (about 3 s). A 4 s reference made one voice keep talking after the sentence ended.
- Do not use real people's voices (audiobook narrators, actors) as references. The model's terms forbid cloning a person without consent. The bundled voices were made with the model's own Voice Design (a text description, no reference audio) and do not imitate anyone.

## Licenses and credits

- Add-on code: MIT.
- [Irodori-TTS](https://github.com/Aratako/Irodori-TTS), [Irodori-TTS-Server](https://github.com/Aratako/Irodori-TTS-Server) and the model [Aratako/Irodori-TTS-v4-Small](https://huggingface.co/Aratako/Irodori-TTS-v4-Small) are by Aratako (MIT; see the model card for usage restrictions). Generated audio carries an inaudible watermark.
