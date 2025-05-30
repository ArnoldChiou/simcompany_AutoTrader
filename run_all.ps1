# run_all.ps1
# Execute all functions of main.py sequentially (excluding Login to game)

Remove-Item -ErrorAction SilentlyContinue "record/monitor_forest.log"
Remove-Item -ErrorAction SilentlyContinue "record/monitor_powerplant.log"
Remove-Item -ErrorAction SilentlyContinue "record/monitor_oilrig.log"

$projectPath = Split-Path -Parent $MyInvocation.MyCommand.Definition

# Use Start-Job to execute all functions sequentially to avoid conflicts caused by multiple Selenium instances running simultaneously
$jobs = @()

# Define the jobs and their python commands
$jobDefinitions = @(
    @{ name = 'AutoBuyer'; cmd = "from main import run_auto_buyer; run_auto_buyer()"; needsSelenium = $true },
    @{ name = 'ForestNurseryMonitor'; cmd = "from production_monitor import setup_logger; from main import run_forest_nursery_monitor; logger = setup_logger('production_monitor.forest', 'monitor_forest.log'); run_forest_nursery_monitor(logger)"; needsSelenium = $true },
    @{ name = 'PowerPlantProducer'; cmd = "from production_monitor import setup_logger; from main import run_power_plant_producer; logger = setup_logger('production_monitor.powerplant', 'monitor_powerplant.log'); run_power_plant_producer(logger)"; needsSelenium = $true },
    @{ name = 'OilRigMonitor'; cmd = "from production_monitor import setup_logger; from main import run_oil_rig_monitor; logger = setup_logger('production_monitor.oilrig', 'monitor_oilrig.log'); run_oil_rig_monitor(logger)"; needsSelenium = $true }
)

foreach ($jobDef in $jobDefinitions) {
    Write-Host "Running $($jobDef.name)"
    $jobs += Start-Job -ScriptBlock {
        param($projectPath, $cmd)
        Set-Location $projectPath
        python -c $cmd
    } -ArgumentList $projectPath, $jobDef.cmd
    Start-Sleep -Seconds 10
}

Write-Host "All jobs have been started. Please check log files in the record/ directory."

