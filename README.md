# MedDataHub

MedDataHub is an AI-ready medical dataset repository for women's and paediatric health research. It is being built as a modular, phased application: a React frontend backed by a FastAPI/MySQL service, with a governed ETL and dataset-assessment pipeline.

> **Current milestone: Phases 1-3.** The frontend demo is complete and the FastAPI backend skeleton is in place. Authentication, persistent storage, domain models, upload APIs and the production ETL engine are not implemented yet. All repository records and pipeline outputs remain synthetic demonstration data.

## Quick start

Requirements: Node.js 20+ and Python 3.12+. MySQL is only needed for the readiness probe and later phases.

```powershell
npm install
npm run dev
```

`npm install` installs the root, frontend and backend dependencies, creates the backend virtual environment and creates local `.env` files from the examples. `npm run dev` starts both services:

- Frontend: http://localhost:5173
- API docs: http://127.0.0.1:8000/docs
- Liveness: http://127.0.0.1:8000/api/v1/health
- Readiness: http://127.0.0.1:8000/api/v1/health/ready

Readiness returns HTTP 503 until MySQL is configured and reachable. Press Ctrl+C to stop both servers.

If npm lifecycle scripts are disabled in your environment, run `node scripts/setup.mjs` once instead of `npm install`.

## Current features

- Dashboard with repository, quality, readiness and access-request summaries.
- Dataset upload with real browser-local CSV, XLSX and JSON validation, type inference, missing-value profiling and SHA-256 checksums.
- Dataset catalogue, search, filtering, pagination, detail views and version history.
- ETL workspace with queued/running/completed jobs, steps and logs (simulated).
- Data-quality, AI-readiness and representativeness assessments (rule-based demonstration reports).
- Access-request workflow and role switching (UI-only demonstration; not authentication).
- Responsive layout, accessible controls, loading/empty/error states and a global toast system.

Backend skeleton:

- FastAPI application factory with environment-based settings and CORS configuration.
- Versioned liveness and database-readiness endpoints with request IDs.
- SQLAlchemy engine/session scaffolding, configured for MySQL via PyMySQL.
- Backend linting and API tests that do not require a running database.

## Tech stack

| Layer | Choice |
| --- | --- |
| UI | React 18, TypeScript, Vite 6 |
| Routing | React Router 6 |
| Charts | Recharts |
| Icons | Lucide React |
| Spreadsheet parsing | read-excel-file |
| Database (planned) | MySQL 8, Alembic migrations |
| Backend (implemented) | FastAPI, Pydantic Settings, SQLAlchemy 2.0, PyMySQL, Uvicorn, pytest, Ruff |
| Planned processing | Python ETL jobs with persisted lineage and reports |

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

Frontend-specific and Python-specific commands remain available in `frontend/package.json` and `backend/README.md`.

## Demo versus real behaviour

| Capability | Status |
| --- | --- |
| File extension, size, signature, CSV/JSON/XLSX parsing | Real, in-browser |
| Row/column profiling, inferred types, duplicate and missing counts | Real, in-browser |
| SHA-256 checksum | Real, in-browser |
| Dataset IDs, ETL progress, quality/readiness/representativeness scores | Rule-based simulation |
| Role switching, approvals, downloads, version publishing | UI demonstration only |
| Persistent storage, authentication, signed downloads | Not connected yet |

Uploading never publishes or downloads a dataset. New records enter a simulated governance review and remain non-downloadable. Only synthetic data should ever be used in this demo.

## Project structure

```
package.json            Unified npm install/dev/build/test commands
scripts/
  setup.mjs             Installs frontend/backend dependencies and env files
  dev.mjs               Runs both development servers
  backend.mjs           Runs Python commands inside the backend virtualenv
backend/
  app/
    api/v1/             Versioned API routes (health, readiness)
    core/               Settings and logging
    db/                 SQLAlchemy base and session scaffolding
    schemas/            Pydantic response models
    main.py             Application factory and middleware
  tests/                API and configuration tests
  pyproject.toml        Dependencies, pytest and Ruff configuration
frontend/
  public/               Static assets (favicon)
  src/
    components/         Reusable UI primitives
    data/               Synthetic seed data and demo report builders
    layouts/            Application shell and navigation
    lib/                File extraction/profiling, checksums, formatting
    pages/              Route-level screens (lazy-loaded)
    store/              In-memory demo state and actions
    types.ts            Shared domain types
  index.html
  vite.config.ts
docs/
  progress.md           Phase status, verification results and known gaps
```

## Roadmap

| Phase | Scope | Status |
| --- | --- | --- |
| 1 | Repository inspection and plan | Complete |
| 2 | Frontend application and demo flows | Complete |
| 3 | FastAPI skeleton and configuration | Complete |
| 4 | MySQL schema, models and migrations | Not started |
| 5-7 | Authentication, secure dataset storage and upload APIs | Not started |
| 8-11 | ETL pipeline, quality, readiness and representativeness engines | Not started |
| 12 | Access governance and audit logging | Not started |
| 13 | Frontend/API integration | Not started |
| 14 | Testing, documentation and hardening | In progress |

See `docs/progress.md` for the current verification record and next steps.
