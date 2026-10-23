# Installs Inno Setup 6 using winget (Windows Package Manager, built into Win10/11)
# Falls back to a direct GitHub mirror if winget is unavailable.

$ErrorActionPreference = 'Stop'

function Test-InnoInstalled {
    return (Test-Path "C:\Program Files (x86)\Inno Setup 6\ISCC.exe") -or
           (Test-Path "C:\Program Files\Inno Setup 6\ISCC.exe")
}

if (Test-InnoInstalled) {
    Write-Host "Inno Setup already installed."
    exit 0
}

# ── Try winget first (available on Windows 10 1809+ and all Windows 11) ──────
$winget = Get-Command winget -ErrorAction SilentlyContinue
if ($winget) {
    Write-Host "Installing Inno Setup via winget..."
    & winget install --id JRSoftware.InnoSetup --silent --accept-source-agreements --accept-package-agreements
    Start-Sleep -Seconds 5
    if (Test-InnoInstalled) {
        Write-Host "INSTALL_DONE"
        exit 0
    }
}

# ── Fallback: GitHub mirror ───────────────────────────────────────────────────
$dest = "$env:TEMP\innosetup6.exe"
$mirrors = @(
    'https://github.com/jrsoftware/issrc/releases/download/is-6_3_3/innosetup-6.3.3.exe',
    'https://github.com/jrsoftware/issrc/releases/latest/download/innosetup.exe'
)
$downloaded = $false
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

foreach ($url in $mirrors) {
    try {
        Write-Host "Trying: $url"
        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
        $sz = (Get-Item $dest).Length
        if ($sz -gt 1MB) {
            $downloaded = $true
            break
        } else {
            Write-Host "  Download too small ($sz bytes), skipping."
            Remove-Item $dest -Force -ErrorAction SilentlyContinue
        }
    } catch {
        Write-Host "  Failed: $($_.Exception.Message)"
    }
}

if ($downloaded) {
    Write-Host "Installing..."
    Start-Process -FilePath $dest -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-' -Wait
    Remove-Item $dest -Force -ErrorAction SilentlyContinue
    if (Test-InnoInstalled) {
        Write-Host "INSTALL_DONE"
        exit 0
    }
}

Write-Host "INSTALL_FAILED — Please install Inno Setup 6 manually: https://jrsoftware.org/isinfo.php"
exit 1
