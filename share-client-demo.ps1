$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontendDir = Join-Path $projectRoot "frontend"
$backendDir = Join-Path $projectRoot "backend"
$envPath = Join-Path $projectRoot ".env"
$cloudflaredLog = Join-Path $projectRoot "cloudflared-demo.log"

function Update-EnvValue {
    param(
        [string]$Path,
        [string]$Key,
        [string]$Value
    )

    $content = Get-Content $Path -Raw
    $escapedValue = [Regex]::Escape($Value)

    if ($content -match "(?m)^$Key=") {
        $content = [Regex]::Replace($content, "(?m)^$Key=.*$", "$Key=$Value")
    } else {
        $content = $content.TrimEnd("`r", "`n") + "`r`n$Key=$Value`r`n"
    }

    Set-Content -Path $Path -Value $content
}

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    throw "cloudflared is not installed or not on PATH."
}

if (-not (Test-Path $envPath)) {
    throw ".env file not found at $envPath"
}

if (Test-Path $cloudflaredLog) {
    Remove-Item $cloudflaredLog -Force
}

$cloudflared = Start-Process `
    -FilePath "cloudflared" `
    -ArgumentList "tunnel", "--url", "http://localhost:3000", "--logfile", $cloudflaredLog `
    -WorkingDirectory $projectRoot `
    -PassThru

$publicUrl = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $cloudflaredLog) {
        $match = Select-String -Path $cloudflaredLog -Pattern "https://[-a-z0-9]+\.trycloudflare\.com" | Select-Object -First 1
        if ($match) {
            $publicUrl = $match.Matches[0].Value
            break
        }
    }
}

if (-not $publicUrl) {
    Stop-Process -Id $cloudflared.Id -Force
    throw "Could not read the Cloudflare public URL. Check $cloudflaredLog for details."
}

Update-EnvValue -Path $envPath -Key "FRONTEND_URL" -Value $publicUrl
Update-EnvValue -Path $envPath -Key "GITHUB_CALLBACK_URL" -Value "$publicUrl/auth/github/callback"
Update-EnvValue -Path $envPath -Key "BACKEND_URL" -Value "http://localhost:8000"
Update-EnvValue -Path $envPath -Key "SESSION_COOKIE_SECURE" -Value "true"
Update-EnvValue -Path $envPath -Key "SESSION_COOKIE_SAMESITE" -Value "none"
Update-EnvValue -Path $envPath -Key "NEXT_PUBLIC_API_BASE_URL" -Value ""

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$backendDir'; .\.venv\Scripts\activate; uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$frontendDir'; npm run dev"

Write-Host ""
Write-Host "Frontend public URL: $publicUrl"
Write-Host "GitHub callback URL: $publicUrl/auth/github/callback"
Write-Host ""
Write-Host "Update your GitHub OAuth App to use the callback URL above, then open the frontend URL on another device."
