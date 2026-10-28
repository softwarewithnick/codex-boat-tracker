param([switch]$Fullscreen, [switch]$Headless, [int]$Frames = 0, [string]$Screenshot = "")
$ErrorActionPreference = 'Stop'
$projectDir = $PSScriptRoot
$projectPython = Join-Path $projectDir '.venv\Scripts\python.exe'
$keyPath = Join-Path $projectDir '.local\aisstream-key.dpapi'
$previousKey = $env:AISSTREAM_API_KEY
try {
    if (-not $env:AISSTREAM_API_KEY) {
        if (Test-Path -LiteralPath $keyPath) {
            $secureKey = (Get-Content -LiteralPath $keyPath -Raw).Trim() | ConvertTo-SecureString
        } else {
            $secureKey = Read-Host 'AISstream API key' -AsSecureString
        }
        $env:AISSTREAM_API_KEY = [System.Net.NetworkCredential]::new('', $secureKey).Password
    }
    if (Test-Path -LiteralPath $projectPython) {
        $python = $projectPython
    } else {
        $python = (Get-Command python -ErrorAction Stop).Source
    }
    $appArguments = @((Join-Path $projectDir 'main.py'), '--live')
    if ($Fullscreen) { $appArguments += '--fullscreen' }
    if ($Headless) { $appArguments += '--headless' }
    if ($Frames -gt 0) { $appArguments += @('--frames', $Frames) }
    if ($Screenshot) { $appArguments += @('--screenshot', $Screenshot) }
    & $python @appArguments
    if ($LASTEXITCODE -ne 0) { throw "Boat tracker exited with code $LASTEXITCODE." }
} finally {
    if ($null -eq $previousKey) {
        Remove-Item Env:\AISSTREAM_API_KEY -ErrorAction SilentlyContinue
    } else {
        $env:AISSTREAM_API_KEY = $previousKey
    }
}



