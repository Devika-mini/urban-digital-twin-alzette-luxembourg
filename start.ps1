<#
.SYNOPSIS
  One command to the running Alzette digital twin, from PowerShell on Windows.

.DESCRIPTION
  Runs start.sh, with the same commands and options, through the bash that comes with Git for
  Windows (the clone itself needs Git). There is a single implementation, so both entry points
  always behave the same:

    .\start.ps1                  check, generate what is missing or outdated, build, start, wait until healthy
    .\start.ps1 --force          regenerate everything derived from the data folder, then start
    .\start.ps1 --no-generate    skip the generation, start straight away
    .\start.ps1 stop             stop the twin (the database is kept)
    .\start.ps1 logs [service]   follow the logs
    .\start.ps1 status           list the services and their health
    .\start.ps1 reset [--volumes] [--yes]
                                 delete the generated files (never data\ or .env)
    .\start.ps1 help

  If PowerShell refuses to run scripts, run it as:
    powershell -ExecutionPolicy Bypass -File .\start.ps1
#>

$ErrorActionPreference = "Stop"

function Find-GitBash {
    # Git for Windows' bash: never C:\Windows\System32\bash.exe, which is WSL's (another Docker context).
    $candidates = @()
    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($git) {
        # ...\Git\cmd\git.exe or ...\Git\mingw64\bin\git.exe -> ...\Git\bin\bash.exe
        $dir = Split-Path $git.Source
        while ($dir -and -not (Test-Path (Join-Path $dir "bin\bash.exe"))) {
            $parent = Split-Path $dir
            if ($parent -eq $dir) { $dir = $null } else { $dir = $parent }
        }
        if ($dir) { $candidates += (Join-Path $dir "bin\bash.exe") }
    }
    $candidates += @(
        "$env:ProgramFiles\Git\bin\bash.exe",
        "${env:ProgramFiles(x86)}\Git\bin\bash.exe",
        "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe"
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) { return $candidate }
    }
    return $null
}

$bash = Find-GitBash
if (-not $bash) {
    Write-Host "Error: Git for Windows' bash was not found." -ForegroundColor Red
    Write-Host "  start.ps1 runs start.sh with it. Install Git for Windows (https://git-scm.com/download/win)"
    Write-Host "  and run this again, or run ./start.sh from Git Bash."
    exit 1
}

# Forward slashes: bash's dirname does not split C:\... paths.
$script = (Join-Path $PSScriptRoot "start.sh") -replace '\\', '/'
& $bash $script @args
exit $LASTEXITCODE
