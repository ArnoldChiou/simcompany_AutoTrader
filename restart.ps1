param(
    [ValidateSet('All', 'AutoBuyer', 'PowerPlant', 'ConstructionMonitor')]
    [string]$Target = 'All',

    [int]$LegacyPowerPlantJobId = 0
)

$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $MyInvocation.MyCommand.Definition

function Resolve-PythonExecutable {
    $pythonRoot = Join-Path $env:LOCALAPPDATA 'Programs\Python'
    if (Test-Path -LiteralPath $pythonRoot) {
        $installedPython = Get-ChildItem -LiteralPath $pythonRoot -Filter python.exe -Recurse -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($installedPython) {
            return $installedPython.FullName
        }
    }

    # The current shell may expose an unrelated bundled Python first.  Prefer
    # the user's installed interpreter, where this project's dependencies live.
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        return $pythonCommand.Source
    }

    $runningPython = Get-Process -Name python -ErrorAction SilentlyContinue |
        Where-Object { $_.Path } |
        Select-Object -First 1
    if ($runningPython) {
        return $runningPython.Path
    }

    throw 'Python executable was not found. Install Python or add python.exe to PATH.'
}

$pythonPath = Resolve-PythonExecutable
Write-Host "Using Python: $pythonPath"
$recordPath = Join-Path $projectPath 'record'
$serviceRunnerPath = Join-Path $projectPath 'service_runner.py'
New-Item -ItemType Directory -Path $recordPath -Force | Out-Null

function Stop-ProjectProcess {
    param(
        [string]$Name,
        [string]$ServiceKey,
        [string]$LegacyMarker
    )

    # Clean up jobs created by older versions when this script is run in the
    # same PowerShell session.
    $existingJobs = Get-Job -Name $Name -ErrorAction SilentlyContinue
    foreach ($job in $existingJobs) {
        Write-Host "Stopping $Name (Job $($job.Id))..."
        Stop-Job -Job $job -ErrorAction SilentlyContinue
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
    }

    $pidPath = Join-Path $recordPath "$ServiceKey.pid"
    $stoppedIds = @()
    if (Test-Path -LiteralPath $pidPath) {
        $storedPid = 0
        $pidText = (Get-Content -Raw -LiteralPath $pidPath).Trim()
        if ([int]::TryParse($pidText, [ref]$storedPid)) {
            $managedProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $storedPid" -ErrorAction SilentlyContinue
            if ($managedProcess -and $managedProcess.CommandLine -like '*service_runner.py*') {
                Write-Host "Stopping $Name process tree (PID $storedPid)..."
                # Selenium launches Chrome and ChromeDriver as children.  Stop
                # the complete tree so a stale Chrome process cannot lock the
                # profile during the next launch.
                & taskkill.exe /PID $storedPid /T /F | Out-Null
                Wait-Process -Id $storedPid -Timeout 15 -ErrorAction SilentlyContinue
                $stoppedIds += $storedPid
            } elseif ($managedProcess) {
                Write-Warning "PID $storedPid no longer belongs to $Name; it was not stopped."
            }
        }
        Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
    }

    # Find processes created by the previous Start-Job based launcher so the
    # first restart after this upgrade cannot create duplicates.
    $legacyProcesses = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*$LegacyMarker*" -and $_.ProcessId -notin $stoppedIds }
    foreach ($legacyProcess in $legacyProcesses) {
        Write-Host "Stopping legacy $Name process tree (PID $($legacyProcess.ProcessId))..."
        & taskkill.exe /PID $legacyProcess.ProcessId /T /F | Out-Null
        Wait-Process -Id $legacyProcess.ProcessId -Timeout 15 -ErrorAction SilentlyContinue
    }
}

function Start-ProjectProcess {
    param(
        [string]$Name,
        [string]$ServiceKey,
        [string]$PythonExecutable = $pythonPath
    )

    Write-Host "Starting $Name..."
    $stdoutPath = Join-Path $recordPath "$ServiceKey.stdout.log"
    $stderrPath = Join-Path $recordPath "$ServiceKey.stderr.log"
    $pidPath = Join-Path $recordPath "$ServiceKey.pid"
    $arguments = @('-u', "`"$serviceRunnerPath`"", $ServiceKey)
    $startParameters = @{
        FilePath = $PythonExecutable
        ArgumentList = $arguments
        WorkingDirectory = $projectPath
        WindowStyle = 'Hidden'
        RedirectStandardOutput = $stdoutPath
        RedirectStandardError = $stderrPath
        PassThru = $true
    }
    $serviceProcess = Start-Process @startParameters
    Set-Content -LiteralPath $pidPath -Value $serviceProcess.Id -Encoding ascii
    Start-Sleep -Seconds 1
    if ($serviceProcess.HasExited) {
        Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
        throw "$Name failed to start. Check $stderrPath"
    }
    Write-Host "$Name started as independent process PID $($serviceProcess.Id)."
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
    Stop-ProjectProcess -Name 'AutoBuyer' -ServiceKey 'autobuyer' -LegacyMarker 'run_auto_buyer'
    Start-ProjectProcess -Name 'AutoBuyer' -ServiceKey 'autobuyer'
}

if ($Target -in @('All', 'PowerPlant')) {
    Stop-ProjectProcess -Name 'PowerPlantProducer' -ServiceKey 'powerplant' -LegacyMarker 'run_power_plant_producer'
    Start-ProjectProcess -Name 'PowerPlantProducer' -ServiceKey 'powerplant'
}

if ($Target -in @('All', 'ConstructionMonitor')) {
    Stop-ProjectProcess -Name 'ConstructionMonitor' -ServiceKey 'construction' -LegacyMarker 'run_building_construction_monitor'
    Start-ProjectProcess -Name 'ConstructionMonitor' -ServiceKey 'construction'
}

Write-Host "`nThe selected service is detached from this PowerShell session and will keep running after the window closes."
