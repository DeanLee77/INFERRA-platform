# Inferra Explorer + Fuseki Docker Deployment

> **Development-only topology — reviewed 2026-07-17.** This direct Explorer to
> Fuseki setup is an operator/developer inspection tool, not the AXIOM/AEGIS or
> Core production trust boundary. In the accepted architecture, PostgreSQL
> audit/outbox records are authoritative, Fuseki is a rebuildable derived
> PROV-O/ontology projection, and production UIs use read-only Platform APIs
> rather than direct SPARQL administration. Default credentials below are never
> valid for production.

This deployment runs **Graph Explorer** (AWS Neptune/Graph Explorer fork) wired to a local **Apache Jena Fuseki** instance.

## Architecture

```
┌─────────────────┐     ┌──────────────┐
│   Browser       │────▶│  Explorer    │
│  localhost:8080 │     │  (port 80)   │
└─────────────────┘     └──────┬───────┘
                               │
                               │ HTTP
                               │ (Docker network)
                               ▼
                        ┌──────────────┐
                        │    Fuseki    │
                        │  (port 3030) │
                        │  /inferra    │
                        └──────────────┘
```

## Quick Start

### Deploy Explorer + Fuseki

```bash
cd inferra-platform
docker compose -f docker-compose-explorer.yml up -d --build
```

### Check Services

```bash
docker compose -f docker-compose-explorer.yml ps
```

### Access Services

| Service      | URL                        | Credentials        |
|--------------|----------------------------|--------------------|
| **Explorer** | http://localhost:8080      | None (dev mode)    |
| **Fuseki**   | http://localhost:3030      | admin / admin      |

### View Logs

```bash
# All services
docker compose -f docker-compose-explorer.yml logs -f

# Explorer only
docker compose -f docker-compose-explorer.yml logs -f explorer

# Fuseki only
docker compose -f docker-compose-explorer.yml logs -f fuseki
```

### Stop Services

```bash
docker compose -f docker-compose-explorer.yml down
```

### Stop and Remove Volumes (clear all data)

```bash
docker compose -f docker-compose-explorer.yml down -v
```

## Configuration

### Explorer Configuration

The explorer is configured via:
- `explorer-config/config.json` - Main configuration mounted into the explorer container at runtime
- `explorer-config/defaultConnection.json` - Reference default connection settings generated from the same values for the UI

Key configuration values:
- `GRAPH_CONNECTION_URL`: `http://fuseki:3030/inferra` - Internal Docker network URL to Fuseki
- `PUBLIC_OR_PROXY_ENDPOINT`: `http://localhost:8080` - Public URL for the explorer
- `GRAPH_TYPE`: `sparql` - SPARQL endpoint
- `SERVICE_TYPE`: `fuseki` - Fuseki service type

### Fuseki Configuration

- **Dataset name**: `inferra`
- **Admin password**: `admin`
- **Persistence**: Data stored in `fuseki-data` volume

## Loading Data into Fuseki

### Via Fuseki UI
1. Open http://localhost:3030
2. Login with admin/admin
3. Select the `inferra` dataset
4. Use the "Upload" tab to load RDF files (TTL, N-Triples, etc.)

### Via curl

```bash
# Upload a Turtle file
curl -X POST \
  -H "Content-Type: text/turtle" \
  -T your-data.ttl \
  -u admin:admin \
  "http://localhost:3030/inferra/data"

# Upload N-Triples
curl -X POST \
  -H "Content-Type: application/n-triples" \
  -T your-data.nt \
  -u admin:admin \
  "http://localhost:3030/inferra/data"

# SPARQL UPDATE
curl -X POST \
  -H "Content-Type: application/sparql-update" \
  -u admin:admin \
  --data "INSERT DATA { <http://example.org/s> <http://example.org/p> <http://example.org/o> }" \
  "http://localhost:3030/inferra/update"
```

### Via SPARQL Endpoint

```bash
# Query the dataset
curl -X POST \
  -H "Accept: application/sparql-results+json" \
  -u admin:admin \
  --data "query=SELECT * WHERE { ?s ?p ?o } LIMIT 10" \
  "http://localhost:3030/inferra/query"
```

## Troubleshooting

### Explorer won't start
```bash
# Check if Fuseki is healthy
docker compose -f docker-compose-explorer.yml ps

# Check explorer logs
docker compose -f docker-compose-explorer.yml logs explorer
```

### Can't connect to Fuseki from explorer
- Ensure Fuseki is running: `docker compose -f docker-compose-explorer.yml ps fuseki`
- Check Fuseki logs: `docker compose -f docker-compose-explorer.yml logs fuseki`
- Verify dataset exists: Open http://localhost:3030 and check for `inferra` dataset

### Port conflicts
If ports 3030 or 8080 are in use, modify the port mappings in `docker-compose-explorer.yml`:
```yaml
ports:
  - "127.0.0.1:3031:3030"  # Fuseki on 3031
  - "127.0.0.1:8081:80"    # Explorer on 8081
```

## Integration with Full Inferra Stack

To run Explorer + Fuseki alongside the full Inferra platform:

1. Stop the standalone Fuseki if running
2. Start the platform with `docker compose up -d --build`
3. Start the optional explorer profile with `docker compose --profile explorer up -d --build explorer`

## Security Notes

⚠️ **Development Only**: This configuration uses:
- Default passwords (admin/admin)
- HTTP only (no HTTPS)
- Localhost binding only

For production deployments:
- Use `docker-compose.prod.yml` approach with secrets
- Enable HTTPS
- Use strong credentials
- Configure proper network policies
