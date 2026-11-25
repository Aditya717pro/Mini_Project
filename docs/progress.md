# Development progress

Last updated: 2026-11-25

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
| 18 | Two-option homepage and repository generation entry points | Complete | Homepage offers only SYNTHETIC and UPLOAD TO REPOSITORY; analytics retained; repository, dataset detail and version detail expose Generate Synthetic Data. |
| 19 | Single shared ETL ingestion path | Complete | Direct upload and generated upload converge on `create_upload`; generated files are resolved by ID server-side, validated, copied independently and queued as a real ETL job. |
| 20 | Automatic upload processing and white/blue UI | Complete | Upload now runs profile → mapping → approval → load automatically, polls real job state, returns home with an acknowledgement, and uses a white interface with blue accents. |
| 21 | Strict SynthMed source preservation | Complete | `sourcePreservingMode=true` now aligns each generated row to one source row in source order, preserves protected and numeric source values, reports record-level validation, and keeps internal row indices out of all outputs. |

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
- Alembic autogenerate compares server defaults and explicitly registers both MedDataHub and SynthMed models in the migration metadata. The current head is `d7f0a1b2c3e4_add_dataset_provenance`, parented on `c4e8f1a2b3d9_create_research_reports`; earlier revisions add utility evaluations and checksums, P5 versioning/experiments, conditional generation metadata, comparisons, schema drift reconciliation, generation jobs/configs/reports, SynthMed source/generated tables and ETL governance. The current head adds dataset origin, source lineage and provenance columns and is reversible via `alembic downgrade -1`. Tests cover the revision graph, upgrade to head, schema parity, no-drift `check`, upgrade/downgrade round trip and data preservation on temporary SQLite databases.
- The SynthMed worker remains a single-process in-memory executor, not a durable queue. A process crash can interrupt active work; recovery converts stranded active jobs to a terminal `Failed` state with an `InterruptedJob` payload so users can resubmit. Recovery is configurable (`SYNTHMED_STALE_JOB_RECOVERY_ENABLED=true`, `SYNTHMED_STALE_JOB_AFTER_SECONDS=0` by default), idempotent, conditional on the job still being active, and skips terminal jobs. Recovery failures are logged and startup continues. Shutdown stops submissions, awaits running tasks, logs executor errors and disposes the database engine last.

## Shared repository ingestion workflow

- The homepage has exactly two primary actions: `SYNTHETIC` and `UPLOAD TO REPOSITORY`; the analytics dashboard remains below them.
- SynthMed can prepare a source from a repository dataset or a specific repository version, or from a temporary source upload; temporary source files do not enter My Repository automatically.
- Repository list rows, dataset details and version details expose Generate Synthetic Data with the exact repository dataset ID and, where applicable, version ID.
- Generated datasets offer exactly PREVIEW, DOWNLOAD and UPLOAD actions. UPLOAD navigates to the Repository Upload page with the generated dataset ID; no client-supplied generated file path is accepted.
- Direct local uploads and generated uploads both call `create_upload` and create a `Queued` ETL job. The upload form automatically profiles, derives mapping decisions from suggestions, approves, runs, polls real job state and returns to the homepage with an acknowledgement; datasets remain behind governance review after ETL.
- Generated ingestion copies the stored synthetic file byte-for-byte into an independent repository raw file, verifies checksum/size/schema, preserves synthetic lineage metadata, and logs `synthmed.generated_ingestion_queued`. No hardlink, direct `Available` publication or self-approval path remains.
- Generated listings report `In Repository ETL` while a queued/in-flight repository record exists and `Registered in Repository` only after the repository dataset becomes `Available`.
- Upload progress is driven by real backend work; the previous timed `ProgressBar`, fake preview records and simulated generated registration ETL were removed. The automatic flow shows staged ETL state and failure/retry details while polling the real job.
- The default light theme keeps surfaces predominantly white, with navy blue (`#0b2545`) as the dark accent for text, primary controls, edges and borders; the existing dark theme remains selectable.

## Strict SynthMed source preservation

- `sourcePreservingMode=true` builds an internal source-row plan from the raw source file before model preparation; conditional jobs filter source rows by exact equality before repeating them in source order to `recordCount`.
- Each generated row is aligned to one planned source row: age, gender, disease and disease level are exact source values, and all approved numeric columns are restored from that row, so derived values such as BMI remain consistent with their source height and weight.
- `ageToleranceYears`, `numericTolerance`, `numericTolerancePercent` and per-column `numericTolerances` are accepted by generation and condition-validation APIs; the UI exposes the source-preserving toggle and age tolerance.
- Out-of-tolerance, missing or otherwise invalid model values are rejected and replaced from the aligned source row; restorations, rejected candidates, regeneration attempts and numeric violations are reported. No silent clipping, zero-fill or fabricated replacement is used.
- Strict mode skips deduplication and truncation when `recordCount` exceeds available source rows; repeated rows are intentional and are reported as duplicates rather than being removed.
- Preview, CSV/XLSX/JSON downloads, alternate-format exports and the source-preservation report derive from the same validated frame, and internal `sourceRowIndex` values remain server-side only.
- The preservation report now records source/generated/selected counts, gender/age/disease/level mismatches, per-column numeric violations, missing/extra records, row-order mismatches, duplicate records, rejected records, regeneration attempts, status and numeric tolerances.
- The medical schema profile recognises unit-suffixed measurement aliases such as `glucose_mg_dl`; ambiguous measurements still require confirmation before clinical validation.

## Verification record

| Check | Command | Result |
| --- | --- | --- |
| Backend lint | `& "D:\Mini_Project\backend\.venv\Scripts\python.exe" -m ruff check backend/app backend/tests` from workspace root | All checks passed |
| Backend tests | `& "D:\Mini_Project\backend\.venv\Scripts\python.exe" -m pytest -o addopts="" -q backend/tests` | 266 passed in 330.54s; includes 6 strict source-preservation regressions |
| TypeScript strict check | `npm --prefix frontend run typecheck` | Passed |
| Production build | `npm --prefix frontend run build` | Passed |
| Browser test discovery | `npx playwright test --list` | 5 tests discovered across 3 specs |
| Browser tests | `$env:E2E_API_PORT='8019'; $env:E2E_WEB_PORT='5182'; $env:E2E_API_BASE_URL='http://127.0.0.1:5182/api/v1'; npx playwright test` | 5 passed in 1.1m; Chromium against a fresh migrated SQLite DB with real APIs |
| Alembic migration check | `$env:PYTHONPATH='.'; & "D:\Mini_Project\backend\.venv\Scripts\python.exe" -m alembic check` from `backend` | No new upgrade operations detected |
| Git diff check | `git diff --check` | Passed; only line-ending warnings |
| Performance spot check | 500-row PDF renderer with `tracemalloc` | 0.113s; 0.71 MiB traced peak; full suite slowest test 2.69s |

Tests use synthetic CSV/XLSX/JSON fixtures only. No real patient data was used. Generation end-to-end tests use fictional clinical CSVs and cover upload → analysis → model selection → unconditional/conditional generation → preview → quality/privacy/condition reports → downloads → report downloads → export → job history → source file preservation and audit logging. Research report tests cover all seven PDF types, checksum verification, ownership, redaction, privacy claim boundaries, immutable file-per-attempt storage and the browser report generation/download flow. Browser workflow tests now also cover the two homepage actions, direct file upload through the automatic shared ETL lifecycle, generated dataset UPLOAD routing through automatic ETL, homepage upload acknowledgement, repository-source CTGAN generation, shared generated ETL ingestion, lineage/provenance assertions, ETL status reporting and version-specific Generate Synthetic Data links.

## Known gaps and risks

- Quality, readiness and representativeness scores are transparent rules, not clinically validated assessment instruments.
- Playwright covers browser registration/login, research reports, the two-option homepage, both shared ETL entry points and the automatic upload path; no frontend component unit suite is configured and every ETL decision screen is not browser-tested individually.
- Automatic upload accepts profiling suggestions without an explicit reviewer decision screen; the manual ETL workflow remains available for governed review where direct human approval is required.
- Backend integration tests against a real MySQL instance are still absent; workflow tests use SQLite overrides.
- Readiness requires a configured and reachable MySQL instance in normal operation.
- SQLAlchemy must stay on 2.0.x until the 2.1 C-extension compatibility issue on Python 3.14/Windows is resolved.
- `npm audit` reports advisories in React Router 6; the available fix requires a major upgrade and should be handled separately.
- CTGAN/TVAE training is CPU-bound and the UI is not browser-smoke-tested with a long-running production job; browser tests set inline generation and use small fictional inputs.
- Condition satisfaction is measured from generated records, not clinical validity; it is separate from quality and privacy reports.
- Privacy reports are nearest-neighbour screening signals with a conditional-cohort limitation; they do not provide differential privacy or anonymity guarantees.
- Processed outputs are staged behind governance approval; this prototype does not claim regulatory compliance.

## Recommended next step

Add frontend component tests for the ETL review and SynthMed generation flows, browser-smoke-test a long CPU job, and run a MySQL-backed integration pass over upload → profiling → decisions → approval → run → download and upload → model selection → conditional generation → evaluation → export before treating the pipeline as production-ready.
