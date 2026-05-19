param(
    [string]$BaseUrl = "http://localhost:8000",

    [int]$RecoveryTimeoutSeconds = 90,

    [int]$PollIntervalSeconds = 5
)

$ErrorActionPreference = "Stop"

$script = Join-Path $PSScriptRoot "docker_chaos_smoke.ps1"
$services = @("redis", "fuseki", "worker")

foreach ($service in $services) {
    Write-Host "Restart chaos drill: $service"
    & $script `
        -Service $service `
        -Action restart `
        -BaseUrl $BaseUrl `
        -RecoveryTimeoutSeconds $RecoveryTimeoutSeconds `
        -PollIntervalSeconds $PollIntervalSeconds
}

Write-Host "Phase 4 chaos suite completed."
