param(
    [ValidateSet('All', 'AutoBuyer', 'PowerPlant')]
    [string]$Target = 'All',

    [int]$LegacyPowerPlantJobId = 0
)

$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $MyInvocation.MyCommand.Definition

function Stop-ProjectJob {
    param([string]$Name)

    $existingJobs = Get-Job -Name $Name -ErrorAction SilentlyContinue
    foreach ($job in $existingJobs) {
        Write-Host "Stopping $Name (Job $($job.Id))..."
        Stop-Job -Job $job -ErrorAction SilentlyContinue
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
    }
}

function Start-ProjectJob {
    param(
        [string]$Name,
        [string]$PythonCommand
    )

    Write-Host "Starting $Name..."
    Start-Job -Name $Name -ScriptBlock {
        param($WorkingDirectory, $Command)
        Set-Location $WorkingDirectory
        python -u -c $Command
    } -ArgumentList $projectPath, $PythonCommand
}

if ($LegacyPowerPlantJobId -gt 0) {
    $legacyJob = Get-Job -Id $LegacyPowerPlantJobId -ErrorAction SilentlyContinue
    if ($legacyJob) {
        Write-Host "Stopping legacy PowerPlant Job $LegacyPowerPlantJobId..."
        Stop-Job -Job $legacyJob -ErrorAction SilentlyContinue
        Remove-Job -Job $legacyJob -Force -ErrorAction SilentlyContinue
    }
}

if ($Target -in @('All', 'AutoBuyer')) {
    Stop-ProjectJob -Name 'AutoBuyer'
    Start-ProjectJob -Name 'AutoBuyer' -PythonCommand 'from main import run_auto_buyer; run_auto_buyer()'
}

if ($Target -in @('All', 'PowerPlant')) {
    Stop-ProjectJob -Name 'PowerPlantProducer'
    Start-ProjectJob -Name 'PowerPlantProducer' -PythonCommand "from production_monitor import setup_logger; from main import run_power_plant_producer; logger = setup_logger('production_monitor.powerplant', 'monitor_powerplant.log'); run_power_plant_producer(logger)"
}

Start-Sleep -Seconds 3

Write-Host "`nCurrent project jobs:"
Get-Job -Name AutoBuyer, PowerPlantProducer -ErrorAction SilentlyContinue |
    Select-Object Id, Name, State, HasMoreData |
    Format-Table -AutoSize

Write-Host 'Initial output:'
Get-Job -Name AutoBuyer, PowerPlantProducer -ErrorAction SilentlyContinue |
    Receive-Job -Keep -ErrorAction Continue

Write-Host "`nUse this command to check output later:"
Write-Host 'Get-Job -Name AutoBuyer,PowerPlantProducer | Receive-Job -Keep'
