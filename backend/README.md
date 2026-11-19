# MedDataHub backend

FastAPI service for the MedDataHub dataset repository. It provides JWT authentication, RBAC, persistent SQLAlchemy models, Alembic migrations, secure file storage, upload APIs, a governed ETL engine, rule-based assessment reports and real CTGAN synthetic data generation via SDV.

## Requirements

- Python 3.12 or newer
- MySQL 8.x for normal persistent operation (tests use SQLite)
- Node.js 20+ only for the unified root scripts

## Setup

From the repository root:

```powershell
npm install
```

Or work on the backend alone:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
```

Edit `.env` for local database settings. Never commit `.env` or real patient data.

## Run

From the repository root:

```powershell
npm run dev:backend
```

Or from `backend`:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- API docs: http://127.0.0.1:8000/docs
- Liveness: http://127.0.0.1:8000/api/v1/health
- Readiness: http://127.0.0.1:8000/api/v1/health/ready

## Migrations

Apply schema changes with Alembic:

```powershell
alembic upgrade head
```

Roll back the latest migration:

```powershell
alembic downgrade -1
```

The `b7c4e1d9a3f2_etl_governance` migration adds ETL approval/decision columns and the `etl_mapping_decisions` table, and migrates the previous `Running` status to `Processing`. SynthMed adds `d4a8c1f0b2e3_synthmed_source_and_generated_tables` for source/generated datasets and `f6b2c9d4e7a1_ctgan_generation_jobs_configs_and_reports` for generation jobs, configs and evaluation reports.

## ETL API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/etl/jobs` | List accessible jobs |
| `GET` | `/api/v1/etl/jobs/{job_id}` | Job detail with profile, mappings, logs and report |
| `POST` | `/api/v1/etl/jobs/{job_id}/profile` | Extract/profile raw data and generate suggestions |
| `POST` | `/api/v1/etl/jobs/{job_id}/mappings` | Record all mapping decisions |
| `POST` | `/api/v1/etl/jobs/{job_id}/approve` | Approve the reviewed mapping set |
| `POST` | `/api/v1/etl/jobs/{job_id}/run` | Run ETL with conditional status locking |
| `POST` | `/api/v1/etl/jobs/{job_id}/cancel` | Cancel a cancellable job |
| `POST` | `/api/v1/etl/jobs/{job_id}/reject` | Administrator-only rejection |

Example mapping decision payload:

```json
[
  { "source": "age", "decision": "Approved", "target": "age_years", "note": "Unit declared in years" },
  { "source": "notes", "decision": "Unmapped", "target": null }
]
```

## SynthMed generation API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/synthmed/generation/analyse/{source_dataset_id}` | Analyse columns and generation readiness |
| `POST` | `/api/v1/synthmed/generation/start` | Start a real CTGAN training job |
| `GET` | `/api/v1/synthmed/generation/jobs/{job_id}` | Job status and error message |
| `GET` | `/api/v1/synthmed/generation/jobs` | Job history |
| `GET` | `/api/v1/synthmed/generated` | Generated datasets |
| `GET` | `/api/v1/synthmed/generated/{generation_id}` | Generated dataset detail |
| `GET` | `/api/v1/synthmed/generated/{generation_id}/preview` | Generated data preview |
| `GET` | `/api/v1/synthmed/generated/{generation_id}/quality` | SDMetrics quality report |
| `GET` | `/api/v1/synthmed/generated/{generation_id}/privacy` | Privacy-risk report |
| `GET` | `/api/v1/synthmed/generated/{dataset_id}/download` | Download generated dataset |
| `POST` | `/api/v1/synthmed/generated/{generation_id}/export` | Export generated data to another format |
| `GET` | `/api/v1/synthmed/generated/{generation_id}/reports/{report_type}/download` | Download report JSON |

Generation runs on CPU with configurable epochs, batch size and seed. Batch size must be a multiple of 10 between 20 and 10000. Set `SYNTHMED_GENERATION_INLINE=true` for inline test execution; production uses background workers.

## Verify

From the repository root:

```powershell
npm test
npm run lint:backend
```

Or from `backend`:

```powershell
pytest
ruff check .
```

Tests override the database and storage dependencies, so a running MySQL instance is not required.

## Layout

```text
app/
  api/routes/     Versioned API routes
  core/           Settings and logging
  db/             SQLAlchemy engine, session and base
  etl/            Extract, transform, load and pipeline modules
  models/         Domain models
  schemas/        Pydantic request/response models
   services/       Business services
   synthmed/       Source datasets, CTGAN generation, evaluation and routes
   utils/          Upload validation helpers

migrations/       Alembic environment and revisions
tests/            API, workflow and ETL governance tests
```

## Boundaries

- Quality, readiness and representativeness scores are rule-based, not clinically validated.
- CTGAN quality and privacy reports are statistical screening signals, not clinical equivalence, differential privacy or anonymity guarantees.
- Only synthetic data should be used.
- Ambiguous dates are never inferred; missing values are never imputed; invalid rows are flagged and retained.
- Raw files are immutable and processed outputs are atomically replaced with rollback on validation failure.
- Generated outputs and reports are owner-scoped; source files are never modified during generation.
