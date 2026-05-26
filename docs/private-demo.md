# AXIOM/AEGIS Private Demo Runbook And Smoke Evidence

Internal-only runbook for [INFA-61](/INFA/issues/INFA-61), under the private-readiness gate in [INFA-40](/INFA/issues/INFA-40#document-plan).

This path uses sanitized synthetic fixture data only. It does not use PHI, customer data, production integrations, real payer policy, external infrastructure, public URLs, sales claims, compliance claims, or autonomous workflow execution.

## Readiness Verdict

Combined local smoke verdict: PASS against the Dockerized INFERRA Platform API.

- Checked at: `2026-05-26T04:08:10Z` (`2026-05-26 14:08` Australia/Sydney).
- Docker service evidence: `demo_artifacts/infa72-docker-20260526/docker-services.txt`.
- Docker API health evidence: `demo_artifacts/infa72-docker-20260526/api-health.json`.
- Platform route smoke evidence: `demo_artifacts/infa72-docker-20260526/synthetic-receipt-routes.json`.
- Browser smoke evidence: `demo_artifacts/infa72-docker-20260526/axiom-private-demo-browser-smoke.json`.
- Browser screenshots: `demo_artifacts/infa72-docker-20260526/axiom-private-demo-desktop.png`, `demo_artifacts/infa72-docker-20260526/axiom-private-demo-mobile.png`.
- Sanitization fields were false for PHI, customer data, secrets, real payer policy, and production integration across all platform receipt cases.
- No severe browser console errors were captured in the AXIOM desktop/mobile browser smoke.

The reproducible QA preview path is:

- Platform: `http://127.0.0.1:8000`
- AXIOM: `http://127.0.0.1:3001/private-demo`
- AEGIS: `http://127.0.0.1:4179/private-demo`

AXIOM defaults to port `3000`, but port `3000` was already occupied in this harness. The verified preview command below uses `3001` so QA can reproduce the smoke without disturbing the existing local service.

## Repositories And Branches

Workspace layout:

- `INFERRA-platform`: `_default`, repo `DeanLee77/INFERRA-platform`, branch `main`
- `INFERRA-axiom`: `../INFERRA-axiom`, repo `DeanLee77/INFERRA-axiom`, branch `main`
- `INFERRA-aegis`: `../INFERRA-aegis`, repo `DeanLee77/INFERRA-aegis`, branch `feature/inferra_aegis`

Runtime dependencies:

- Platform: Dockerized INFERRA Platform API stack on `127.0.0.1:8000`.
- AXIOM: Node/npm.
- AEGIS: Bun.
- Browser smoke: Playwright Chromium from the AEGIS dev dependency tree.

## Fixtures And Sample Data

Platform fixtures:

- Rule fixture: `project/demo/fixtures/synthetic_dmepos_power_mobility_rule.txt`
- Case fixture: `project/demo/fixtures/synthetic_decision_cases.json`
- Rule route: `GET http://127.0.0.1:8000/service/rule/syntheticDecisionReceiptFixture`
- Receipt route: `GET http://127.0.0.1:8000/service/inference/syntheticDecisionReceipt?caseId=<case-id>`

Synthetic case ids:

- `certify-ready`: expected `CERTIFY`, no missing evidence prompts.
- `review-missing-order`: expected `REVIEW`, one missing synthetic supplier-order evidence prompt.
- `deny-contraindication`: expected `DENY`, no missing evidence prompts.

Generated platform evidence:

- `demo_artifacts/synthetic-decision-receipt-certify-ready.json`
- `demo_artifacts/synthetic-decision-receipt-review-missing-order.json`
- `demo_artifacts/synthetic-decision-receipt-deny-contraindication.json`
- `demo_artifacts/smoke-certify-ready.json`
- `demo_artifacts/smoke-review-missing-order.json`
- `demo_artifacts/smoke-deny-contraindication.json`

AEGIS fixture:

- `../INFERRA-aegis/src/lib/data/fixtures/axiom-synthetic-receipt.json`
- Fixture id: `axiom-dmepos-power-mobility-review-v1`
- Expected AEGIS gate: `ESCALATE`
- Expected control decision: hold external release and route to human documentation review.

## Platform Start

Default QA path uses the Dockerized INFERRA Platform stack from `C:\Users\user\.pi\projects\inferra-platform`:

```powershell
docker compose up -d api
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/health" | ConvertTo-Json -Depth 10
```

Expected health shape:

```powershell
status: ok
version: 2.0.0
components.database: ok
components.redis: ok
components.celery: ok
components.fuseki: ok
```

The old Flask compatibility process on port `5000` is not required for the private-demo smoke. If the Docker API image was rebuilt locally, restart only the API service:

```powershell
docker compose up -d --build api
```

Do not use the legacy Flask process for AXIOM `/private-demo` validation unless explicitly testing backwards compatibility.

## AXIOM Start

From `../INFERRA-axiom`:

```powershell
npm install
npm run build
npm run preview:private-demo -- --port 3001
```

Open `http://127.0.0.1:3001/private-demo`.

If port `3000` is free and QA wants the default dev path instead:

```powershell
$env:BROWSER = "none"
$env:HOST = "127.0.0.1"
$env:PORT = "3000"
npm start
```

Open `http://127.0.0.1:3000/private-demo`.

## AEGIS Start

From `../INFERRA-aegis`:

```powershell
bun install
bun run check
bun run test
bun run build
$env:PORT = "4179"
bun server.js
```

Open `http://127.0.0.1:4179/private-demo`.

## Combined Smoke Checklist

1. Start the Dockerized platform API on port `8000`.
2. Confirm the platform fixture route returns `synthetic_dmepos_power_mobility_rule`.
3. Confirm these platform receipt routes return expected outcomes:
   - `certify-ready` -> `CERTIFY`
   - `review-missing-order` -> `REVIEW`
   - `deny-contraindication` -> `DENY`
4. Start AXIOM preview on port `3001`.
5. Open AXIOM `/private-demo`, select `REVIEW`, and confirm the missing-evidence prompt says `Attach complete synthetic supplier order packet.`
6. Start AEGIS static server on port `4179`.
7. Open AEGIS `/private-demo` and confirm:
   - `AXIOM receipt through AEGIS gate`
   - `axiom-dmepos-power-mobility-review-v1`
   - `Ledger-style receipt summary`
   - AEGIS gate/control result is `ESCALATE` for the offline AXIOM receipt fixture.
8. Confirm browser console has no severe errors.
9. Confirm logs and artifacts contain no PHI, customer data, secrets, real payer policy, production integration, or public/sales claims.

Platform route smoke command:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/service/rule/syntheticDecisionReceiptFixture" | ConvertTo-Json -Depth 10
Invoke-RestMethod "http://127.0.0.1:8000/service/inference/syntheticDecisionReceipt?caseId=certify-ready" | ConvertTo-Json -Depth 10
Invoke-RestMethod "http://127.0.0.1:8000/service/inference/syntheticDecisionReceipt?caseId=review-missing-order" | ConvertTo-Json -Depth 10
Invoke-RestMethod "http://127.0.0.1:8000/service/inference/syntheticDecisionReceipt?caseId=deny-contraindication" | ConvertTo-Json -Depth 10
```

Receipt generation command:

```powershell
python scripts/generate_synthetic_receipt.py --case review-missing-order --output demo_artifacts/smoke-review-missing-order.json
```

## Verification Run

Passed:

- `.venv\Scripts\python.exe -m pytest tests\adapters\inbound\http\routes\test_private_demo_router.py` in Docker API source: `3 passed`.
- Dockerized platform health on `127.0.0.1:8000/api/v1/health` returned `status: ok`.
- Dockerized platform synthetic routes on `127.0.0.1:8000` returned expected `CERTIFY`, `REVIEW`, and `DENY` outcomes.
- `npm run build` in AXIOM passed with existing lint warnings.
- AXIOM desktop/mobile browser smoke requested only `127.0.0.1:8000` platform synthetic routes and made no `127.0.0.1:5000` requests.
- `bun run check` in AEGIS passed with `0 errors and 0 warnings`.
- `bun run test` in AEGIS passed with `1` file and `3` tests.
- `bun run build` in AEGIS passed with existing plugin-timing and chunk-size warnings.
- Browser smoke passed across AXIOM desktop and mobile preview with no severe console errors.

Recorded non-blocking failures or gaps:

- `npm test -- --watchAll=false --runTestsByPath src/App.test.js` in AXIOM exited with `No tests found`; the verified AXIOM checks for this issue are build plus browser smoke.
- AXIOM port `3000` was already occupied in this harness; verified preview used port `3001`.
- Existing AXIOM lint warnings and Sass deprecation warnings remain outside this private-demo slice.
- Existing AEGIS build warnings about plugin timing and large chunks remain outside this private-demo slice.

## Stop

Stop foreground servers with `Ctrl+C` in each terminal.

If a process was started in the background, stop the specific owning process for the port:

```powershell
Get-NetTCPConnection -LocalPort 8000,3001,4179 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,State,OwningProcess
Stop-Process -Id <owning-process-id>
```

Do not stop unrelated services on port `3000`; it was occupied before this smoke.

## Reset

Platform:

```powershell
Remove-Item -Recurse -Force demo_artifacts -ErrorAction SilentlyContinue
Push-Location C:\Users\user\.pi\projects\inferra-platform
docker compose restart api
Pop-Location
```

AXIOM:

```powershell
Remove-Item -Recurse -Force build -ErrorAction SilentlyContinue
```

AEGIS:

```powershell
Remove-Item -Recurse -Force build,.svelte-kit -ErrorAction SilentlyContinue
```

Then rerun the start and smoke steps. The platform synthetic routes are fixture-driven and should regenerate the same expected outcomes from a clean reset.

## Known Failure Modes

- Local Docker database unavailable. The Dockerized API health check should show `components.database: ok` before browser smoke.
- Docker API unhealthy. Check `docker compose ps api redis postgres fuseki worker` from `C:\Users\user\.pi\projects\inferra-platform`.
- Port collision on `3000`, `3001`, `4179`, or `8000`. Move only the preview port you own, or stop the known owning process.
- AXIOM cannot reach platform. Confirm `http://127.0.0.1:8000/service/inference/syntheticDecisionReceipt?caseId=review-missing-order` returns JSON and that CORS headers are present.
- AEGIS fixture shape drift. Run `bun run test` and confirm `axiomEvidenceEnvelope` still derives the expected `ESCALATE` envelope.
- Browser route shows stale content. Rebuild AXIOM or AEGIS and restart the preview/static server.
- Evidence or logs contain real data, secrets, real payer policy, or unsupported claims. Stop, delete the artifact, and replace only with synthetic fixture output.

## Residual Risk

- This is a local private proof, not a production deployment or public demo.
- QA still needs to perform the independent browser validation path after this issue closes.
- UX/accessibility and collateral wording remain separate readiness gates.
- The AEGIS side intentionally consumes a deterministic offline AXIOM receipt fixture for this slice; it does not prove a live AEGIS backend integration.
- The AXIOM private-demo page proves the receipt workflow against live platform routes; it does not prove the older rule-authoring and database-backed workflows.
