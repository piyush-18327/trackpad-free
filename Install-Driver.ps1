param([string]$Python = 'python.exe')

$ErrorActionPreference = 'Stop'
$log = Join-Path $PSScriptRoot 'driver-install.log'
try {
    "Trackpad Free driver installation - $(Get-Date -Format o)" | Set-Content $log -Encoding UTF8
    $admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $admin) { throw 'Run this installer as administrator.' }
    if ([Environment]::OSVersion.Version.Build -lt 22000) { throw 'This signed package requires Windows 11.' }

    $result = & $Python (Join-Path $PSScriptRoot 'driver_package.py') --verify 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Package verification failed: $result" }
    $inf = [string]($result | Select-Object -Last 1)
    $catalog = Join-Path (Split-Path $inf) 'AmtPtpDevice.cat'
    $signature = Get-AuthenticodeSignature $catalog
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Microsoft Windows Hardware Compatibility Publisher') {
        throw 'The driver catalog does not have a valid Microsoft hardware signature.'
    }
    "Verified upstream v2.2 package and Microsoft signature. Installing $inf" | Add-Content $log -Encoding UTF8
    $output = & "$env:windir\System32\pnputil.exe" /add-driver $inf /install 2>&1
    $code = $LASTEXITCODE
    $output | Add-Content $log -Encoding UTF8
    if ($code -notin @(0, 3010)) { throw "PnPUtil failed with exit code $code. See output above." }
    if ($code -eq 3010) {
        'Installation completed. Windows requires a restart.' | Add-Content $log -Encoding UTF8
    } else {
        'Package installation completed. Reconnect the trackpad and refresh Trackpad Free to verify the active driver.' | Add-Content $log -Encoding UTF8
    }
} catch {
    "ERROR: $_" | Add-Content $log -Encoding UTF8
    Write-Error $_
    exit 1
}
