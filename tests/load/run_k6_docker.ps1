param(
    [string]$BaseUrl = "http://host.docker.internal:8000",
    [int]$Vus = 20,
    [string]$Duration = "1m",
    [string]$Script = "k6_api_smoke.js",
    [int]$MetricsRate = 4,
    [int]$LiveRate = 12,
    [int]$UserSleepSeconds = 3,
    [string]$Profile = "",
    [string]$Network = "",
    [string]$Image = "grafana/k6:0.51.0"
)

$ErrorActionPreference = "Stop"
$LoadDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptPath = Join-Path $LoadDir $Script
if (-not (Test-Path -LiteralPath $ScriptPath)) {
    throw "k6 script not found: $ScriptPath"
}

Write-Host "Running k6 load smoke through Docker."
Write-Host "BaseUrl: $BaseUrl"
Write-Host "VUs: $Vus"
Write-Host "Duration: $Duration"
Write-Host "Script: $Script"
if ($Profile) {
    Write-Host "Profile: $Profile"
}
if ($Network) {
    Write-Host "Network: $Network"
}
Write-Host "Image: $Image"

$DockerArgs = @(
    "run",
    "--rm",
    "-e", "BASE_URL=$BaseUrl",
    "-e", "VUS=$Vus",
    "-e", "DURATION=$Duration",
    "-e", "METRICS_RATE=$MetricsRate",
    "-e", "LIVE_RATE=$LiveRate",
    "-e", "USER_SLEEP_SECONDS=$UserSleepSeconds",
    "-v", "${LoadDir}:/scripts:ro"
)

if ($Profile) {
    $DockerArgs += @("-e", "PROFILE=$Profile")
}

if ($Network) {
    $DockerArgs += @("--network", $Network)
}

$DockerArgs += @($Image, "run", "/scripts/$Script")

docker @DockerArgs

if ($LASTEXITCODE -ne 0) {
    throw "Dockerized k6 smoke failed with exit code $LASTEXITCODE"
}
