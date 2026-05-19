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

