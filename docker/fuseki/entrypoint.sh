#!/usr/bin/env sh
set -eu

read_secret_file() {
    path="$1"
    if [ -n "$path" ] && [ -s "$path" ]; then
        tr -d '\r\n' < "$path"
    fi
}

if [ -n "${FUSEKI_ADMIN_PASSWORD_FILE:-}" ]; then
    ADMIN_PASSWORD="$(read_secret_file "$FUSEKI_ADMIN_PASSWORD_FILE")"
elif [ -n "${FUSEKI_PASSWORD_FILE:-}" ]; then
    ADMIN_PASSWORD="$(read_secret_file "$FUSEKI_PASSWORD_FILE")"
elif [ -z "${ADMIN_PASSWORD:-}" ]; then
    ADMIN_PASSWORD="${FUSEKI_PASSWORD:-admin}"
fi

if [ -n "${FUSEKI_READ_PASSWORD_FILE:-}" ]; then
    FUSEKI_READ_PASSWORD="$(read_secret_file "$FUSEKI_READ_PASSWORD_FILE")"
elif [ -z "${FUSEKI_READ_PASSWORD:-}" ]; then
    FUSEKI_READ_PASSWORD="inferra_read"
fi

export ADMIN_PASSWORD
export FUSEKI_READ_USER="${FUSEKI_READ_USER:-inferra_reader}"
export FUSEKI_READ_PASSWORD

mkdir -p "$FUSEKI_BASE"
envsubst '${ADMIN_PASSWORD} ${FUSEKI_READ_USER} ${FUSEKI_READ_PASSWORD}' \
    < /inferra-fuseki/shiro.ini.template \
    > "$FUSEKI_BASE/shiro.ini"

if [ "$#" -eq 0 ]; then
    set -- /jena-fuseki/fuseki-server
fi

"$@" &
server_pid="$!"

terminate() {
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
}

trap terminate INT TERM

echo "Waiting for Fuseki to finish starting up..."
until curl --output /dev/null --silent --fail -u "admin:${ADMIN_PASSWORD}" 'http://localhost:3030/$/status'; do
    if ! kill -0 "$server_pid" 2>/dev/null; then
        wait "$server_pid"
    fi
    sleep 1s
done

if [ "${TDB:-}" = "2" ]; then
    tdb_version="tdb2"
else
    tdb_version="tdb"
fi

for env_var in $(env | grep '^FUSEKI_DATASET_' || true); do
    dataset="${env_var#*=}"
    echo "Creating dataset $dataset"
    curl --output /dev/null --silent --show-error \
        -u "admin:${ADMIN_PASSWORD}" \
        -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
        --data "dbName=${dataset}&dbType=${tdb_version}" \
        'http://localhost:3030/$/datasets' || true
done

echo "Fuseki is available :-)"
unset ADMIN_PASSWORD

wait "$server_pid"
