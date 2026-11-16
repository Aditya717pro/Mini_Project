# Development progress

Last updated: 2026-11-16

## Phase status

| Phase | Scope | Status | Notes |
| --- | --- | --- | --- |
| 1 | Inspect repository and environment; produce implementation plan | Complete | Frontend scaffolded from scratch; no existing application code was present. |
| 2 | React/TypeScript frontend with all required screens and demo flows | Complete | Code-complete, typechecked, production-built and browser smoke-tested. |
| 3 | FastAPI skeleton and configuration | Complete | App factory, settings, CORS, request IDs, health/readiness endpoints, DB session scaffolding, tests and linting. |
| 4 | MySQL schema, SQLAlchemy models and Alembic migrations | Not started | `mysql` was not available on PATH during Phase 1. |
| 5 | Authentication and role-based access control | Not started | Current role switch is UI-only. |
| 6 | Secure file storage and upload APIs | Not started | Uploads are browser-local only. |
| 7 | Dataset, version and metadata persistence | Not started | Seed data is in memory only. |
| 8 | ETL pipeline and mapping workflow | Not started | ETL jobs/progress are simulated. |
| 9 | Data-quality engine | Not started | Reports are rule-based demonstrations. |
| 10 | AI-readiness assessment | Not started | Scores are rule-based demonstrations. |
| 11 | Representativeness assessment | Not started | Scores are rule-based demonstrations. |
| 12 | Access governance and audit logs | Not started | Approvals are in-memory demo actions. |
| 13 | Frontend/backend integration | Not started | Placeholder env vars exist in `frontend/.env.example`. |
| 14 | Testing, documentation and hardening | In progress | Frontend checks and backend API/config tests exist; domain, integration and security testing remain. |

## Implemented frontend scope

### Screens

- Dashboard
- Upload dataset
- My datasets
- Dataset detail (including versions, quality, readiness, access and preview)
- ETL processing
- Data quality
- AI readiness
- Representativeness
- Dataset repository
- Access requests
- Settings
- 404 page

### Behaviour

- Browser-local file validation: extension allow-list, 25 MB limit, magic-signature checks, CSV/JSON/XLSX parsing.
- Real profiling: row/column counts, inferred column types, missing percentages, duplicate rows, sample values.
- Real SHA-256 checksum via Web Crypto.
- Upload workflow: metadata validation, local submit simulation, ETL job creation, pending governance review.
- In-memory demo state for datasets, versions, ETL jobs, quality/readiness/representativeness reports, access requests, activity and toasts.
- Repository search, domain/access/status filters, sorting, grid/table views and pagination.
- Mapping review, publish and access-decision simulations.
- Route-level lazy loading with a loading fallback.
- Responsive desktop/mobile navigation and zero horizontal overflow at 390 px.

## Implemented backend scope (Phase 3)

- FastAPI application factory with injectable settings for tests.
- Environment-driven settings from `backend/.env` or process environment, including app metadata, environment, API prefix, database URL, CORS origins, log level and SQL echo.
- CORS middleware restricted to configured frontend origins.
- Request-ID middleware: validates incoming `X-Request-ID` values and generates UUID-based IDs, returned in responses.
- `GET /api/v1/health`: liveness that never touches the database.
- `GET /api/v1/health/ready`: executes `SELECT 1` through SQLAlchemy and returns HTTP 503 with a degraded payload when MySQL is unavailable.
- SQLAlchemy declarative base, engine factory, session factory and request-scoped `get_db` dependency.
- Root metadata endpoint and OpenAPI documentation at `/docs`.
- Ruff lint configuration and 13 backend tests covering configuration, liveness, readiness success/failure, request IDs, CORS, OpenAPI and engine query execution.
- CORS origins accept both comma-separated process environment values and initializer lists; environment parsing uses `NoDecode` so Pydantic Settings does not require JSON arrays.
- SQLAlchemy is pinned below 2.1: the 2.1.8 C extension failed to load on Python 3.14.7/Windows in this environment, while 2.0.57 works.
- Development tests use `httpx2`, which current Starlette versions require for `TestClient`.

## Unified npm workflow

- Root `package.json` provides `npm install`, `npm run dev`, `npm run build`, `npm run typecheck`, `npm run lint:backend` and `npm test`.
- `npm install` runs `scripts/setup.mjs`, which installs frontend packages, creates `backend/.venv` when needed, installs backend editable dependencies and creates local `.env` files from the examples.
- `npm run dev` runs `scripts/dev.mjs`, which starts Vite on port 5173 and Uvicorn on port 8000 together and stops both on exit or Ctrl+C.
- `scripts/backend.mjs` runs Python tooling and tests inside the backend virtual environment, so contributors do not need to activate it manually.
- Individual `dev:frontend` and `dev:backend` commands remain available.

## Verification record

| Check | Command | Result |
| --- | --- | --- |
| TypeScript strict check | `npm run typecheck` | Passed |
| Production build | `npm run build` | Passed; route chunks split; no chunk-size warning |
| Browser route smoke test | Headless Chrome via Playwright | Passed for all routes, dataset detail, upload workflow and repository search |
| Console/runtime errors | Same smoke test | Zero page errors, console errors or HTTP 4xx responses |
| Mobile layout | 390 x 844 viewport | Zero horizontal overflow |
| Unified install | `npm install` | Frontend and backend dependencies installed; local env files created |
| Unified dev servers | `npm run dev` | Frontend 200, API liveness 200, readiness 503 without MySQL |
| Backend lint | `npm run lint:backend` | Passed |
| Backend tests | `npm test` | 13 passed |
| Live API smoke | Uvicorn + `curl` | Liveness 200, readiness 503 without MySQL, OpenAPI 200 |
| API request IDs | Live smoke and tests | Returned and validated |
| CORS | TestClient preflight | Configured frontend origin allowed |

The smoke test used generated synthetic CSV data and did not upload any real or patient data.

## Known gaps and risks

- Backend has no domain models, database tables, migrations or business endpoints yet.
- No authentication, authorization, persistent storage or audit logging yet.
- ETL progress, quality, readiness and representativeness outputs are demonstration rules, not validated scientific scoring.
- Role switching and approvals are not security controls; they must be replaced by server-side RBAC.
- Downloads are disabled by demonstration policy; signed URL generation is not implemented.
- Dataset identifiers and timestamps are generated client-side for the demo.
- Readiness reports HTTP 503 until MySQL is installed, configured and reachable. No schema exists yet.
- SQLAlchemy must stay on 2.0.x until the 2.1 C extension compatibility issue on Python 3.14/Windows is resolved or Python is downgraded.
- No committed frontend unit/component or end-to-end test suite yet; verification used a temporary external browser smoke script.
- No backend integration tests against a real MySQL instance yet.
- `mysql` is not on PATH; database tooling must be configured before Phase 4.
- `npm audit` reports moderate advisories in React Router 6; the available fix requires a major upgrade to React Router 7 and should be handled as a dedicated dependency migration.
- The unified installer runs npm install and pip install during `npm install`; environments with lifecycle scripts disabled must run `node scripts/setup.mjs` manually.

## Recommended next step

Begin Phase 4: define the MySQL schema and SQLAlchemy models for users, roles, datasets, versions, files, metadata, ETL jobs/steps/logs, quality/readiness/representativeness reports and access requests; add Alembic, constraints, indexes and migrations, plus database-level tests.
