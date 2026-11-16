# MedDataHub backend

FastAPI service for the MedDataHub medical dataset repository. This is the Phase 3 skeleton: configuration, application factory, health/readiness endpoints and database session scaffolding. Domain models, migrations, authentication, storage and ETL are not implemented yet.

## Requirements

- Python 3.12 or newer (verified with 3.14.7)
- MySQL 8.x for the planned persistent database (not required for liveness tests)

## Setup

From the repository root, the unified npm workflow installs the backend into `backend/.venv` and creates `backend/.env` from the example:

```powershell
npm install
```

To work on the backend alone:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
```

Edit `.env` for your local MySQL credentials. Never commit `.env` or real patient data.

## Run

From the repository root:

```powershell
npm run dev:backend
```

Or run Uvicorn directly from `backend`:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- API docs: http://127.0.0.1:8000/docs
- Liveness: http://127.0.0.1:8000/api/v1/health
- Readiness: http://127.0.0.1:8000/api/v1/health/ready

The readiness endpoint returns HTTP 503 while MySQL is unavailable. Liveness does not require a database.

## Verify

From the repository root:

```powershell
npm test
npm run lint:backend
```

Or inside `backend`:

```powershell
pytest
ruff check .
```

Tests override the database dependency, so they do not require a running MySQL instance.

## Layout

```
app/
  api/v1/        Versioned API routes
  core/          Settings and logging
  db/            SQLAlchemy base and session scaffolding
  schemas/       Pydantic response models
  main.py        Application factory and middleware
tests/           API tests
```

## Boundaries

- No authentication or role enforcement yet.
- No tables, models or migrations yet (Phase 4).
- No file storage or upload APIs yet (Phase 6).
- Simulated frontend ETL and assessment output must not be treated as validated production results.
