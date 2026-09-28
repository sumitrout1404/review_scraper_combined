# Commit (if there are changes) and push to all three repositories:
#   origin   -> review_scraper_combined  (this repo, backend/ + frontend/)
#   backend  -> review_scraper_backend   (contents of backend/ at the root)
#   frontend -> review_scraper_frontend  (contents of frontend/ at the root)
#
# Usage: .\scripts\push-all.ps1 "commit message"
param([string]$Message)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (git status --porcelain) {
    if (-not $Message) {
        Write-Error "There are uncommitted changes. Pass a commit message: .\scripts\push-all.ps1 ""your message"""
    }
    git add -A
    git commit -m $Message
    if ($LASTEXITCODE -ne 0) { Write-Error "git commit failed" }
}

foreach ($remote in @("origin", "backend", "frontend")) {
    git remote get-url $remote *> $null
    if ($LASTEXITCODE -ne 0) { Write-Error "Missing remote '$remote'. See README section 0." }
}

Write-Output "==> combined"
git push origin main
if ($LASTEXITCODE -ne 0) { Write-Error "push to origin failed" }

Write-Output "==> backend"
git subtree push --prefix=backend backend main
if ($LASTEXITCODE -ne 0) { Write-Error "subtree push to backend failed" }

Write-Output "==> frontend"
git subtree push --prefix=frontend frontend main
if ($LASTEXITCODE -ne 0) { Write-Error "subtree push to frontend failed" }

Write-Output "Done - all three repositories updated."
