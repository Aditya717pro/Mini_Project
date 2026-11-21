# MedDataHub

MedDataHub is an AI-ready medical dataset repository prototype for women's and paediatric health research. It uses a React/TypeScript frontend, a FastAPI service, persistent SQLAlchemy storage and a governed ETL pipeline. All bundled and test data is synthetic.

> **Current milestone:** authentication, persistent dataset storage, upload APIs, the governed ETL engine, the React/API integration and real SDV 2.2.0 CTGAN, TVAE and GaussianCopula generation, including exact-equality conditional sampling, are implemented. Quality, readiness, representativeness, synthetic quality, privacy-risk and condition-satisfaction reporting are rule-based/statistical and are not clinically validated.

## Quick start

Requirements: Node.js 20+ and Python 3.12+. MySQL 8 is needed for normal persistent operation; tests use SQLite overrides.

```powershell
npm install
npm run dev
```

- Frontend: http://localhost:5173
- API docs: http://127.0.0.1:8000/docs
- Liveness: http://127.0.0.1:8000/api/v1/health
- Readiness: http://127.0.0.1:8000/api/v1/health/ready

If npm lifecycle scripts are disabled, run `node scripts/setup.mjs` once instead of `npm install`.

## ETL lifecycle

Uploads create a `Queued` job. The UI and API enforce this sequence:

`Queued → Profiling → Review required → Approved → Processing → Completed`

`Failed`, `Cancelled` and `Rejected` are terminal/closed states. Suggestions are never auto-approved. Every source column needs an explicit `Approved`, `Rejected` or `Unmapped` decision before the mapping set can be approved and run.

Key ETL endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/etl/jobs` | List accessible jobs |
| `GET` | `/api/v1/etl/jobs/{job_id}` | Job status, profile, mappings, logs and report |
| `POST` | `/api/v1/etl/jobs/{job_id}/profile` | Profile raw data and generate suggestions |
| `POST` | `/api/v1/etl/jobs/{job_id}/mappings` | Record reviewer decisions |
| `POST` | `/api/v1/etl/jobs/{job_id}/approve` | Approve the completed mapping set |
| `POST` | `/api/v1/etl/jobs/{job_id}/run` | Run approved ETL atomically |
| `POST` | `/api/v1/etl/jobs/{job_id}/cancel` | Cancel a cancellable job |
| `POST` | `/api/v1/etl/jobs/{job_id}/reject` | Administrator rejection |

Raw files are immutable. Processed CSV and transformation logs are staged in temporary files, validated, then published with atomic replacement and rollback. Ambiguous dates are left unchanged and flagged; missing values are not imputed; invalid rows are retained and flagged; unit conversions are never silent.

## SynthMed generation

SynthMed trains real SDV 2.2.0 synthesizers on an uploaded source dataset. Supported models are CTGAN (`CTGANSynthesizer`), TVAE (`TVAESynthesizer`) and GaussianCopula (`GaussianCopulaSynthesizer`), for both unconditional and conditional generation. Generation analyses source columns, detects likely identifiers, records preprocessing decisions, validates SDV metadata, then models only eligible columns. Identifier-like columns are excluded rather than reproduced, source files are never modified, and missing values are preserved by default. One fitted synthesizer instance generates all records for a job.

Conditional generation uses `sample_from_conditions` with `sdv.sampling.Condition` exact-equality conditions. CTGAN and TVAE use SDV reject sampling; GaussianCopula uses native conditioned Gaussian multivariate sampling. Range operators, missing/null values, primary keys and patient identifiers are rejected. Exact conditions on different columns with the same `numRows` are combined with AND; groups with different `numRows` are separate cohorts whose `numRows` sum to `recordCount`.

Jobs progress through genuine states: `Queued`, `Preprocessing`, `Training`, `Generating`, `Validating`, `Evaluating`, `Completed` and `Failed`. The UI polls actual backend status and does not show simulated progress. CTGAN/TVAE training uses CPU and supports configurable epochs, batch size and random seed; batch size must be a multiple of 10 between 20 and 10000.

Key generation endpoints:

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
| `GET` | `/api/v1/synthmed/generated/{generation_id}` | Dataset detail and configuration |
| `GET` | `/api/v1/synthmed/generated/{generation_id}/preview` | Generated data preview |
| `GET` | `/api/v1/synthmed/generated/{generation_id}/conditions` | Condition-satisfaction report |
| `GET` | `/api/v1/synthmed/generated/{generation_id}/evaluation` | Combined evaluation summary |
| `GET` | `/api/v1/synthmed/generated/{generation_id}/quality` | SDMetrics quality report |
| `GET` | `/api/v1/synthmed/generated/{generation_id}/privacy` | Privacy-risk report |
| `GET` | `/api/v1/synthmed/generated/{dataset_id}/download` | Download generated dataset |
| `POST` | `/api/v1/synthmed/generated/{generation_id}/export` | Export generated data to another format |
| `GET` | `/api/v1/synthmed/generated/{generation_id}/reports/{report_type}/download` | Download report JSON |

Quality reports use SDMetrics quality and diagnostics. Condition satisfaction is computed from generated records and stored as a separate `conditions` report; it is distinct from quality, privacy and clinical validity. Privacy reports cover exact overlap, duplicates, nearest-neighbour similarity and explicit limitations, including a conditional-cohort limitation. These are screening signals only: they do not establish clinical equivalence, differential privacy or anonymity.

## Current features

- Dashboard with repository, quality, readiness and access-request summaries.
- JWT authentication with server-side roles and RBAC on protected operations.
- Real CSV/XLSX/JSON uploads with metadata, checksums and persistent version records.
- Dataset catalogue, search, filtering, pagination, detail views and version history.
- ETL workspace driven by backend job state, profiling output, mapping decisions, logs and transformation reports.
- Quality, AI-readiness and representativeness reports generated by transparent rules.
- SynthMed CTGAN/TVAE/GaussianCopula generation with model selection, compatibility display, conditional toggle, condition builder and validation.
- Real job state, preprocessing records, previews, format exports and condition/evaluation display.
- SDMetrics quality/diagnostics, privacy-risk and condition-satisfaction reports with explicit limitations and comparison metadata.
- Access-request workflow, governance decisions and audit logging.
- Responsive layout with accessible controls, loading/empty/error states and toasts.

## Tech stack

| Layer | Choice |
| --- | --- |
| UI | React 18, TypeScript, Vite 6 |
| Routing | React Router 6 |
| Charts | Recharts |
| Icons | Lucide React |
| Backend | FastAPI, Pydantic Settings, SQLAlchemy 2.0, Alembic, PyMySQL, Uvicorn |
| Synthetic data | SDV 2.2.0 (CTGAN, TVAE, GaussianCopula), SDMetrics, Pandas, NumPy, scikit-learn, CPU-only PyTorch |
| Testing | pytest, Ruff, TypeScript compiler, Vite build |

## Development commands

| Command | Purpose |
| --- | --- |
| `npm install` | Install all dependencies and create local environment files |
| `npm run dev` | Run the frontend and API together |
| `npm run dev:frontend` | Run only the Vite frontend |
| `npm run dev:backend` | Run only the FastAPI API |
| `npm run build` | Typecheck and build the frontend |
| `npm run typecheck` | Typecheck the frontend |
| `npm run lint:backend` | Run Ruff against the backend |
| `npm test` | Run backend tests |

## Configuration and security

Password reset email is fail-closed. Copy `backend/.env.example` to `backend/.env` and set `SMTP_HOST` to enable it; with no host, `POST /api/v1/auth/forgot-password` returns `503` and no code is stored. The supported variables are `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME` (legacy alias `SMTP_USER`), `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` and `SMTP_USE_TLS`. Codes are six-digit `secrets`-generated values stored only as hashes, with expiry, attempt limits, resend cooldown and one-time use. Never commit `.env` or credentials.

SynthMed uses a single-process in-memory worker, not a durable queue: a process crash can interrupt active generation. Startup recovery fails stranded active jobs with an `InterruptedJob` payload so they can be resubmitted. Defaults are `SYNTHMED_STALE_JOB_RECOVERY_ENABLED=true` and `SYNTHMED_STALE_JOB_AFTER_SECONDS=0`; recovery is conditional, idempotent and preserves terminal jobs. Shutdown stops new submissions, awaits running tasks and disposes the database engine last. Stored paths are resolved inside their designated raw, processed or SynthMed root; traversal, symlink escapes, cross-root and directory paths are rejected with controlled `404` responses.

## Behaviour boundaries

| Capability | Status |
| --- | --- |
| Authentication, RBAC and audit logging | Implemented server-side |
| Persistent datasets, versions, jobs, decisions and reports | Implemented |
| ETL profiling, mapping review, atomic load and raw preservation | Implemented |
| Quality, readiness and representativeness scores | Rule-based; not clinically validated |
| Multi-model generation, quality, privacy and condition reports | Implemented; statistical screening only |
| Clinical equivalence, differential privacy, anonymity guarantees, regulatory validation and real patient data | Out of scope |

Uploading never publishes a dataset. Completed ETL output remains subject to governance approval before broader access. Use synthetic data only.

## Project structure

```text
backend/
  app/
    api/routes/         Versioned API routes
    etl/                Extract, transform, load and pipeline engine
    models/             SQLAlchemy domain models
    schemas/            Pydantic request/response models
    services/           Auth, upload, profiling, mapping, job, storage and report services
    synthmed/           Source datasets, multi-model conditional generation, evaluation and downloads
    db/                 Engine, session and Alembic-managed schema
  migrations/versions/  Alembic migrations
  tests/                API, workflow and ETL governance tests
frontend/
  src/
    pages/              Route-level screens
    store/              API-backed application state and actions
    lib/                API client, parsing and formatting
    components/         Reusable UI primitives
docs/
  progress.md           Verification record and known gaps
```

See `docs/progress.md` for current verification results and `backend/README.md` for migration and test details.
