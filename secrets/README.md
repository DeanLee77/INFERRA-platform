# Local Production Secrets

This directory holds generated secret files for the local production Compose
overlay. Generated `*.txt` files and `.env.prod.local` are ignored by git.

Run one of:

```bash
bash secrets/init-secrets.sh
```

```powershell
powershell -ExecutionPolicy Bypass -File secrets/init-secrets.ps1
```

Then start the local production rehearsal stack with:

```bash
docker compose --env-file secrets/.env.prod.local -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Commercial deployment should replace these files with the deployment platform's
secret manager.

AXIOM and AEGIS must not read this directory through sibling-repository paths.
Each product backend/BFF receives its own least-privilege credentials from its
deployment environment or secret manager. The internal `inferra-core` package
reads no environment variables or secret files and must remain secret-free as
the rest of the engine moves; secret handling remains a Platform/application-
host responsibility.
