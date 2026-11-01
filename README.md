# Irodori Audio for Anki

An Anki add-on that creates natural-sounding Japanese **sentence audio** with [Irodori-TTS](https://github.com/Aratako/Irodori-TTS), running on your own computer. It picks a female or male voice and an emotion for every sentence, writes the audio to your `SentenceAudio` field, and never touches recorded audio.

Tested with the Kiku note type (fields `Sentence` and `SentenceAudio`), Anki 26.9.3, Windows 11 and an NVIDIA RTX 4080.

## What it does

- Menu in the card browser: **Cards > Generate Sentence Audio (Irodori)**.
- Six voices (3 female, 3 male) and seven emotions: neutral, happy, sad, angry, scared, whisper, joking.
- Voice and emotion are chosen by simple rules from the sentence (speech style such as 俺, ぼく, だぜ, わよ; keywords; punctuation). No AI model besides the TTS is needed. When unsure it uses neutral and a pseudo-random voice.
- Safe by default: notes with recorded audio are skipped, your `Sentence` field is never changed, old audio files are kept, and a whole run can be undone with *Edit > Undo*. Nothing changes if the server is down.
- Runs in the background with progress and a cancel button.

## 1. Run the Irodori server locally

You need an NVIDIA GPU with about 6 GB of free VRAM (CPU works but is slow), [uv](https://docs.astral.sh/uv/), git and ffmpeg (for mp3).

```bash
git clone https://github.com/Aratako/Irodori-TTS-Server.git
cd Irodori-TTS-Server
uv sync --extra cu128          # NVIDIA CUDA 12.8. Use --extra cpu for CPU only
cp .env.example .env
```

Edit `.env`:

```
IRODORI_HOST=127.0.0.1
IRODORI_HF_CHECKPOINT=Aratako/Irodori-TTS-v4-Small
```

Leave `IRODORI_DEFAULT_NUM_STEPS` unset. Keep the host on `127.0.0.1` so other computers cannot reach the server.

Copy the six `.wav` files from this repo's `voices/` folder into `Irodori-TTS-Server/voices/`. Their names (`female_calm`, `female_bright`, `female_cool`, `male_calm`, `male_young`, `male_deep`) are the voice ids the add-on uses.

Start the server (the first request downloads the model, about a minute):

```bash
uv run --no-sync python -m irodori_openai_tts --host 127.0.0.1 --port 8088
```

Or use `server/start-irodori.ps1 -ServerDir <your Irodori-TTS-Server folder>` (Windows) or `server/start-irodori.sh <folder>` (Linux/macOS), or copy the script into the server folder and run it there. Check it at <http://127.0.0.1:8088/health>.

Measured on an RTX 4080: about 0.9 s per sentence and 4-5 GB of VRAM.

## 2. Install the add-on

Install from [AnkiWeb](https://ankiweb.net/shared/info/2078760911) (code: `2078760911`), download `irodori_audio.ankiaddon` from the [releases page](https://github.com/mattias/anki-irodori-audio/releases) and open it with Anki, or copy `addon/irodori_audio/` into your Anki `addons21` folder. Restart Anki.

## 3. Use it

1. Start the server.
2. In the card browser, select a few notes and listen to the result first.
3. **Cards > Generate Sentence Audio (Irodori)**. A dialog shows how many notes get audio and how many are skipped.
4. Notes with new audio get the tag `irodori`.

Settings are in *Tools > Add-ons > Irodori Audio > Config*: field names, audio format, overwrite behavior, voices and emotion captions.

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
