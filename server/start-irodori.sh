#!/bin/sh
# Start the Irodori-TTS server on this computer only (127.0.0.1).
cd "${1:-$(dirname "$0")}" || exit 1
exec uv run --no-sync python -m irodori_openai_tts --host 127.0.0.1 --port 8088
