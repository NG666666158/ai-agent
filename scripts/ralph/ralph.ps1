param(
    [ValidateSet("claude", "amp")]
    [string]$Tool = "claude",
    [int]$MaxIterations = 10
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$PrdFile = Join-Path $ScriptDir "prd.json"
$ProgressFile = Join-Path $ScriptDir "progress.txt"
$ArchiveDir = Join-Path $ScriptDir "archive"
$LastBranchFile = Join-Path $ScriptDir ".last-branch"
$PromptFile = if ($Tool -eq "claude") { Join-Path $ScriptDir "CLAUDE.md" } else { Join-Path $ScriptDir "prompt.md" }

function Get-BranchNameFromPrd {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        return ""
    }
    $json = Get-Content $Path -Raw | ConvertFrom-Json
    return [string]$json.branchName
}

function Write-InitialProgressFile {
    @"
# Ralph Progress Log
Started: $(Get-Date -Format s)
---
"@ | Set-Content -Path $ProgressFile -Encoding UTF8
}

function Initialize-ProgressFile {
    if (-not (Test-Path $ProgressFile)) {
        Write-InitialProgressFile
    }
}

function Archive-PreviousRunIfNeeded {
    if (-not (Test-Path $PrdFile) -or -not (Test-Path $LastBranchFile)) {
        return
    }

    $currentBranch = Get-BranchNameFromPrd -Path $PrdFile
    $lastBranch = (Get-Content $LastBranchFile -Raw).Trim()

    if (
        [string]::IsNullOrWhiteSpace($currentBranch) -or
        [string]::IsNullOrWhiteSpace($lastBranch) -or
        $currentBranch -eq $lastBranch
    ) {
        return
    }

    $folderName = $lastBranch -replace '^ralph/', ''
    $archiveTarget = Join-Path $ArchiveDir ("{0}-{1}" -f (Get-Date -Format "yyyy-MM-dd"), $folderName)
    New-Item -ItemType Directory -Path $archiveTarget -Force | Out-Null

    if (Test-Path $PrdFile) {
        Copy-Item $PrdFile (Join-Path $archiveTarget "prd.json") -Force
    }
    if (Test-Path $ProgressFile) {
        Copy-Item $ProgressFile (Join-Path $archiveTarget "progress.txt") -Force
    }

    Write-InitialProgressFile
}

function Ensure-TargetBranch {
    $branchName = Get-BranchNameFromPrd -Path $PrdFile
    if ([string]::IsNullOrWhiteSpace($branchName)) {
        throw "scripts/ralph/prd.json is missing branchName."
    }

    $currentBranch = (git -C $RepoRoot branch --show-current).Trim()
    if ($currentBranch -eq $branchName) {
        return
    }

    $refName = "refs/heads/$branchName"
    $branchExists = $true
    try {
        git -C $RepoRoot show-ref --verify --quiet $refName | Out-Null
    } catch {
        $branchExists = $false
    }

    if ($branchExists) {
        git -C $RepoRoot checkout $branchName | Out-Host
    } else {
        git -C $RepoRoot checkout -b $branchName main | Out-Host
    }
}

Archive-PreviousRunIfNeeded
Initialize-ProgressFile

$activeBranch = Get-BranchNameFromPrd -Path $PrdFile
if (-not [string]::IsNullOrWhiteSpace($activeBranch)) {
    $activeBranch | Set-Content -Path $LastBranchFile -Encoding UTF8
}

Write-Host "Starting Ralph automation - Tool: $Tool - Max iterations: $MaxIterations"

for ($i = 1; $i -le $MaxIterations; $i++) {
    Write-Host ""
    Write-Host "==============================================================="
    Write-Host ("  Ralph Iteration {0} of {1} ({2})" -f $i, $MaxIterations, $Tool)
    Write-Host "==============================================================="

    Ensure-TargetBranch

    if ($Tool -eq "amp") {
        throw "Amp prompt exists, but amp CLI is not validated on this machine. Use -Tool claude first."
    }

    $null = Get-Content $PromptFile -Raw
    $captured = Get-Content $PromptFile -Raw | & claude --dangerously-skip-permissions --print 2>&1
    $outputText = ($captured | Out-String)
    $captured | Out-Host

    if ($outputText -match "<promise>COMPLETE</promise>") {
        Write-Host ""
        Write-Host "Ralph completed all tasks."
        exit 0
    }

    Write-Host ("Iteration {0} complete. Continuing..." -f $i)
    Start-Sleep -Seconds 2
}

Write-Host ""
Write-Host ("Ralph reached max iterations ({0}) without completing all tasks." -f $MaxIterations)
Write-Host "Check scripts/ralph/progress.txt for status."
exit 1
