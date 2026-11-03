**Irodori Audio** creates `SentenceAudio` from `Sentence` with a local Irodori-TTS server that the add-on can install and start for you (*Tools > Irodori Audio*).

Use it from the card browser: select notes, then *Cards > Generate Sentence Audio (Irodori)*.

- `SERVER_URL`: the Irodori-TTS server (keep it on 127.0.0.1). If a server already answers there, the add-on uses it and does not start its own.
- `SERVER_DIR`: install folder for the local server. Empty = the default folder in your local data directory.
- `AUTO_START_SERVER`: start the installed server when Anki starts. Default `true`.
- `BACKEND`: `auto` (default), `cpu` or `cu128`. `auto` uses the CUDA build for NVIDIA GPUs of compute capability 7.0 or newer (GTX 16 and RTX series) and the CPU build otherwise. Change it and run *Set up local server* again to reinstall.
- `ONBOARDING_SHOWN`: set to `true` once the welcome dialog has been shown. Set it to `false` to see it again.
- `SOURCE_FIELD` / `TARGET_FIELD`: field names (default `Sentence` / `SentenceAudio`).
- `AUDIO_FORMAT`: `mp3` (needs ffmpeg, which the setup installs) or `wav`.
- `OVERWRITE`: replace audio made earlier by this add-on. Default `false`. Other audio, such as recordings, is never replaced.
- `TAG`: tag added to notes that get audio. Empty string = no tag.
- `SEED`: base random seed. `RETRIES`, `MAX_SECONDS_PER_CHAR`, `MAX_SECONDS_BASE`: a clip much longer than its text (a stray cry after the sentence) is regenerated with another seed.
- `VOICES`: voice id on the server, gender and caption. `EMOTION_CAPTIONS` and `EMOTION_TEXT_WRAP`: how each emotion is requested.
