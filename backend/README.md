# MedDataHub backend

FastAPI service for the MedDataHub dataset repository. It provides JWT authentication, RBAC, persistent SQLAlchemy models, Alembic migrations, secure file storage, upload APIs, a governed ETL engine, rule-based assessment reports and real SDV 2.2.0 CTGAN, TVAE and GaussianCopula synthetic data generation, including exact-equality conditional sampling.

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

Password reset email requires working SMTP settings. Delivery is fail-closed: an unconfigured service returns `503` before any user lookup or code creation; if sending fails, the request still returns the generic `202` response for privacy, but no reset code is persisted or accepted and no success audit entry is written. Six-digit codes are generated with `secrets`, stored only as password hashes, and retain expiry, attempt limits, resend cooldown and one-time use.

| Variable | Default | Purpose |
| --- | --- | --- |
| `SMTP_HOST` | empty (disabled) | SMTP server host; empty disables reset email |
| `SMTP_PORT` | `587` | SMTP port (1-65535) |
| `SMTP_USERNAME` | empty | SMTP username; `SMTP_USER` is accepted as a legacy alias |
| `SMTP_PASSWORD` | empty | SMTP password |
| `SMTP_FROM_EMAIL` | `no-reply@meddatahub.local` | Sender address |
| `SMTP_USE_TLS` | `true` | Start TLS before login |
| `OTP_TTL_SECONDS` | `600` | Code lifetime |
| `OTP_MAX_ATTEMPTS` | `5` | Incorrect-attempt limit |
| `OTP_REQUEST_COOLDOWN_SECONDS` | `60` | Resend cooldown |

Never hardcode credentials or commit `.env`.

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

The current head is `d7f0a1b2c3e4_add_dataset_provenance`, parented on `c4e8f1a2b3d9_create_research_reports`. It adds dataset origin, source lineage and provenance columns; `alembic downgrade -1` reverses it. Earlier revisions add research reports (`c4e8f1a2b3d9`), conditional generation (`b2f6d8a9c1e3`), comparisons (`c74e9b1a6d02`), schema drift reconciliation (`a1f4d7e9c2b6`), generation jobs/configs/reports (`f6b2c9d4e7a1`), SynthMed source/generated tables (`d4a8c1f0b2e3`) and ETL governance (`b7c4e1d9a3f2`). Alembic autogenerate compares server defaults.

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
| `GET` | `/api/v1/synthmed/models` | Supported models, SDV version and compatibility |
| `POST` | `/api/v1/synthmed/generation/analyse/{source_dataset_id}` | Analyse columns and generation readiness |
| `GET` | `/api/v1/synthmed/datasets/{dataset_id}/columns` | Eligible/ineligible columns and model guidance |
| `POST` | `/api/v1/synthmed/generation/validate-conditions` | Validate model, conditions and cohorts |
| `POST` | `/api/v1/synthmed/conditions/validate` | Alias for condition validation |
| `POST` | `/api/v1/synthmed/generation/start` | Start a job with `model`, `generationMode` and `conditions` |
| `GET` | `/api/v1/synthmed/generation/jobs/{job_id}` | Job status and error message |
| `GET` | `/api/v1/synthmed/generation/jobs` | Job history |
| `GET` | `/api/v1/synthmed/generation/jobs/{job_id}/conditions` | Condition result for a job |
| `GET` | `/api/v1/synthmed/generated` | Generated datasets |
| `GET` | `/api/v1/synthmed/generated/{generation_id}` | Generated dataset detail |
| `GET` | `/api/v1/synthmed/generated/{generation_id}/preview` | Generated data preview |
| `GET` | `/api/v1/synthmed/generated/{generation_id}/conditions` | Condition-satisfaction report |
| `GET` | `/api/v1/synthmed/generated/{generation_id}/evaluation` | Combined evaluation summary |
| `GET` | `/api/v1/synthmed/generated/{generation_id}/quality` | SDMetrics quality report |
| `GET` | `/api/v1/synthmed/generated/{generation_id}/privacy` | Privacy-risk report |
| `GET` | `/api/v1/synthmed/generated/{dataset_id}/download` | Download generated dataset |
| `POST` | `/api/v1/synthmed/generated/{generation_id}/export` | Export generated data to another format |
| `GET` | `/api/v1/synthmed/generated/{generation_id}/reports/{report_type}/download` | Download report JSON |

Research PDF reports are owner-scoped and immutable. Creation endpoints are `POST /api/v1/reports/dataset-profile`, `/api/v1/reports/etl`, `/api/v1/reports/synthmed/generation`, `/api/v1/reports/synthmed/comparison`, `/api/v1/reports/synthmed/privacy`, `/api/v1/reports/synthmed/utility` and `/api/v1/reports/synthmed/experiment`. Use `GET /api/v1/reports`, `GET /api/v1/reports/{report_id}`, `GET /api/v1/reports/{report_id}/status` and `GET /api/v1/reports/{report_id}/download` for history, detail, status and checksum-verified download.

Supported models are CTGAN (`CTGANSynthesizer`), TVAE (`TVAESynthesizer`) and GaussianCopula (`GaussianCopulaSynthesizer`), both unconditionally and conditionally. One fitted synthesizer instance generates all records in a job. Conditional generation uses `sample_from_conditions` with `sdv.sampling.Condition` exact-equality conditions: CTGAN and TVAE use SDV reject sampling, while GaussianCopula uses native conditioned Gaussian multivariate sampling. Range operators, missing/null values, primary keys and patient identifiers are rejected. Exact conditions on different columns with equal `numRows` are combined with AND; unequal `numRows` produce separate cohorts whose values sum to `recordCount`. Job states include `Evaluating` between `Validating` and `Completed`.

CTGAN/TVAE training runs on CPU with configurable epochs, batch size and seed. Batch size must be a multiple of 10 between 20 and 10000. Set `SYNTHMED_GENERATION_INLINE=true` for inline test execution; production uses in-process background workers.

Set `SYNTHMED_STALE_JOB_RECOVERY_ENABLED=false` to skip startup recovery. `SYNTHMED_STALE_JOB_AFTER_SECONDS` is an optional minimum age for recovery; `0` marks all active jobs found at startup as interrupted. Recovery runs before requests are accepted, writes an `InterruptedJob` error and an audit entry, and is idempotent. If recovery fails, the error is logged and startup continues. On shutdown the executor stops accepting submissions, running tasks are awaited, SQLAlchemy engine disposal happens last, and shutdown errors are logged.

There is no durable queue. The SynthMed worker is in-process, so a process crash before completion cannot resume training or sampling; recovery only converts stranded active jobs into a terminal failed state so users can resubmit. ETL jobs run synchronously in request handlers and do not use a separate executor.

## Verify

From the repository root:

```powershell
npm test
npm run lint:backend
npm run test:e2e
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
    synthmed/       Source datasets, model selection, conditional generation, evaluation and routes
   utils/          Upload validation helpers

migrations/       Alembic environment and revisions
tests/            API, workflow and ETL governance tests
```

## Boundaries

- Quality, readiness and representativeness scores are rule-based, not clinically validated.
- SynthMed quality, privacy and condition reports are statistical screening signals, not clinical equivalence, differential privacy or anonymity guarantees; condition satisfaction is measured from generated records and is separate from quality and privacy.
- Conditional cohorts can introduce selection artefacts; rare exact values may yield fewer rows or fail under reject sampling.
- Only synthetic data should be used.
- Ambiguous dates are never inferred; missing values are never imputed; invalid rows are flagged and retained.
- Raw files are immutable and processed outputs are atomically replaced with rollback on validation failure.
- Stored file paths are resolved inside their designated storage root; absolute legacy paths are accepted only when they remain inside that root.
- Generated outputs and reports are owner-scoped; source files are never modified during generation.
