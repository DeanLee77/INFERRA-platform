param(
    [string]$BaseUrl = "http://api:8000",
    [int]$Vus = 500,
    [string]$Duration = "1m",
    [int]$MetricsRate = 4,
    [int]$LiveRate = 12,
    [int]$UserSleepSeconds = 3,
    [string]$Network = "inferra_default",
    [string]$Image = "grafana/k6:0.51.0"
)

$ErrorActionPreference = "Stop"
$Runner = Join-Path $PSScriptRoot "run_k6_docker.ps1"

& $Runner `
    -BaseUrl $BaseUrl `
    -Vus $Vus `
    -Duration $Duration `
    -MetricsRate $MetricsRate `
    -LiveRate $LiveRate `
    -UserSleepSeconds $UserSleepSeconds `
    -Network $Network `
    -Script "k6_production_gate.js" `
    -Image $Image

if ($LASTEXITCODE -ne 0) {
    throw "Dockerized k6 production gate failed with exit code $LASTEXITCODE"
}
