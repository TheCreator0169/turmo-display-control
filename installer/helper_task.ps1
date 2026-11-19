# Registers or removes the elevated scheduled task "TURMO CpuTemp Helper" (same task and XML as the Settings button).
# Run by the installer (already admin). Usage: helper_task.ps1 -Action install|remove [-Dir <folder with TURMO-CpuTempHelper.exe>]
param([Parameter(Mandatory)][ValidateSet('install','remove')][string]$Action, [string]$Dir = '')
$ErrorActionPreference = 'Stop'
$task = 'TURMO CpuTemp Helper'
try {
  if ($Action -eq 'install') {
    $exe = Join-Path $Dir 'TURMO-CpuTempHelper.exe'
    if (-not (Test-Path -LiteralPath $exe)) { throw "helper not found: $exe" }
    $user = "$env:USERDOMAIN\$env:USERNAME"
    $xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>TURMO CPU temperature helper (elevated, localhost read-only)</Description></RegistrationInfo>
  <Triggers><LogonTrigger><Enabled>true</Enabled><UserId>$user</UserId></LogonTrigger></Triggers>
  <Principals><Principal id="Author"><UserId>$user</UserId><LogonType>InteractiveToken</LogonType><RunLevel>HighestAvailable</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure><Interval>PT1M</Interval><Count>3</Count></RestartOnFailure>
    <StartWhenAvailable>true</StartWhenAvailable>
    <Enabled>true</Enabled>
    <Hidden>true</Hidden>
  </Settings>
  <Actions Context="Author"><Exec><Command>$exe</Command><WorkingDirectory>$Dir</WorkingDirectory></Exec></Actions>
</Task>
"@
    Register-ScheduledTask -TaskName $task -Xml $xml -Force | Out-Null
    Start-ScheduledTask -TaskName $task
  } else {
    Stop-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue
    # by the exact path of this install, never by process name
    $exe = Join-Path $Dir 'TURMO-CpuTempHelper.exe'
    Get-CimInstance Win32_Process -Filter "Name='TURMO-CpuTempHelper.exe'" |
      Where-Object { $_.ExecutablePath -eq $exe } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
  }
} catch {
  $_ | Out-File (Join-Path $env:TEMP 'turmo_installer_helper.log')
  exit 1
}
