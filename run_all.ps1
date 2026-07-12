# run_all.ps1
# Run only the two currently used services: AutoBuyer and PowerPlantProducer.

# Kill any leftover Chrome or Chromedriver processes before starting
Get-Process -Name chrome, chromedriver -ErrorAction SilentlyContinue | ForEach-Object { try { $_.Kill() } catch {} }

$projectPath = Split-Path -Parent $MyInvocation.MyCommand.Definition

# Define Wait-For-SeleniumFree function
function Wait-For-SeleniumFree {
    while (Get-Process -Name chrome, chromedriver -ErrorAction SilentlyContinue) {
        Write-Host "Selenium/Chrome is still running, waiting 10 seconds..."
        Start-Sleep -Seconds 10
    }
}

# Use Start-Job to execute all functions sequentially to avoid conflicts caused by multiple Selenium instances running simultaneously
$jobs = @()

# Define the jobs and their python commands
$jobDefinitions = @(
    @{ name = 'AutoBuyer'; cmd = "from main import run_auto_buyer; run_auto_buyer()"; needsSelenium = $true },
    @{ name = 'PowerPlantProducer'; cmd = "from production_monitor import setup_logger; from main import run_power_plant_producer; logger = setup_logger('production_monitor.powerplant', 'monitor_powerplant.log'); run_power_plant_producer(logger)"; needsSelenium = $true }
)

foreach ($jobDef in $jobDefinitions) {
    Write-Host "Running $($jobDef.name)"
    $canStart = $true
    if ($jobDef.needsSelenium) {
        $maxTries = 5
        for ($try = 1; $try -le $maxTries; $try++) {
            if (Get-Process -Name chrome, chromedriver -ErrorAction SilentlyContinue) {
                for ($sec = 1; $sec -le 20; $sec++) {
                    Write-Host "Selenium/Chrome is still running, waiting ($sec/20) seconds before starting $($jobDef.name)... (try $try/$maxTries)"
                    Start-Sleep -Seconds 1
                }
                $canStart = $false
            } else {
                $canStart = $true
                break
            }
        }
    }
    if ($canStart) {
        $jobs += Start-Job -Name $jobDef.name -ScriptBlock {
            param($projectPath, $cmd)
            Set-Location $projectPath
            python -u -c $cmd
        } -ArgumentList $projectPath, $jobDef.cmd
        Start-Sleep -Seconds 10
    } else {
        Write-Host "$($jobDef.name) skipped because Selenium/Chrome is still running after $maxTries checks."
    }
}

Write-Host "All jobs have been started. Please check log files in the record/ directory."
$jobs | Select-Object Id, Name, State | Format-Table -AutoSize

