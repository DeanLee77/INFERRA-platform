#!/usr/bin/env bash
set -euo pipefail

SECRETS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SECRETS_DIR}/.env.prod.local"

generate_secret() {
    local name="$1"
    local path="${SECRETS_DIR}/${name}.txt"
    if [ ! -f "$path" ]; then
        if command -v openssl >/dev/null 2>&1; then
            openssl rand -base64 32 | tr -d '\n' > "$path"
        else
            python -c "import secrets; print(secrets.token_urlsafe(32), end='')" > "$path"
        fi
        chmod 600 "$path"
        echo "[OK]   generated ${name}.txt"
    else
        echo "[SKIP] ${name}.txt already exists"
    fi
}

secret_value() {
    tr -d '\r\n' < "${SECRETS_DIR}/$1.txt"
}

generate_secret "inferra_api_key"
generate_secret "inferra_jwt_secret"
generate_secret "inferra_csrf_token"
generate_secret "redis_password"
generate_secret "postgres_password"
generate_secret "fuseki_admin_password"
generate_secret "grafana_admin_password"
generate_secret "zai_api_key"

cat > "$ENV_FILE" <<EOF
INFERRA_AUTH_ENABLED=true
INFERRA_API_KEY=$(secret_value inferra_api_key)
INFERRA_JWT_SECRET=$(secret_value inferra_jwt_secret)
INFERRA_CSRF_PROTECTION=false
INFERRA_CSRF_TOKEN=$(secret_value inferra_csrf_token)
POSTGRES_USER=inferra
POSTGRES_PASSWORD=$(secret_value postgres_password)
FUSEKI_USER=admin
FUSEKI_PASSWORD=$(secret_value fuseki_admin_password)
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=$(secret_value grafana_admin_password)
INFERRA_ABDUCTION_ADAPTER=z3
INFERRA_LLM_ABDUCTION_MAX_HYPOTHESES=5
ZAI_API_KEY=$(secret_value zai_api_key)
EOF

chmod 600 "$ENV_FILE"
echo "[OK]   wrote .env.prod.local"
echo "Start with:"
echo "  docker compose --env-file secrets/.env.prod.local -f docker-compose.yml -f docker-compose.prod.yml up -d"
