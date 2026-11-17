# Development progress

Last updated: 2026-11-17

## Phase status

| Phase | Scope | Status | Notes |
| --- | --- | --- | --- |
| 1 | Inspect repository and environment | Complete | Existing application code and tests were reviewed before changes. |
| 2 | React/TypeScript frontend | Complete | All required screens exist; ETL screen now uses real backend state. |
| 3 | FastAPI skeleton and configuration | Complete | App factory, settings, CORS, request IDs, health/readiness. |
| 4 | Database schema and migrations | Complete | SQLAlchemy models and Alembic revisions, including ETL governance migration. |
| 5 | Authentication and RBAC | Complete | JWT auth, server-side roles and protected operations. |
| 6 | Secure file storage and upload APIs | Complete | Validated uploads, raw/processed storage paths, checksums and versions. |
| 7 | Dataset and metadata persistence | Complete | Datasets, versions, metadata, reports and audit records are persisted. |
| 8 | ETL pipeline and mapping workflow | Complete | Profile → review → approve → run, atomic load and preserved originals. |
| 9 | Data-quality engine | Complete | Rule-based reports; not clinically validated. |
| 10 | AI-readiness assessment | Complete | Rule-based reports; not clinically validated. |
| 11 | Representativeness assessment | Complete | Rule-based reports; not clinically validated. |
| 12 | Access governance and audit logs | Complete | Server-side access decisions and audit logging. |
| 13 | Frontend/API integration | Complete | UI actions call FastAPI endpoints and reflect backend job state. |
| 14 | Testing, documentation and hardening | In progress | Backend workflow coverage and docs updated; frontend test suite still absent. |

## ETL governance implementation

- Job states: `Queued`, `Profiling`, `Review required`, `Approved`, `Processing`, `Completed`, `Failed`, `Cancelled`, `Rejected`.
- Upload creates only a `Queued` job; mapping suggestions are never auto-approved.
- Profiling records row/column counts, inferred types, missing values, duplicate rows, malformed/duplicate headers, mixed types and ambiguous dates.
- Every source column requires an explicit reviewer decision: `Approved`, `Rejected` or `Unmapped`.
- Approval requires all decisions, records approver identity/time and an audit entry.
- Run requires approved mappings and uses a conditional database status transition to prevent concurrent runs.
- Transform preserves original values, flags invalid/review rows, retains every row, and never imputes missing values.
- Ambiguous dates such as `03/04/2025` are left unchanged and flagged; only unambiguous patterns are standardised.
- Unit conversions occur only when the unit is explicit in the source name and are logged.
- Load stages processed CSV and transformation log files, validates them, publishes with `os.replace`, and restores previous outputs on failure.
- Frontend ETL page exposes profiling, decision saving, approval, run, cancel, administrator rejection, profile findings and transformation reports.

## Verification record

| Check | Command | Result |
| --- | --- | --- |
| Backend lint | `ruff check .` | Passed |
| Backend tests | `pytest` | 26 passed |
| Alembic upgrade/downgrade | `alembic upgrade head`, `alembic downgrade -1` | Passed on a temporary SQLite database |
| TypeScript strict check | `npm run typecheck` | Passed |
| Production build | `npm run build` | Passed |
| Frontend tests | None configured | Not run |

Tests use synthetic CSV/XLSX/JSON fixtures only. No real patient data was used.

## Known gaps and risks

- Quality, readiness and representativeness scores are transparent rules, not clinically validated assessment instruments.
- No frontend unit/component or end-to-end test suite is configured; the ETL UI was typechecked and production-built but not browser-smoke-tested after the rewrite.
- Backend integration tests against a real MySQL instance are still absent; workflow tests use SQLite overrides.
- Readiness requires a configured and reachable MySQL instance in normal operation.
- SQLAlchemy must stay on 2.0.x until the 2.1 C-extension compatibility issue on Python 3.14/Windows is resolved.
- `npm audit` reports advisories in React Router 6; the available fix requires a major upgrade and should be handled separately.
- Processed outputs are staged behind governance approval; this prototype does not claim regulatory compliance.

## Recommended next step

Add frontend component tests for the ETL review flow and run a MySQL-backed integration pass over upload → profiling → decisions → approval → run → download before treating the pipeline as production-ready.
