# Start the Irodori-TTS server on this computer only (127.0.0.1).
# Run it from the folder where you cloned Irodori-TTS-Server, or pass the folder as an argument.
param([string]$ServerDir = $PSScriptRoot)
Set-Location $ServerDir
uv run --no-sync python -m irodori_openai_tts --host 127.0.0.1 --port 8088
