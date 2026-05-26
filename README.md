# INFERRA Platform

INFERRA Platform is a Python/Flask rule and inference service prototype. It stores rule text and history in a SQLAlchemy-backed database, parses rule files, and exposes rule and inference endpoints from `app.py`.

## Repository Status

- Public repository: `DeanLee77/INFERRA-platform`
- Default branch: `main`
- Current intake baseline before README/licensing cleanup: `236ff18`
- Release context: this repository is being reviewed for INFERRA AXIOM/AEGIS readiness. Do not use this repository as a public release, sales-demo, or customer-facing artifact until the release and IP gates are complete.

## Runtime Requirements

- Python 3.9
- Pipenv
- PostgreSQL-compatible database available through `SQLALCHEMY_DATABASE_URI`

## Local Setup

```powershell
pip install pipenv
pipenv install
Copy-Item project/.env.example project/.env
pipenv run python app.py
```

Before running the service, edit `project/.env` with local development values. Do not commit real environment files or secrets.

## Tests

```powershell
pipenv run pytest
```

The test tree currently lives under the `project/**/test_*.py` paths.

## Configuration

The application reads these environment variables:

- `SQLALCHEMY_DATABASE_URI`
- `SECRET_KEY`
- `SESSION_TYPE`

Use `project/.env.example` as the template for local development configuration.

## Licensing

No open-source license is currently granted for this repository.

Until INFERRA Legal/IP approves and publishes a `LICENSE` file or equivalent written licensing terms, the code and documentation in this public repository should be treated as proprietary INFERRA material with all rights reserved. Viewing the public repository does not grant permission to copy, modify, distribute, sublicense, or use it in another product.

Third-party package dependencies are declared in `Pipfile` and `Pipfile.lock`. Their licenses still need Legal/IP review before any release packaging, distribution, or public demo claim relies on this repository.

## Security Notes

- Keep real `.env` files local and out of git.
- Rotate any credential that was ever committed to this public repository before using connected environments.
- Do not add production secrets, customer data, private datasets, or unpublished patent-enabling disclosure to this repository without explicit approval.
