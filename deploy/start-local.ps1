$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "src"

if (Test-Path "$PSScriptRoot\.env") {
  Get-Content "$PSScriptRoot\.env" | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -match '^\s*$') {
      return
    }
    $name, $value = $_ -split '=', 2
    if ($name) {
      [Environment]::SetEnvironmentVariable($name.Trim(), ($value ?? "").Trim(), "Process")
    }
  }
}

python -m pip install -e .
Set-Location "$PSScriptRoot\..\frontend"
npm install
npm run build
Set-Location "$PSScriptRoot\.."

python -m uvicorn --app-dir src orion_agent.main:app --host 127.0.0.1 --port 8011
