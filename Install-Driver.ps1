param(
    [string]$Python = 'python.exe',
    # driver_package.py from source, or --run=driver-package for TrackpadFree.exe
    [string]$Entry = '',
    [string]$LogDir = ''
)

$ErrorActionPreference = 'Stop'
if (-not $Entry) { $Entry = Join-Path $PSScriptRoot 'driver_package.py' }
if (-not $LogDir) { $LogDir = $PSScriptRoot }
$log = Join-Path $LogDir 'driver-install.log'
try {
    "Trackpad Free driver installation - $(Get-Date -Format o)" | Set-Content $log -Encoding UTF8
    $admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $admin) { throw 'Run this installer as administrator.' }
    if ([Environment]::OSVersion.Version.Build -lt 22000) { throw 'This signed package requires Windows 11.' }

    # Start-Process -Wait, not `& $Python`: PowerShell does not wait for a windowed
    # exe (TrackpadFree.exe) or collect its exit code when called with &.
    $out = Join-Path $LogDir 'driver-verify.out'
    $err = Join-Path $LogDir 'driver-verify.err'
    $process = Start-Process -FilePath $Python -ArgumentList @("`"$Entry`"", '--verify') -Wait -PassThru -NoNewWindow `
        -RedirectStandardOutput $out -RedirectStandardError $err
    $result = @(Get-Content $out) + @(Get-Content $err)
    Remove-Item $out, $err -ErrorAction SilentlyContinue
    if ($process.ExitCode -ne 0) { throw "Package verification failed: $($result -join ' ')" }
    $inf = [string]($result | Select-Object -First 1)
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
