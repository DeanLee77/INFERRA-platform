param(
    [ValidateSet("smoke", "load", "stress", "spike", "soak", "all")]
    [string]$Profile = "smoke",
    [string]$BaseUrl = "http://api:8000",
    [int]$Vus = 50,
    [string]$Duration = "3m",
    [string]$Network = "inferra_default",
    [string]$Image = "grafana/k6:0.51.0"
)

$ErrorActionPreference = "Stop"
$Runner = Join-Path $PSScriptRoot "run_k6_docker.ps1"
$Profiles = if ($Profile -eq "all") {
    @("smoke", "load", "stress", "spike", "soak")
} else {
    @($Profile)
}

foreach ($current in $Profiles) {
    & $Runner `
        -BaseUrl $BaseUrl `
        -Vus $Vus `
        -Duration $Duration `
        -Network $Network `
        -Script "k6_profiles.js" `
        -Profile $current `
        -Image $Image

    if ($LASTEXITCODE -ne 0) {
        throw "Dockerized k6 $current profile failed with exit code $LASTEXITCODE"
    }
}

