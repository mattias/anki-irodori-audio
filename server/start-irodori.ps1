# Start the Irodori-TTS server on this computer only (127.0.0.1).
# Usage: .\start-irodori.ps1 -ServerDir C:\path\to\Irodori-TTS-Server
# (or copy this file into the Irodori-TTS-Server folder and run it there)
param([string]$ServerDir = $PSScriptRoot)
if (-not (Test-Path (Join-Path $ServerDir "pyproject.toml"))) {
    Write-Error "No Irodori-TTS-Server project in '$ServerDir'. Pass the folder where you cloned it: -ServerDir <path>"
    exit 1
}
Set-Location $ServerDir
uv run --no-sync python -m irodori_openai_tts --host 127.0.0.1 --port 8088
