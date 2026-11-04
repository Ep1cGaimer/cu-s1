param([switch]$SkipModelDownload)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
function Check-Exit([string]$Task) {
    if ($LASTEXITCODE -ne 0) { throw "$Task failed (exit $LASTEXITCODE)." }
}
if (Get-Command uv -ErrorAction SilentlyContinue) {
    & uv sync --frozen
    Check-Exit 'Installing Python dependencies'
} else {
    if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
        if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
            throw 'Install Python 3.12 from python.org (with the Python launcher), then run setup again.'
        }
        & py -3.12 -m venv .venv
        Check-Exit 'Creating the Python environment'
    }
    & .venv/Scripts/python.exe -m pip install -e .
    Check-Exit 'Installing Python dependencies'
}
$ollamaCommand = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollamaCommand) {
    $ollamaPath = Join-Path $env:LOCALAPPDATA 'Programs/Ollama/ollama.exe'
    if (Test-Path -LiteralPath $ollamaPath) { $ollamaCommand = Get-Item -LiteralPath $ollamaPath }
}
if (-not $ollamaCommand) {
    throw 'Install and start Ollama from ollama.com, then run setup again.'
}
$ollamaExe = if ($ollamaCommand.Source) { $ollamaCommand.Source } else { $ollamaCommand.FullName }
if (-not $SkipModelDownload) {
    Write-Host 'Checking/downloading the local vision model (about 2 GB on first setup)...'
    & $ollamaExe pull qwen3-vl:2b-instruct
    Check-Exit 'Preparing the vision model; make sure Ollama is running'
}
& .venv/Scripts/python.exe -m cu_s1.doctor --json
Check-Exit 'Checking the local model connection'
