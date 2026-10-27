# Optional: install the prerequisites on a fresh Windows machine with winget.
#   powershell -ExecutionPolicy Bypass -File install\setup-windows.ps1
# Installs Git, Python 3.12, Node.js LTS and Codex CLI. Antigravity CLI is installed
# separately from https://antigravity.google/docs/getting-started (Windows tab).
$ErrorActionPreference = "Continue"

foreach ($id in @("Git.Git", "Python.Python.3.12", "OpenJS.NodeJS.LTS")) {
    Write-Host "== $id" -ForegroundColor Cyan
    winget install -e --id $id --accept-source-agreements --accept-package-agreements --silent
}

# refresh PATH for this session so npm is found right away
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")

Write-Host "== Codex CLI" -ForegroundColor Cyan
npm install -g @openai/codex

Write-Host "`nNext:" -ForegroundColor Green
Write-Host "  1. Install Antigravity CLI: https://antigravity.google/docs/getting-started (Windows tab)"
Write-Host "  2. Open a NEW terminal and sign in:  codex login   then   agy   (sign in, then /exit)"
Write-Host "  3. Run install\install.ps1, then:  py `$HOME\.claude\skills\boss\scripts\orch.py doctor --live"
