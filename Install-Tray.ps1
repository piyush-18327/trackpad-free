param(
    [Parameter(Mandatory)][string]$User,
    [string]$Pythonw = 'pythonw.exe',
    [switch]$Remove
)

# Registers (or removes) a sign-in task that starts the tray icon with highest
# privileges, so battery reading works without a UAC prompt each time.
$ErrorActionPreference = 'Stop'
$log = Join-Path $PSScriptRoot 'tray-install.log'
$taskPath = '\TrackpadFree\'
$taskName = 'Trackpad Free Tray'
try {
    "Trackpad Free tray task - $(Get-Date -Format o)" | Set-Content $log -Encoding UTF8
    $admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $admin) { throw 'Run this installer as administrator.' }

    $existing = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
    if ($Remove) {
        if ($existing) {
            Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Confirm:$false
        }
        'Tray task removed.' | Add-Content $log -Encoding UTF8
        exit 0
    }

    $tray = Join-Path $PSScriptRoot 'tray.py'
    if (-not (Test-Path $tray)) { throw "Missing $tray" }
    $python = (Get-Command $Pythonw).Source
    $action = New-ScheduledTaskAction -Execute $python -Argument "`"$tray`"" -WorkingDirectory $PSScriptRoot
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $User
    $principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings -Description 'Trackpad Free battery tray icon' -Force | Out-Null
    "Registered $taskPath$taskName for $User running $python `"$tray`"" | Add-Content $log -Encoding UTF8
    Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName
    'Tray started. It will start automatically at every sign-in.' | Add-Content $log -Encoding UTF8
} catch {
    "ERROR: $_" | Add-Content $log -Encoding UTF8
    Write-Error $_
    exit 1
}
