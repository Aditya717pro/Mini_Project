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
| 15 | SynthMed multi-model generation and reporting | Complete | Real SDV 2.2.0 CTGAN/TVAE/GaussianCopula jobs, previews, exports, SDMetrics quality and privacy-risk reports. |
| 16 | P0 audit remediation | Complete | Admin RBAC, worker recovery/shutdown, storage containment, fail-closed OTP and Alembic drift checks. |
| 17 | P2 conditional generation and model selection | Complete | Model capabilities/validation, exact-equality cohorts, condition satisfaction and comparison metadata. |

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

## SynthMed generation implementation

- Uploads source datasets into owner-scoped storage without modifying the original file.
- Generation analysis detects likely identifiers, column kinds, missingness and modelable columns; zero-modelable-column jobs fail with a clear message.
- SDV metadata is detected and validated before training; pandas datetime columns omit `datetime_format` to avoid SDV validation failures.
- Installed SDV is 2.2.0. CTGAN (`CTGANSynthesizer`), TVAE (`TVAESynthesizer`) and GaussianCopula (`GaussianCopulaSynthesizer`) support unconditional and conditional generation; one fitted synthesizer instance generates all records in a job.
- CTGAN/TVAE training runs on CPU with configurable epochs, batch size and seed; batch size is constrained to multiples of 10 between 20 and 10000.
- Job states are genuine backend states: `Queued`, `Preprocessing`, `Training`, `Generating`, `Validating`, `Evaluating`, `Completed` and `Failed`; failed jobs record an error message and traceback server-side.
- Generation excludes identifier-like categorical columns from modelling; numerical columns are not dropped solely for high uniqueness.
- Previews, CSV/XLSX/JSON downloads, alternate-format exports and JSON report downloads are owner-scoped.
- Quality reporting uses SDMetrics quality and diagnostics with per-property scores and details.
- Privacy reporting covers exact overlap, duplicate rows, nearest-neighbour similarity and explicit limitations, including conditional cohorts; no anonymity or differential privacy claim is made.

## P2 conditional generation

- Conditional sampling uses `sample_from_conditions` with `sdv.sampling.Condition` exact-equality conditions. CTGAN and TVAE use SDV reject sampling; GaussianCopula uses native conditioned Gaussian multivariate sampling.
- Range operators, missing/null values, primary keys and patient identifiers are rejected.
- Exact conditions on different columns with equal `numRows` are combined with AND; unequal `numRows` are separate cohorts whose values sum to `recordCount`.
- New endpoints expose model capabilities, dataset columns, condition validation (including the `/conditions/validate` alias), condition results for jobs and generated datasets, and a combined evaluation summary. Existing preview, download, quality, privacy and report endpoints are unchanged.
- Condition satisfaction is computed from generated records and stored as a separate `conditions` report, distinct from quality, privacy and clinical validity.
- The frontend exposes model selection, compatibility display, a conditional toggle, a condition builder, validation, actual job status, satisfaction/evaluation display and comparison metadata.

## P0 audit remediation

- Administrator access checks now use `UserRole.ADMINISTRATOR` in MedDataHub datasets and SynthMed generation jobs, and administrators list all generation jobs without owning them.
- SynthMed startup recovery marks stranded active jobs as `Failed` with an `InterruptedJob` error and audit entry; recovery is idempotent, configurable and safe to disable in tests.
- API shutdown stops accepting new executor submissions, awaits running work, logs shutdown failures and disposes the database engine last. No durable queue was introduced.
- Stored file paths are resolved through a shared containment helper. Absolute legacy paths are accepted only inside the correct root; traversal, symlink escapes, cross-category paths and directories are rejected with controlled 404 responses before ETL, readiness, analysis, preview, export or download work begins.
- New dataset and ETL file persistence uses normalised relative paths; old absolute paths remain readable when contained. Internal filesystem paths are not returned in API responses.
- Password reset delivery is fail-closed: configuration is checked before user lookup, an unconfigured SMTP service returns `503` and creates no OTP, and a delivery failure rolls back the OTP and the success audit entry while keeping the generic privacy-preserving `202` response. Codes are six-digit `secrets`-generated values stored only as password hashes, with expiry, attempt limits, resend cooldown and one-time use retained.
- SMTP settings are `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME` (legacy alias `SMTP_USER`), `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` and `SMTP_USE_TLS`; none are hardcoded and `.env` remains untracked. `.env.example` records the defaults (`SMTP_PORT=587`, `SMTP_FROM_EMAIL=no-reply@meddatahub.local`, `SMTP_USE_TLS=true`, `OTP_TTL_SECONDS=600`, `OTP_MAX_ATTEMPTS=5`, `OTP_REQUEST_COOLDOWN_SECONDS=60`).
- Alembic autogenerate compares server defaults and explicitly registers both MedDataHub and SynthMed models in the migration metadata. The current head is `b2f6d8a9c1e3_add_conditional_generation`, parented on `c74e9b1a6d02_add_synthmed_comparisons`; earlier revisions include `a1f4d7e9c2b6` (schema drift reconciliation), `f6b2c9d4e7a1` (generation jobs/configs/reports), `d4a8c1f0b2e3` (source/generated tables) and `b7c4e1d9a3f2` (ETL governance). The new head adds generation mode and selected model to jobs and generated datasets, plus normalized conditions, condition validation and satisfaction metadata to jobs, and is reversible via `alembic downgrade -1`. Tests cover the revision graph, upgrade to head, schema parity, no-drift `check`, upgrade/downgrade round trip and data preservation on temporary SQLite databases.
- The SynthMed worker remains a single-process in-memory executor, not a durable queue. A process crash can interrupt active work; recovery converts stranded active jobs to a terminal `Failed` state with an `InterruptedJob` payload so users can resubmit. Recovery is configurable (`SYNTHMED_STALE_JOB_RECOVERY_ENABLED=true`, `SYNTHMED_STALE_JOB_AFTER_SECONDS=0` by default), idempotent, conditional on the job still being active, and skips terminal jobs. Recovery failures are logged and startup continues. Shutdown stops submissions, awaits running tasks, logs executor errors and disposes the database engine last.

## Verification record

| Check | Command | Result |
| --- | --- | --- |
| Backend lint | `ruff check .` from `backend` | All checks passed |
| Backend tests | `& 'backend\.venv\Scripts\python.exe' -m pytest backend/tests -q` | 85 passed |
| TypeScript strict check | `npm run typecheck` | Passed |
| Production build | `npm run build` | Passed |
| Frontend tests | None configured | Not run |
| Alembic migration check | `alembic current`, `alembic check`, `pytest tests/test_migrations.py -q` | At head `b2f6d8a9c1e3`; no drift; 4 migration tests passed |
| Git diff check | Separate diff review | To be checked separately |

Tests use synthetic CSV/XLSX/JSON fixtures only. No real patient data was used. Generation end-to-end tests use fictional clinical CSVs and cover upload → analysis → model selection → unconditional/conditional generation → preview → quality/privacy/condition reports → downloads → report downloads → export → job history → source file preservation and audit logging.

## Known gaps and risks

- Quality, readiness and representativeness scores are transparent rules, not clinically validated assessment instruments.
- No frontend unit/component or end-to-end test suite is configured; the ETL UI was typechecked and production-built but not browser-smoke-tested after the rewrite.
- Backend integration tests against a real MySQL instance are still absent; workflow tests use SQLite overrides.
- Readiness requires a configured and reachable MySQL instance in normal operation.
- SQLAlchemy must stay on 2.0.x until the 2.1 C-extension compatibility issue on Python 3.14/Windows is resolved.
- `npm audit` reports advisories in React Router 6; the available fix requires a major upgrade and should be handled separately.
- CTGAN/TVAE training is CPU-bound and the UI is not browser-smoke-tested with a long-running production job.
- Condition satisfaction is measured from generated records, not clinical validity; it is separate from quality and privacy reports.
- Privacy reports are nearest-neighbour screening signals with a conditional-cohort limitation; they do not provide differential privacy or anonymity guarantees.
- Processed outputs are staged behind governance approval; this prototype does not claim regulatory compliance.

## Recommended next step

Add frontend component tests for the ETL review and SynthMed generation flows, browser-smoke-test a long CPU job, and run a MySQL-backed integration pass over upload → profiling → decisions → approval → run → download and upload → model selection → conditional generation → evaluation → export before treating the pipeline as production-ready.
