from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dataset import Dataset, DatasetVersion
from app.models.enums import UserRole
from app.models.etl import ETLJob
from app.models.user import User
from app.research_reports.constants import (
    COMPARISON,
    DATASET_PROFILE,
    ETL,
    EXPERIMENT,
    PRIVACY,
    SYNTHETIC_GENERATION,
    UTILITY,
)
from app.synthmed.models import (
    SynthMedComparison,
    SynthMedDatasetVersion,
    SynthMedEvaluationReport,
    SynthMedExperiment,
    SynthMedGeneratedDataset,
    SynthMedGenerationJob,
    SynthMedUtilityEvaluation,
)
from app.synthmed.services import comparison_service, experiment_service, generation_service, source_service


@dataclass
class ResolvedSources:
    report_type: str
    dataset: Dataset | None = None
    dataset_version: DatasetVersion | None = None
    synth_source: Any | None = None
    synth_version: SynthMedDatasetVersion | None = None
    etl_job: ETLJob | None = None
    generation_job: SynthMedGenerationJob | None = None
    generated_dataset: SynthMedGeneratedDataset | None = None
    comparison: SynthMedComparison | None = None
    privacy_evaluation: SynthMedEvaluationReport | None = None
    utility_evaluation: SynthMedUtilityEvaluation | None = None
    experiment: SynthMedExperiment | None = None

    def reference_values(self) -> dict[str, str]:
        dataset_ref = self.dataset.id if self.dataset else self.synth_source.id if self.synth_source else ""
        version_ref = (
            self.dataset_version.id
            if self.dataset_version
            else self.synth_version.id if self.synth_version else ""
        )
        return {
            "datasetId": dataset_ref,
            "datasetVersionId": version_ref,
            "etlJobId": self.etl_job.id if self.etl_job else "",
            "generationJobId": self.generation_job.id if self.generation_job else "",
            "generatedDatasetId": self.generated_dataset.id if self.generated_dataset else "",
            "comparisonId": self.comparison.id if self.comparison else "",
            "privacyEvaluationId": self.privacy_evaluation.id if self.privacy_evaluation else "",
            "utilityEvaluationId": self.utility_evaluation.id if self.utility_evaluation else "",
            "experimentId": self.experiment.id if self.experiment else "",
        }


def _require(value: str | None, label: str) -> str:
    if not value or not str(value).strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{label} is required for this report type.",
        )
    return str(value).strip()


def _ensure_owner(owner_id: str, user: User, label: str) -> None:
    if user.role != UserRole.ADMINISTRATOR and owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Not permitted to view this {label}.")


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else "NOT AVAILABLE"


def _core_dataset(db: Session, dataset_id: str, user: User) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    _ensure_owner(dataset.owner_id, user, "dataset")
    return dataset


def _core_version(db: Session, dataset: Dataset, version_id: str | None) -> DatasetVersion:
    if version_id:
        version = db.get(DatasetVersion, version_id)
        if version is None or version.dataset_id != dataset.id:
            raise HTTPException(status_code=422, detail="Dataset version does not belong to the selected dataset.")
        return version
    version = db.scalar(
        select(DatasetVersion)
        .where(DatasetVersion.dataset_id == dataset.id)
        .order_by(DatasetVersion.is_current.desc(), DatasetVersion.version_number.desc())
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Dataset version not found.")
    return version


def _synth_source(db: Session, dataset_id: str, user: User) -> Any:
    source = source_service.get_source(db, dataset_id)
    source_service.ensure_source_access(source, user)
    return source


def _synth_version(db: Session, source_id: str, version_id: str | None) -> SynthMedDatasetVersion | None:
    if version_id:
        version = db.get(SynthMedDatasetVersion, version_id)
        if version is None or version.logical_dataset_id != source_id or version.dataset_kind != "source":
            raise HTTPException(status_code=422, detail="Version does not belong to the selected source dataset.")
        return version
    return db.scalar(
        select(SynthMedDatasetVersion)
        .where(
            SynthMedDatasetVersion.dataset_kind == "source",
            SynthMedDatasetVersion.logical_dataset_id == source_id,
        )
        .order_by(SynthMedDatasetVersion.is_active.desc(), SynthMedDatasetVersion.version_number.desc())
    )


def _generated(db: Session, generated_id: str | None, user: User) -> SynthMedGeneratedDataset | None:
    if not generated_id:
        return None
    generated = source_service.get_generated(db, generated_id)
    source_service.ensure_generated_access(generated, user)
    return generated


def _privacy_evaluation(
    db: Session, evaluation_id: str | None, generated: SynthMedGeneratedDataset | None, user: User
) -> SynthMedEvaluationReport | None:
    if evaluation_id:
        row = db.get(SynthMedEvaluationReport, evaluation_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Privacy evaluation not found.")
        _ensure_owner(row.owner_id, user, "privacy evaluation")
        return row
    if generated is not None:
        return db.scalar(
            select(SynthMedEvaluationReport)
            .where(
                SynthMedEvaluationReport.generated_dataset_id == generated.id,
                SynthMedEvaluationReport.report_type == "privacy",
            )
            .order_by(SynthMedEvaluationReport.created_at.desc())
        )
    return None


def validate_sources(db: Session, *, user: User, report_type: str, refs: dict[str, str | None]) -> ResolvedSources:
    result = ResolvedSources(report_type=report_type)
    dataset_id = refs.get("datasetId")
    version_id = refs.get("datasetVersionId")

    if dataset_id and report_type in {DATASET_PROFILE, ETL}:
        dataset = db.get(Dataset, dataset_id)
        if dataset is not None:
            result.dataset = _core_dataset(db, dataset_id, user)
            result.dataset_version = _core_version(db, dataset, version_id)
        else:
            result.synth_source = _synth_source(db, dataset_id, user)
            result.synth_version = _synth_version(db, dataset_id, version_id)

    if report_type == ETL:
        etl_job_id = refs.get("etlJobId")
        if etl_job_id:
            job = db.get(ETLJob, etl_job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="ETL job not found.")
            _ensure_owner(job.initiated_by_id, user, "ETL job")
            result.etl_job = job
        elif result.dataset:
            result.etl_job = db.scalar(
                select(ETLJob).where(ETLJob.dataset_id == result.dataset.id).order_by(ETLJob.created_at.desc())
            )
        else:
            raise HTTPException(status_code=422, detail="etlJobId is required for SynthMed dataset sources.")

    if report_type == SYNTHETIC_GENERATION:
        generation_job_id = refs.get("generationJobId")
        if generation_job_id:
            result.generation_job = generation_service.get_job(db, generation_job_id, user)
            result.generated_dataset = result.generation_job.generated_dataset
        else:
            generated_id = _require(refs.get("generatedDatasetId"), "generatedDatasetId")
            result.generated_dataset = _generated(db, generated_id, user)
            result.generation_job = generation_service.job_for_generated(db, result.generated_dataset.id)
            if result.generation_job:
                _ensure_owner(result.generation_job.owner_id, user, "generation job")

    if report_type == COMPARISON:
        comparison_id = _require(refs.get("comparisonId"), "comparisonId")
        result.comparison = comparison_service.get_comparison(db, comparison_id, user)
        result.generated_dataset = result.comparison.generated_dataset

    if report_type == PRIVACY:
        generated_id = refs.get("generatedDatasetId")
        result.generated_dataset = _generated(db, generated_id, user)
        result.privacy_evaluation = _privacy_evaluation(
            db, refs.get("privacyEvaluationId"), result.generated_dataset, user
        )
        if result.privacy_evaluation is None:
            raise HTTPException(status_code=404, detail="No persisted privacy evaluation was found.")
        if result.generated_dataset is None:
            result.generated_dataset = db.get(SynthMedGeneratedDataset, result.privacy_evaluation.generated_dataset_id)

    if report_type == UTILITY:
        utility_id = _require(refs.get("utilityEvaluationId"), "utilityEvaluationId")
        result.utility_evaluation = db.get(SynthMedUtilityEvaluation, utility_id)
        if result.utility_evaluation is None:
            raise HTTPException(status_code=404, detail="Utility evaluation not found.")
        _ensure_owner(result.utility_evaluation.owner_id, user, "utility evaluation")
        result.generated_dataset = db.get(SynthMedGeneratedDataset, result.utility_evaluation.generated_dataset_id)

    if report_type == EXPERIMENT:
        experiment_id = _require(refs.get("experimentId"), "experimentId")
        result.experiment = experiment_service.get_experiment(db, user=user, experiment_id=experiment_id)
        result.generated_dataset = (
            db.get(SynthMedGeneratedDataset, result.experiment.generated_dataset_id)
            if result.experiment.generated_dataset_id
            else None
        )

    return result
