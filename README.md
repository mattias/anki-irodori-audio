# Irodori Audio for Anki

An Anki add-on that creates natural-sounding Japanese **sentence audio** with [Irodori-TTS](https://github.com/Aratako/Irodori-TTS), running on your own computer. It picks a female or male voice and an emotion for every sentence, writes the audio to your `SentenceAudio` field, and never touches recorded audio. It installs and starts its own local voice server, so there is nothing to set up by hand.

Good for mining from books and manga, where you otherwise get a flat, robotic voice.

Tested with the Kiku note type (fields `Sentence` and `SentenceAudio`), Anki 26.9.3, Windows 11 and an NVIDIA RTX 4080.

## What it does

- Menu in the card browser: **Cards > Generate Sentence Audio (Irodori)**.
- Six voices (3 female, 3 male) and seven emotions: neutral, happy, sad, angry, scared, whisper, joking.
- Voice and emotion are chosen by simple rules from the sentence (speech style such as 俺, ぼく, だぜ, わよ; keywords; punctuation). No AI model besides the TTS is needed. When unsure it uses neutral and a pseudo-random voice.
- Installs, starts and stops the voice server for you (Windows, Linux, macOS), with a guided setup the first time.
- Safe by default: notes with recorded audio are skipped, your `Sentence` field is never changed, old audio files are kept, and a whole run can be undone with *Edit > Undo*. Nothing changes if the server is down.
- Runs in the background with progress and a cancel button.

## Quick start

You need Anki 2.1.50 or newer, an internet connection for the one-time setup, about **10 GB of free disk space**, and ideally an **NVIDIA GPU** (about 6 GB of free VRAM). Without a GPU it still works on the CPU, but slowly (many seconds per sentence).

1. **Install the add-on.** In Anki: *Tools > Add-ons > Get Add-ons...*, paste the code `2078760911` and click OK ([AnkiWeb page](https://ankiweb.net/shared/info/2078760911)). Or download `irodori_audio.ankiaddon` from the [releases page](https://github.com/mattias/anki-irodori-audio/releases) and open it with Anki. Restart Anki.
2. **Set up the server.** After the restart a welcome dialog offers to set up the server. You can also open it from *Tools > Irodori Audio > Set up local server...*. It shows what will be downloaded, then click **Install and start**. This runs once, takes a few minutes to half an hour depending on your connection, and shows a log. You can cancel and run it again later; it continues where it stopped.
3. **Generate audio.** In the card browser, select **3-5 notes** first and run **Cards > Generate Sentence Audio (Irodori)**. A dialog shows how many notes get audio and how many are skipped. Confirm, then listen to the result. If you like it, select more notes.

Notes with new audio get the tag `irodori`. *Edit > Undo* reverts a whole run.

From then on the server starts automatically when Anki starts and stops when Anki closes. If it is not running when you generate audio, the add-on offers to start it. Starting takes up to a minute while the voice model loads.

### What the setup installs

Everything goes into one folder (Windows: `%LOCALAPPDATA%\IrodoriAudio`, Linux: `~/.local/share/irodori-audio`, macOS: `~/Library/Application Support/IrodoriAudio`). Nothing else on your computer is changed.

1. [uv](https://github.com/astral-sh/uv), a Python package manager (skipped if you already have it).
2. The [Irodori-TTS-Server](https://github.com/Aratako/Irodori-TTS-Server) code, a fixed tested version.
3. Python and the server's packages including PyTorch, about 5 GB. With an NVIDIA GPU it installs the CUDA version, otherwise the CPU version.
4. ffmpeg (needed for mp3), unless you already have it, and the six voice files from the add-on.
5. The voice model [Irodori-TTS-v4-Small](https://huggingface.co/Aratako/Irodori-TTS-v4-Small), about 3 GB, into the Hugging Face cache (`.cache/huggingface` in your home folder).

The server listens only on `127.0.0.1`, so other computers cannot reach it. All sentence text stays on your computer.

### The Irodori Audio menu

*Tools > Irodori Audio* has: Set up local server, Start server, Stop server, Server status, Open server log, Open server folder, and Remove local server (frees the disk space; the model stays in the Hugging Face cache).

Settings are in *Tools > Add-ons > Irodori Audio > Config*: field names, audio format, overwrite behavior, voices, emotion captions, the install folder (`SERVER_DIR`) and whether the server starts with Anki (`AUTO_START_SERVER`).

## Troubleshooting

| Problem | What to do |
|---|---|
| The setup fails | Read the last lines of the log in the setup window. Run the setup again; it continues where it stopped. If it keeps failing, open an [issue](https://github.com/mattias/anki-irodori-audio/issues) and paste the log. |
| A firewall or antivirus blocks the downloads | Allow Anki to download from github.com, pypi.org, download.pytorch.org and huggingface.co, or use the manual setup below. |
| "The Irodori server is not running" | Accept the offer to start it, or use *Tools > Irodori Audio > Start server*. If it fails, use *Open server log*. |
| The first start takes minutes | The voice model is downloaded and loaded the first time. Later starts take up to a minute. |
| "CUDA out of memory" or the server crashes | Close other GPU programs (games, other AI tools) and start the server again. |
| `no kernel image is available for execution on the device` | Your NVIDIA GPU is too old for the CUDA build of PyTorch (GTX 10 series and older). Update the add-on (it now detects this and uses the CPU), or set `BACKEND` to `cpu` in the config and run *Set up local server* again. |
| Generation is very slow | Check *Server status*. Without an NVIDIA GPU the CPU is used and each sentence takes many seconds. |
| Notes are skipped | Notes that already have recorded audio are never replaced. The dialog shows the reasons. Check that the field names in the config match your note type. |
| The voice reads a name or word wrongly | Pronunciation cannot be corrected. Leave that note alone or keep your own audio. |
| Port 8088 is already in use | Another program uses the port. Close it, or change the port in `SERVER_URL` in the add-on config. |
| You want the space back | *Tools > Irodori Audio > Remove local server...*, then delete the model from `.cache/huggingface` if you like. |

## Advanced: run the server yourself

If you already run an Irodori-TTS server, or prefer to set it up by hand, the add-on uses any server that answers at `SERVER_URL` and does not start its own. The server must have the six voice files (`female_calm`, `female_bright`, `female_cool`, `male_calm`, `male_young`, `male_deep`) in its `voices` folder; they are in [`addon/irodori_audio/voices`](addon/irodori_audio/voices).

You need git, [uv](https://docs.astral.sh/uv/) and ffmpeg (on Windows: `winget install --id Git.Git -e`, `winget install --id astral-sh.uv -e`, `winget install --id Gyan.FFmpeg -e`, then open a new PowerShell). Then:

```powershell
cd $HOME
git clone https://github.com/Aratako/Irodori-TTS-Server.git
git clone https://github.com/mattias/anki-irodori-audio.git
cd Irodori-TTS-Server
uv sync --extra cu128
Copy-Item ..\anki-irodori-audio\addon\irodori_audio\voices\*.wav voices\
uv run --no-sync python -m irodori_openai_tts --host 127.0.0.1 --port 8088
```

Use `--extra cpu` instead of `--extra cu128` without an NVIDIA GPU, or `--extra rocm` for AMD on Linux. Leave the window open while you use Anki, and check <http://127.0.0.1:8088/health>. Keep the host on `127.0.0.1`. Helper scripts are in [`server/`](server): `start-irodori.ps1 -ServerDir <folder>` or `start-irodori.sh <folder>`.

To make sure the add-on never manages a server itself, set `AUTO_START_SERVER` to `false` and use a server that is already running.

## Tips and known limits

- **Pronunciation is not controllable.** Unlike VOICEVOX there is no kana to correct. Rare names and unusual readings can be wrong. Listen first.
- **Laughs and breaths are not guaranteed.** The model sometimes adds a stray cry or breath after a sentence. The add-on detects clips that are far too long and regenerates them with another seed.
- **Whisper** is the least reliable emotion, especially for the male voices.
- **Emoji** in the text gave breathing artefacts in some tests, so emotions are set with a caption instead. The only exception is whisper, which also wraps the text in 🤫 and …. This only changes what is sent to the model, never your note.
- **Reference voices should be short** (about 3 s). A 4 s reference made one voice keep talking after the sentence ended.
- Do not use real people's voices (audiobook narrators, actors) as references. The model's terms forbid cloning a person without consent. The bundled voices were made with the model's own Voice Design (a text description, no reference audio) and do not imitate anyone.
- The automatic setup was tested on Windows 11. Linux and macOS use the same code but are untested.

## Licenses and credits

- Add-on code: MIT.
- [Irodori-TTS](https://github.com/Aratako/Irodori-TTS), [Irodori-TTS-Server](https://github.com/Aratako/Irodori-TTS-Server) and the model [Aratako/Irodori-TTS-v4-Small](https://huggingface.co/Aratako/Irodori-TTS-v4-Small) are by Aratako (MIT; see the model card for usage restrictions). Generated audio carries an inaudible watermark.
