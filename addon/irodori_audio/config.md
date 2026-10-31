**Irodori Audio** creates `SentenceAudio` from `Sentence` with a local Irodori-TTS server.

Use it from the card browser: select notes, then *Cards > Generate Sentence Audio (Irodori)*.

- `SERVER_URL`: your Irodori-TTS server (keep it on 127.0.0.1).
- `SOURCE_FIELD` / `TARGET_FIELD`: field names (default `Sentence` / `SentenceAudio`).
- `AUDIO_FORMAT`: `mp3` (needs ffmpeg on the server machine) or `wav`.
- `OVERWRITE`: replace audio made earlier by this add-on. Default `false`. Other audio, such as recordings, is never replaced.
- `TAG`: tag added to notes that get audio. Empty string = no tag.
- `SEED`: base random seed. `RETRIES`, `MAX_SECONDS_PER_CHAR`, `MAX_SECONDS_BASE`: a clip much longer than its text (a stray cry after the sentence) is regenerated with another seed.
- `VOICES`: voice id on the server, gender and caption. `EMOTION_CAPTIONS` and `EMOTION_TEXT_WRAP`: how each emotion is requested.
