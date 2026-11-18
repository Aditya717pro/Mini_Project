from __future__ import annotations

import csv
import os
import random
import secrets
from dataclasses import dataclass
from datetime import date, timedelta
from io import StringIO

from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.access import AccessRequest
from app.models.dataset import Dataset
from app.models.enums import AccessClassification, DatasetStatus, UserRole
from app.models.user import User
from app.schemas.dataset import DatasetMetadataInput
from app.schemas.etl import MappingDecisionInput
from app.services.dataset_service import approve_dataset
from app.services.etl_service import run_etl
from app.services.mapping_service import approve_mappings, record_mapping_decisions
from app.services.profiling_service import profile_job
from app.services.upload_service import create_upload


@dataclass(frozen=True)
class SeedAccount:
    key: str
    email: str
    full_name: str
    role: UserRole
    organisation: str
    title: str


@dataclass(frozen=True)
class SeedDataset:
    title: str
    description: str
    domain: str
    access: AccessClassification
    tags: tuple[str, ...]
    age_range: str
    geography: tuple[str, ...]
    study_design: str
    license: str
    intended_tasks: tuple[str, ...]
    label_column: str
    research_task: str
    collection_period: str
    rows: int
    headers: tuple[str, ...]


ACCOUNTS = (
    SeedAccount(
        key="admin",
        email="admin@meddatahub.local",
        full_name="Dr. Amara Okafor",
        role=UserRole.ADMINISTRATOR,
        organisation="MedDataHub Governance",
        title="Data Governance Lead",
    ),
    SeedAccount(
        key="contributor",
        email="contributor@meddatahub.local",
        full_name="Dr. Priya Raman",
        role=UserRole.CONTRIBUTOR,
        organisation="Northbridge Women's Health Institute",
        title="Clinical Data Lead",
    ),
    SeedAccount(
        key="researcher",
        email="researcher@meddatahub.local",
        full_name="Dr. Elena Fischer",
        role=UserRole.RESEARCHER,
        organisation="University of Helsinki",
        title="Perinatal Epidemiologist",
    ),
)

DATASETS = (
    SeedDataset(
        title="Maternal Antenatal Cohort 2019-2024",
        description=(
            "Synthetic antenatal follow-up records for testing maternal risk prediction workflows. "
            "All rows are generated for development and contain no real patient information."
        ),
        domain="Maternal & neonatal",
        access=AccessClassification.CONTROLLED,
        tags=("antenatal", "maternal", "synthetic"),
        age_range="18-45",
        geography=("Finland", "Kenya"),
        study_design="Prospective cohort",
        license="CC BY 4.0",
        intended_tasks=("Risk prediction", "Cohort description"),
        label_column="outcome",
        research_task="Predict adverse maternal outcome from antenatal measurements",
        collection_period="2019-2024",
        rows=60,
        headers=(
            "participant_id",
            "age_years",
            "sex",
            "region",
            "gestational_age_weeks",
            "weight_kg",
            "height_cm",
            "visit_date",
            "outcome",
        ),
    ),
    SeedDataset(
        title="Paediatric Growth Surveillance",
        description=(
            "Synthetic growth-monitoring measurements for paediatric model development. "
            "Generated values only; not suitable for clinical decision-making."
        ),
        domain="Paediatric health",
        access=AccessClassification.CONTROLLED,
        tags=("paediatric", "growth", "synthetic"),
        age_range="0-17",
        geography=("Norway", "Sweden"),
        study_design="Repeated cross-sectional",
        license="CC BY-NC 4.0",
        intended_tasks=("Growth anomaly detection", "Model benchmarking"),
        label_column="outcome",
        research_task="Detect growth anomalies from routine paediatric measurements",
        collection_period="2020-2024",
        rows=45,
        headers=(
            "participant_id",
            "age_years",
            "sex",
            "region",
            "weight_kg",
            "height_cm",
            "visit_date",
            "outcome",
        ),
    ),
    SeedDataset(
        title="Adolescent Wellbeing Survey",
        description=(
            "Synthetic survey extract covering adolescent wellbeing indicators. "
            "Missing values and duplicate rows are retained to exercise quality review."
        ),
        domain="Adolescent health",
        access=AccessClassification.OPEN,
        tags=("adolescent", "survey", "wellbeing", "synthetic"),
        age_range="12-19",
        geography=("Denmark",),
        study_design="Cross-sectional survey",
        license="CC0 1.0",
        intended_tasks=("Exploratory analysis", "Survey methods teaching"),
        label_column="outcome",
        research_task="Explore wellbeing indicators across adolescent age bands",
        collection_period="2022-2024",
        rows=50,
        headers=(
            "participant_id",
            "age_years",
            "sex",
            "region",
            "height_cm",
            "visit_date",
            "outcome",
        ),
    ),
)


def _password_for(key: str) -> tuple[str, bool]:
    env_key = f"SEED_{key.upper()}_PASSWORD"
    value = os.environ.get(env_key)
    if value:
        return value, False
    return secrets.token_urlsafe(18), True


def _ensure_accounts(db, settings: Settings) -> tuple[dict[str, User], list[tuple[str, str]]]:
    users: dict[str, User] = {}
    generated: list[tuple[str, str]] = []
    for account in ACCOUNTS:
        user = db.scalar(select(User).where(User.email == account.email))
        if user is None:
            password, is_generated = _password_for(account.key)
            user = User(
                email=account.email,
                full_name=account.full_name,
                hashed_password=hash_password(password),
                role=account.role,
                organisation=account.organisation,
                title=account.title,
            )
            db.add(user)
            db.flush()
            if is_generated:
                generated.append((account.email, password))
        users[account.key] = user
    db.commit()
    return users, generated


def _synthetic_csv(spec: SeedDataset, seed: int) -> bytes:
    rng = random.Random(seed)
    regions = ("Central", "North", "South", "East")
    outcomes = ("stable", "improved", "review", "adverse")
    rows: list[list[str]] = []
    start = date(2021, 1, 4)
    for index in range(spec.rows):
        age = 16 + (index % 28) if "Maternal" in spec.title else 2 + (index % 16)
        row = []
        for header in spec.headers:
            if header == "participant_id":
                row.append(f"SYN-{seed}-{index + 1:04d}")
            elif header == "age_years":
                row.append(str(age) if index % 17 else "")
            elif header == "sex":
                row.append("Female" if index % 3 else "Male")
            elif header == "region":
                row.append(regions[index % len(regions)])
            elif header == "gestational_age_weeks":
                row.append(str(8 + (index * 3) % 33))
            elif header == "weight_kg":
                row.append(f"{52 + (index * 7) % 45 + rng.random():.1f}")
            elif header == "height_cm":
                row.append(f"{145 + (index * 5) % 40 + rng.random():.1f}" if index % 13 else "")
            elif header == "visit_date":
                row.append((start + timedelta(days=index * 9)).isoformat())
            elif header == "outcome":
                row.append(outcomes[index % len(outcomes)])
            else:
                row.append("")
        rows.append(row)
    if len(rows) > 5:
        rows[-1] = rows[1].copy()
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(spec.headers)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _metadata(spec: SeedDataset) -> DatasetMetadataInput:
    return DatasetMetadataInput(
        title=spec.title,
        description=spec.description,
        domain=spec.domain,
        access=spec.access,
        tags=list(spec.tags),
        age_range=spec.age_range,
        geography=list(spec.geography),
        study_design=spec.study_design,
        license=spec.license,
        ethics_approved=True,
        data_dictionary_available=True,
        intended_tasks=list(spec.intended_tasks),
        label_column=spec.label_column,
        research_task=spec.research_task,
    )


def _seed_datasets(db, settings: Settings, owner: User, admin: User) -> list[Dataset]:
    created: list[Dataset] = []
    for index, spec in enumerate(DATASETS):
        existing = db.scalar(select(Dataset).where(Dataset.title == spec.title))
        if existing is not None:
            created.append(existing)
            continue
        dataset, job = create_upload(
            db,
            settings=settings,
            user=owner,
            filename=f"{spec.title.lower().replace(' ', '-')}.csv",
            content=_synthetic_csv(spec, seed=index + 1),
            metadata=_metadata(spec),
            request=None,
        )
        dataset.metadata_record.collection_period = spec.collection_period
        db.commit()
        profile_job(db, settings=settings, job=job)
        decisions = [
            MappingDecisionInput(
                source=str(item["source"]),
                decision="Approved" if item.get("target") else "Unmapped",
                target=str(item["target"]) if item.get("target") else None,
                note="Synthetic seed dataset mapping.",
            )
            for item in job.suggested_mapping_json or []
        ]
        record_mapping_decisions(db, job=job, decisions=decisions, actor=owner)
        approve_mappings(
            db,
            job=job,
            actor=admin,
            note="Synthetic seed dataset approved for development use.",
        )
        run_etl(
            db,
            settings=settings,
            job=job,
            actor=owner,
            approved_mapping=dict(job.approved_mapping_json or {}),
            research_task=spec.research_task,
            request=None,
        )
        db.refresh(dataset)
        approve_dataset(db, dataset, admin, "Synthetic seed dataset approved for development use.")
        db.commit()
        db.refresh(dataset)
        if dataset.status != DatasetStatus.AVAILABLE:
            dataset.status = DatasetStatus.AVAILABLE
            db.commit()
        created.append(dataset)
    return created


def _seed_access_request(db, datasets: list[Dataset], researcher: User) -> None:
    if not datasets:
        return
    target = datasets[0]
    existing = db.scalar(
        select(AccessRequest).where(
            AccessRequest.dataset_id == target.id,
            AccessRequest.requester_id == researcher.id,
        )
    )
    if existing is not None:
        return
    db.add(
        AccessRequest(
            dataset_id=target.id,
            requester_id=researcher.id,
            project_title="Synthetic perinatal risk model validation",
            purpose=(
                "Validate a synthetic-data-only prediction workflow and document known limitations. "
                "No real patient records are requested."
            ),
        )
    )
    db.commit()


def main() -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        users, generated = _ensure_accounts(db, settings)
        datasets = _seed_datasets(db, settings, users["contributor"], users["admin"])
        _seed_access_request(db, datasets, users["researcher"])
        print(f"Seed complete: {len(users)} accounts, {len(datasets)} synthetic datasets.")
        for email, password in generated:
            print(f"Generated password for {email}: {password}")
        if generated:
            print("Store these passwords securely. They are shown only once.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
