#!/bin/sh
# Start the Irodori-TTS server on this computer only (127.0.0.1).
# Usage: ./start-irodori.sh /path/to/Irodori-TTS-Server
# (or copy this file into the Irodori-TTS-Server folder and run it there)
dir="${1:-$(dirname "$0")}"
[ -f "$dir/pyproject.toml" ] || { echo "No Irodori-TTS-Server project in '$dir'. Pass the folder where you cloned it." >&2; exit 1; }
cd "$dir" || exit 1
exec uv run --no-sync python -m irodori_openai_tts --host 127.0.0.1 --port 8088
