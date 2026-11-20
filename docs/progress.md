# Development progress

Last updated: 2026-11-20

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
| 15 | SynthMed CTGAN generation and reporting | Complete | Real SDV CTGAN jobs, previews, exports, SDMetrics quality reports and privacy-risk reports. |
| 16 | P0 audit remediation | Complete | Admin RBAC, worker recovery/shutdown, storage containment, fail-closed OTP and Alembic drift checks. |

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

## SynthMed CTGAN implementation

- Uploads source datasets into owner-scoped storage without modifying the original file.
- Generation analysis detects likely identifiers, column kinds, missingness and modelable columns; zero-modelable-column jobs fail with a clear message.
- SDV metadata is detected and validated before training; pandas datetime columns omit `datetime_format` to avoid SDV validation failures.
- Real `CTGANSynthesizer` training/generation runs on CPU with configurable epochs, batch size and seed; batch size is constrained to multiples of 10 between 20 and 10000.
- Job states are genuine backend states: `Queued`, `Preprocessing`, `Training`, `Generating`, `Validating`, `Completed` and `Failed`; failed jobs record an error message and traceback server-side.
- Generation excludes identifier-like categorical columns from modelling; numerical columns are not dropped solely for high uniqueness.
- Previews, CSV/XLSX/JSON downloads, alternate-format exports and JSON report downloads are owner-scoped.
- Quality reporting uses SDMetrics quality and diagnostics with per-property scores and details.
- Privacy reporting covers exact overlap, duplicate rows, nearest-neighbour similarity and explicit limitations; no anonymity or differential privacy claim is made.

## P0 audit remediation

- Administrator access checks now use `UserRole.ADMINISTRATOR` in MedDataHub datasets and SynthMed generation jobs, and administrators list all generation jobs without owning them.
- SynthMed startup recovery marks stranded active jobs as `Failed` with an `InterruptedJob` error and audit entry; recovery is idempotent, configurable and safe to disable in tests.
- API shutdown stops accepting new executor submissions, awaits running work, logs shutdown failures and disposes the database engine last. No durable queue was introduced.
- Stored file paths are resolved through a shared containment helper. Absolute legacy paths are accepted only inside the correct root; traversal, symlink escapes, cross-category paths and directories are rejected with controlled 404 responses before ETL, readiness, analysis, preview, export or download work begins.
- New dataset and ETL file persistence uses normalised relative paths; old absolute paths remain readable when contained. Internal filesystem paths are not returned in API responses.
- Password reset delivery is fail-closed: configuration is checked before user lookup, an unconfigured SMTP service returns `503` and creates no OTP, and a delivery failure rolls back the OTP and the success audit entry while keeping the generic privacy-preserving `202` response. Codes are six-digit `secrets`-generated values stored only as password hashes, with expiry, attempt limits, resend cooldown and one-time use retained.
- SMTP settings are `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME` (legacy alias `SMTP_USER`), `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` and `SMTP_USE_TLS`; none are hardcoded and `.env` remains untracked. `.env.example` records the defaults (`SMTP_PORT=587`, `SMTP_FROM_EMAIL=no-reply@meddatahub.local`, `SMTP_USE_TLS=true`, `OTP_TTL_SECONDS=600`, `OTP_MAX_ATTEMPTS=5`, `OTP_REQUEST_COOLDOWN_SECONDS=60`).
- Alembic autogenerate now compares server defaults and explicitly registers both MedDataHub and SynthMed models in the migration metadata. The verified head is `a1f4d7e9c2b6`, parented on `f6b2c9d4e7a1`; revision `a1f4d7e9c2b6` aligns the ETL unique index and adds the SynthMed generation status index, while earlier SynthMed revisions already carry the server defaults and `uq_synthmed_config_job` constraint. Model-side server defaults were aligned to those revisions rather than adding redundant migrations. Tests cover the revision graph, upgrade to head, schema parity, no-drift `check`, upgrade/downgrade round trip and data preservation on temporary SQLite databases.
- The SynthMed worker remains a single-process in-memory executor, not a durable queue. A process crash can interrupt active work; recovery converts stranded active jobs to a terminal `Failed` state with an `InterruptedJob` payload so users can resubmit. Recovery is configurable (`SYNTHMED_STALE_JOB_RECOVERY_ENABLED=true`, `SYNTHMED_STALE_JOB_AFTER_SECONDS=0` by default), idempotent, conditional on the job still being active, and skips terminal jobs. Recovery failures are logged and startup continues. Shutdown stops submissions, awaits running tasks, logs executor errors and disposes the database engine last.

## Verification record

| Check | Command | Result |
| --- | --- | --- |
| Backend lint | `ruff check .` from `backend` | All checks passed |
| Backend tests | `& 'backend\.venv\Scripts\python.exe' -m pytest backend/tests -q` | 71 passed |
| Alembic upgrade/downgrade/model check | `alembic upgrade head`, `alembic downgrade -1`, `alembic check` | Passed on temporary SQLite databases |
| OpenAPI paths | `app.openapi()['paths']` required-path assertion | Passed |
| TypeScript strict check | `npm run typecheck` | Passed |
| Production build | `npm run build` | Passed |
| Frontend tests | None configured | Not run |

Tests use synthetic CSV/XLSX/JSON fixtures only. No real patient data was used. The CTGAN end-to-end test uses a fictional clinical CSV and verifies upload → analysis → inline generation → preview → quality → privacy → downloads → report downloads → export → job history → source file preservation and audit logging.

## Known gaps and risks

- Quality, readiness and representativeness scores are transparent rules, not clinically validated assessment instruments.
- No frontend unit/component or end-to-end test suite is configured; the ETL UI was typechecked and production-built but not browser-smoke-tested after the rewrite.
- Backend integration tests against a real MySQL instance are still absent; workflow tests use SQLite overrides.
- Readiness requires a configured and reachable MySQL instance in normal operation.
- SQLAlchemy must stay on 2.0.x until the 2.1 C-extension compatibility issue on Python 3.14/Windows is resolved.
- `npm audit` reports advisories in React Router 6; the available fix requires a major upgrade and should be handled separately.
- CTGAN training is CPU-bound and the UI is not browser-smoke-tested with a long-running production job.
- Privacy reports are nearest-neighbour screening signals; they do not provide differential privacy or anonymity guarantees.
- Processed outputs are staged behind governance approval; this prototype does not claim regulatory compliance.

## Recommended next step

Add frontend component tests for the ETL review and SynthMed generation flows, browser-smoke-test a long CPU job, and run a MySQL-backed integration pass over upload → profiling → decisions → approval → run → download and upload → CTGAN generation → evaluation → export before treating the pipeline as production-ready.
