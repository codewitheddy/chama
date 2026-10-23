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

$old = "installer_output\FinanceWiseTBM_Setup_v1.0.0.exe"
if (Test-Path $old) { Remove-Item $old -Force -ErrorAction SilentlyContinue }

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
    $sz = [math]::Round((Get-Item $old).Length / 1MB, 1)
    Write-Host ""
    Write-Host "  Installer ready: installer_output\FinanceWiseTBM_Setup_v1.0.0.exe  ($sz MB)"
    exit 0
} else {
    Write-Host "ERROR: ISCC exited with code $($proc.ExitCode)"
    exit $proc.ExitCode
}
