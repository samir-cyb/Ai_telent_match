$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Run-Step {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Setup step failed: $Executable $Arguments" }
}
if (!(Test-Path '.venv\Scripts\python.exe')) {
    Run-Step 'py' @('-3.12', '-m', 'venv', '.venv')
}
$Python = Join-Path (Get-Location) '.venv\Scripts\python.exe'
Run-Step $Python @('-m', 'pip', 'install', '-r', 'requirements.txt')
Run-Step $Python @('scripts/init_env.py')
Run-Step $Python @('manage.py', 'migrate')
Run-Step $Python @('manage.py', 'check_setup')
Write-Host 'Ready. Start with .\.venv\Scripts\python.exe manage.py runserver'
