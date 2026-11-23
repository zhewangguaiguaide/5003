param([switch]$NoBrowser)

$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:PYTHONUNBUFFERED = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
foreach ($candidate in @('py', 'python3', 'python')) {
    foreach ($python in @(Get-Command $candidate -CommandType Application -ErrorAction SilentlyContinue)) {
        if ($python.Source -like '*\Microsoft\WindowsApps\*') { continue }
        $pythonArguments = @()
        if ($candidate -eq 'py') { $pythonArguments += '-3' }
        try {
            & $python.Source @pythonArguments -B -c 'import sys, sqlite3; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>$null
        } catch { continue }
        if ($LASTEXITCODE -ne 0) { continue }
        $pythonArguments += @('-B', '-u', (Join-Path $PSScriptRoot 'app.py'))
        if (-not $NoBrowser) { $pythonArguments += '--open' }
        Write-Host "Python: $($python.Source)"
        & $python.Source @pythonArguments
        exit $LASTEXITCODE
    }
}
throw 'No working Python 3.10+ with SQLite was found. Install Python and enable its launcher or PATH, then retry.'
