# Finds ISCC.exe anywhere it might be installed, then compiles installer.iss

$searchPaths = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6.7\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)

$iscc = $searchPaths | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $iscc) {
    # Try winget as last resort
    Write-Host "  Inno Setup not found. Trying winget..."
    & winget install --id JRSoftware.InnoSetup --silent --accept-source-agreements --accept-package-agreements 2>&1 | Out-Null
    Start-Sleep -Seconds 8
    $iscc = $searchPaths | Where-Object { Test-Path $_ } | Select-Object -First 1
}

if (-not $iscc) {
    Write-Host "ERROR: Inno Setup not found. Install from https://jrsoftware.org/isinfo.php"
    exit 1
}

Write-Host "  Using: $iscc"

if (-not (Test-Path "installer_output")) {
    New-Item -ItemType Directory -Path "installer_output" | Out-Null
}

# ── Sanity Check & Cleanup: Guarantee NO data files are in dist payload ──
Write-Host "  Verifying distribution payload contains no user data..."
$forbiddenDataFiles = Get-ChildItem -Path "dist\FinanceWiseTBM" -Recurse -Include "*.sqlite3","*.db","*.sqlite","license.key" -File -ErrorAction SilentlyContinue
if ($forbiddenDataFiles) {
    Write-Host "  [CLEANUP] Stripping data files found in dist payload:" -ForegroundColor Yellow
    foreach ($f in $forbiddenDataFiles) {
        Write-Host "    Removed: $($f.FullName)" -ForegroundColor Yellow
        Remove-Item $f.FullName -Force -ErrorAction SilentlyContinue
    }
}

$userMediaDirs = @(
    "dist\FinanceWiseTBM\_internal\media",
    "dist\FinanceWiseTBM\media"
)
foreach ($dir in $userMediaDirs) {
    if (Test-Path $dir) {
        Write-Host "  [CLEANUP] Stripping media folder from dist payload: $dir" -ForegroundColor Yellow
        Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$issContent = Get-Content "installer.iss" -Raw
if ($issContent -match '#define\s+AppVersion\s+"([^"]+)"') {
    $version = $matches[1]
} else {
    $version = "1.1.0"
}

$installerExe = "installer_output\FinanceWiseTBM_Setup_v${version}.exe"
if (Test-Path $installerExe) { Remove-Item $installerExe -Force -ErrorAction SilentlyContinue }

$proc = Start-Process `
    -FilePath $iscc `
    -ArgumentList "installer.iss" `
    -WorkingDirectory (Get-Location).Path `
    -Wait -PassThru -NoNewWindow `
    -RedirectStandardOutput "iscc_out.txt" `
    -RedirectStandardError  "iscc_err.txt"

Get-Content "iscc_out.txt" -ErrorAction SilentlyContinue
Get-Content "iscc_err.txt" -ErrorAction SilentlyContinue
Remove-Item "iscc_out.txt","iscc_err.txt" -ErrorAction SilentlyContinue

if ($proc.ExitCode -eq 0) {
    if (Test-Path $installerExe) {
        $sz = [math]::Round((Get-Item $installerExe).Length / 1MB, 1)
        Write-Host ""
        Write-Host "  Installer ready: $installerExe  ($sz MB)"
    } else {
        Write-Host "  Installer compiled successfully."
    }
    exit 0
} else {
    Write-Host "ERROR: ISCC exited with code $($proc.ExitCode)"
    exit $proc.ExitCode
}
