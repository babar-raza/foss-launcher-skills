# install.ps1 — Install foss-launcher-skills into a target content repo (Windows).
#
# Usage:
#   .\install.ps1 -Target C:\path\to\target-repo                  # Embedded mode
#   .\install.ps1 -Target C:\path\to\target-repo -Standalone       # Standalone mode

param(
    [Parameter(Mandatory=$true)]
    [string]$Target,

    [switch]$Standalone
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Target = (Resolve-Path $Target).Path

Write-Host "=== foss-launcher-skills installer ===" -ForegroundColor Cyan
Write-Host "Source: $ScriptDir"
Write-Host "Target: $Target"
Write-Host "Mode:   $(if ($Standalone) { 'standalone' } else { 'embedded' })"
Write-Host ""

if ($Standalone) {
    # --- Standalone mode ---
    Write-Host "--- Configuring standalone mode ---" -ForegroundColor Yellow

    # Update content_repo in config.yaml
    $configPath = Join-Path $ScriptDir "config.yaml"
    if (Test-Path $configPath) {
        $content = Get-Content $configPath -Raw
        $content = $content -replace '(?m)^content_repo:.*', "content_repo: `"$Target`""
        Set-Content $configPath $content -NoNewline
        Write-Host "Set content_repo to: $Target"
    }

    # Write a link file in target
    $linkFile = Join-Path $Target ".skills-link"
    "$ScriptDir`n$(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ')" | Set-Content $linkFile
    Write-Host "Created .skills-link in target."

    # Distribute skills locally
    Write-Host ""
    Write-Host "--- Distributing skills ---" -ForegroundColor Yellow
    python "$ScriptDir\tools\distribute.py" $ScriptDir

} else {
    # --- Embedded mode (original behavior) ---

    # 1. Copy scripts
    Write-Host "--- Copying scripts/ ---" -ForegroundColor Yellow
    $scriptsTarget = Join-Path $Target "scripts"
    if (-not (Test-Path $scriptsTarget)) { New-Item -ItemType Directory -Path $scriptsTarget | Out-Null }
    Copy-Item "$ScriptDir\scripts\*.py" $scriptsTarget -Force -ErrorAction SilentlyContinue
    Copy-Item "$ScriptDir\scripts\requirements.txt" $scriptsTarget -Force -ErrorAction SilentlyContinue
    Write-Host "Done."

    # 2. Copy configs/
    Write-Host ""
    Write-Host "--- Copying configs/ ---" -ForegroundColor Yellow
    $configsTarget = Join-Path $Target "configs"
    if (-not (Test-Path $configsTarget)) { New-Item -ItemType Directory -Path $configsTarget | Out-Null }
    Copy-Item "$ScriptDir\configs\*.yaml" $configsTarget -Force -ErrorAction SilentlyContinue
    Write-Host "Done."

    # 3. Copy config.yaml with content_repo set to current dir
    Write-Host ""
    Write-Host "--- Copying config.yaml ---" -ForegroundColor Yellow
    $configSrc = Join-Path $ScriptDir "config.yaml"
    $configDst = Join-Path $Target "config.yaml"
    Copy-Item $configSrc $configDst -Force
    $content = Get-Content $configDst -Raw
    $content = $content -replace '(?m)^content_repo:.*', 'content_repo: "."'
    Set-Content $configDst $content -NoNewline
    Write-Host "Done."

    # 3. Distribute skills to agent directories
    Write-Host ""
    Write-Host "--- Distributing skills ---" -ForegroundColor Yellow
    python "$ScriptDir\tools\distribute.py" $Target

    # 4. Copy AGENTS.template.md if AGENTS.md doesn't exist
    $agentsPath = Join-Path $Target "AGENTS.md"
    if (-not (Test-Path $agentsPath)) {
        Write-Host ""
        Write-Host "--- Creating AGENTS.md from template ---" -ForegroundColor Yellow
        Copy-Item "$ScriptDir\AGENTS.template.md" $agentsPath
        Write-Host "Created AGENTS.md (review and customize for your project)."
    } else {
        Write-Host ""
        Write-Host "AGENTS.md already exists in target - skipping." -ForegroundColor DarkGray
    }

    # 5. Write version marker
    $versionFile = Join-Path $Target ".skills-source"
    "$ScriptDir`n$(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ')" | Set-Content $versionFile
}

Write-Host ""
Write-Host "=== Installation complete ===" -ForegroundColor Green
Write-Host "Installed to: $Target"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. pip install -r scripts/requirements.txt"
Write-Host "  2. Review AGENTS.md and customize for your project"
Write-Host "  3. Run your first skill: /repo-scout {family} {platform} {repo-path}"
Write-Host "  4. Then: /truth-merge {family} {platform}"
Write-Host "  5. Scan existing content: /corpus-scan {family} {platform} docs"
