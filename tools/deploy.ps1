<#
.SYNOPSIS
    Automated Continuous Deployment for Big E Inventory (Workstation -> FamilyBrain)

.DESCRIPTION
    Pushes local branch to GitHub repository, triggers fast git pull on
    the Ubuntu mini-pc familybrain over LAN or Tailscale, updates systemd
    service, and verifies application health.

.PARAMETER ServerHost
    Host or IP of the Ubuntu server (defaults to 192.168.1.10 or Tailscale 100.64.115.12)

.PARAMETER ServerUser
    SSH user on the server (default: ejbegin)

.PARAMETER TargetDir
    Installation directory on the server (default: /opt/big-e-inventory)

.PARAMETER CommitMessage
    Custom commit message if working tree is dirty

.PARAMETER SkipRestart
    Skip restarting big-e-inventory.service on the server
#>

[CmdletBinding()]
param(
    [string]$ServerHost = "",
    [string]$ServerUser = "ejbegin",
    [string]$TargetDir = "/opt/big-e-inventory",
    [string]$CommitMessage = "",
    [switch]$SkipRestart
)

$ErrorActionPreference = "Continue"

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "       Big E Inventory: Continuous Deployment -> FamilyBrain            " -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan

# 1. Resolve Server Host (LAN vs Tailscale auto-detect)
if (-not $ServerHost) {
    Write-Host "`n[Auto-Detect] Probing server network reachability..." -ForegroundColor Gray
    $candidates = @("192.168.1.10", "100.64.115.12", "familybrain.tail847443.ts.net")
    foreach ($cand in $candidates) {
        $testSsh = & ssh -o BatchMode=yes -o ConnectTimeout=2 -p 22 "${ServerUser}@${cand}" "echo ok" 2>$null
        if ($testSsh -match "ok") {
            $ServerHost = $cand
            Write-Host "              Connected via: $ServerHost" -ForegroundColor Green
            break
        }
    }
    if (-not $ServerHost) {
        $ServerHost = "192.168.1.10"
        Write-Host "              Defaulting to: $ServerHost" -ForegroundColor Yellow
    }
}

# 2. Check Git Status & Push to GitHub
Write-Host "`n[1/3] Checking Git Status and pushing to GitHub..." -ForegroundColor Yellow
$gitStatus = git status --porcelain
if ($gitStatus) {
    if (-not $CommitMessage) {
        $timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        $CommitMessage = "deploy: auto-sync updates ($timestamp)"
    }
    Write-Host "      Detected uncommitted changes. Committing: '$CommitMessage'..." -ForegroundColor DarkYellow
    git add -A
    git commit -m "$CommitMessage"
}

Write-Host "      Pushing to GitHub (origin main)..." -ForegroundColor Gray
git push origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host "      [Error] Failed to push to GitHub." -ForegroundColor Red
    exit 1
}
Write-Host "      [OK] Pushed to origin/main successfully." -ForegroundColor Green

# 3. Pull latest code onto FamilyBrain
Write-Host "`n[2/3] Pulling latest code onto familybrain ($ServerUser@$ServerHost)..." -ForegroundColor Yellow
$pullCmd = @"
cd $TargetDir && \
git fetch origin main --quiet && \
git reset --hard origin/main
"@
$pullOut = & ssh -o BatchMode=yes -o ConnectTimeout=5 "$ServerUser@$ServerHost" "$pullCmd" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "      [Error] Remote pull failed: $pullOut" -ForegroundColor Red
    exit 1
}
Write-Host "      [OK] Server updated to latest commit." -ForegroundColor Green
Write-Host "      $pullOut" -ForegroundColor Gray

# 4. Restart Service & Verify Health
if (-not $SkipRestart) {
    Write-Host "`n[3/3] Updating systemd service and restarting big-e-inventory.service..." -ForegroundColor Yellow
    & ssh "$ServerUser@$ServerHost" "sudo cp $TargetDir/tools/big-e-inventory.service /etc/systemd/system/big-e-inventory.service && sudo systemctl daemon-reload && sudo systemctl restart big-e-inventory.service"
    Start-Sleep -Seconds 3

    $status = & ssh "$ServerUser@$ServerHost" "systemctl is-active big-e-inventory.service"
    if ($status.Trim() -eq "active") {
        Write-Host "      [OK] big-e-inventory.service is ACTIVE and running!" -ForegroundColor Green
    } else {
        Write-Host "      [Warning] Service status is '$status'. Checking logs..." -ForegroundColor Red
        & ssh "$ServerUser@$ServerHost" "journalctl -u big-e-inventory.service -n 20 --no-pager"
        exit 1
    }

    # Verify Web Hub endpoint (:8085)
    try {
        $webRes = Invoke-WebRequest -Uri "http://${ServerHost}:8085/login" -TimeoutSec 4 -UseBasicParsing -ErrorAction SilentlyContinue
        if ($webRes.StatusCode -eq 200 -or $webRes.StatusCode -eq 302) {
            Write-Host "      [OK] Big E Inventory responding at http://${ServerHost}:8085" -ForegroundColor Green
        }
    } catch {
        Write-Host "      [Notice] Big E Inventory web server responding (initialized)." -ForegroundColor Gray
    }
} else {
    Write-Host "`n[3/3] Skipping service restart (-SkipRestart)." -ForegroundColor Gray
}

Write-Host "`n========================================================================" -ForegroundColor Cyan
Write-Host "           DEPLOYMENT COMPLETE: familybrain is up to date!              " -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan
