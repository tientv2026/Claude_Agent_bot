# agent-boss installer for Windows PowerShell.
#   From a clone:  powershell -ExecutionPolicy Bypass -File install\install.ps1
#   One-liner:     irm https://raw.githubusercontent.com/tientv2026/Claude_Agent_bot/main/install/install.ps1 | iex
$ErrorActionPreference = "Stop"

$repo = if ($env:AGENT_BOSS_REPO) { $env:AGENT_BOSS_REPO } else { "tientv2026/Claude_Agent_bot" }
$ref  = if ($env:AGENT_BOSS_REF)  { $env:AGENT_BOSS_REF }  else { "main" }
$base = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $env:USERPROFILE ".claude" }
$dest = Join-Path $base "skills\boss"
$files = @("SKILL.md", "scripts/orch.py")

$srcDir = $null
if ($PSScriptRoot) {
    $candidate = Join-Path $PSScriptRoot "..\skills\boss"
    if (Test-Path (Join-Path $candidate "SKILL.md")) { $srcDir = (Resolve-Path $candidate).Path }
}

New-Item -ItemType Directory -Force -Path (Join-Path $dest "scripts") | Out-Null
foreach ($f in $files) {
    $target = Join-Path $dest $f
    if ($srcDir) {
        Copy-Item (Join-Path $srcDir $f) $target -Force
    } else {
        Invoke-WebRequest -UseBasicParsing "https://raw.githubusercontent.com/$repo/$ref/skills/boss/$f" -OutFile $target
    }
}
Write-Host "Installed /boss skill -> $dest"

$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command python -ErrorAction SilentlyContinue }
if ($py -and $py.Source -notlike "*WindowsApps*") {
    & $py.Source (Join-Path $dest "scripts\orch.py") doctor
} else {
    Write-Host "Python 3.9+ is required:  winget install -e --id Python.Python.3.12" -ForegroundColor Yellow
}
Write-Host "`nDone. In Claude Code, open your project and type:  /boss <what to build>"
