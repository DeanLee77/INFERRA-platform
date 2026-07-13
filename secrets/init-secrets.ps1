param()

$ErrorActionPreference = "Stop"
$SecretsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path $SecretsDir ".env.prod.local"

function New-SecretValue {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    } finally {
        $rng.Dispose()
    }
    return [Convert]::ToBase64String($bytes)
}

function New-SecretFile {
    param([string]$Name)
    $path = Join-Path $SecretsDir "$Name.txt"
    if ((Test-Path -LiteralPath $path) -and ((Get-Content -LiteralPath $path -Raw).Trim().Length -gt 0)) {
        Write-Host "[SKIP] $Name.txt already exists"
        return
    }
    New-SecretValue | Set-Content -LiteralPath $path -NoNewline -Encoding ascii
    Write-Host "[OK]   generated $Name.txt"
}

function New-FernetKeyFile {
    param([string]$Name)
    $path = Join-Path $SecretsDir "$Name.txt"
    if ((Test-Path -LiteralPath $path) -and ((Get-Content -LiteralPath $path -Raw).Trim().Length -gt 0)) {
        Write-Host "[SKIP] $Name.txt already exists"
        return
    }
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    } finally {
        $rng.Dispose()
    }
    $key = [Convert]::ToBase64String($bytes).Replace("+", "-").Replace("/", "_")
    $key | Set-Content -LiteralPath $path -NoNewline -Encoding ascii
    Write-Host "[OK]   generated $Name.txt"
}

function Get-SecretValue {
    param([string]$Name)
    return (Get-Content -LiteralPath (Join-Path $SecretsDir "$Name.txt") -Raw).Trim()
}

New-SecretFile "inferra_api_key"
New-SecretFile "inferra_jwt_secret"
New-SecretFile "inferra_csrf_token"
New-SecretFile "redis_password"
New-SecretFile "postgres_password"
New-SecretFile "fuseki_admin_password"
New-SecretFile "fuseki_read_password"
New-SecretFile "grafana_admin_password"
New-SecretFile "zai_api_key"
New-FernetKeyFile "aegis_llm_api_key_encryption_key"

$envContent = @"
INFERRA_AUTH_ENABLED=true
INFERRA_API_KEY=$(Get-SecretValue "inferra_api_key")
INFERRA_API_KEY_SCOPES=read,llm:read,llm:write
INFERRA_JWT_SECRET=$(Get-SecretValue "inferra_jwt_secret")
INFERRA_CSRF_PROTECTION=false
INFERRA_CSRF_TOKEN=$(Get-SecretValue "inferra_csrf_token")
INFERRA_CORS_ALLOWED_ORIGINS=
INFERRA_CORS_ALLOW_CREDENTIALS=false
POSTGRES_USER=inferra
POSTGRES_PASSWORD=$(Get-SecretValue "postgres_password")
FUSEKI_USER=admin
FUSEKI_PASSWORD=$(Get-SecretValue "fuseki_admin_password")
FUSEKI_READ_USER=inferra_reader
FUSEKI_READ_PASSWORD=$(Get-SecretValue "fuseki_read_password")
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=$(Get-SecretValue "grafana_admin_password")
INFERRA_ABDUCTION_ADAPTER=z3
INFERRA_LLM_ABDUCTION_MAX_HYPOTHESES=5
ZAI_API_KEY=$(Get-SecretValue "zai_api_key")
AEGIS_LLM_API_KEY_ENCRYPTION_KEY=$(Get-SecretValue "aegis_llm_api_key_encryption_key")
"@

$envContent | Set-Content -LiteralPath $EnvFile -NoNewline -Encoding ascii
Write-Host "[OK]   wrote .env.prod.local"
Write-Host "Start with:"
Write-Host "  docker compose --env-file secrets/.env.prod.local -f docker-compose.yml -f docker-compose.prod.yml up -d"
