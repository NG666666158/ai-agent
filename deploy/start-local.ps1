$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "src"

python -m pip install -e .
Set-Location "$PSScriptRoot\..\frontend"
npm install
npm run build
Set-Location "$PSScriptRoot\.."

python -m uvicorn --app-dir src orion_agent.main:app --host 127.0.0.1 --port 8011
