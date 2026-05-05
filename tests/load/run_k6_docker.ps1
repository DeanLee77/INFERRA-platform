param(
    [string]$BaseUrl = "http://host.docker.internal:8000",
    [int]$Vus = 20,
    [string]$Duration = "1m",
    [string]$Image = "grafana/k6:0.51.0"
)

$ErrorActionPreference = "Stop"
$LoadDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Running k6 load smoke through Docker."
Write-Host "BaseUrl: $BaseUrl"
Write-Host "VUs: $Vus"
Write-Host "Duration: $Duration"
Write-Host "Image: $Image"

docker run `
    --rm `
    -e BASE_URL=$BaseUrl `
    -e VUS=$Vus `
    -e DURATION=$Duration `
    -v "${LoadDir}:/scripts:ro" `
    $Image `
    run /scripts/k6_api_smoke.js

if ($LASTEXITCODE -ne 0) {
    throw "Dockerized k6 smoke failed with exit code $LASTEXITCODE"
}
