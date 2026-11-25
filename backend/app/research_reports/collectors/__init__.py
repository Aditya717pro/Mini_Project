from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.research_reports import constants
from app.research_reports.collectors import (
    comparison,
    dataset_profile,
    etl,
    experiment,
    generation,
    privacy,
    utility,
)
from app.research_reports.validation import ResolvedSources

COLLECTORS: dict[str, Callable[[Session, Settings, ResolvedSources], dict[str, Any]]] = {
    constants.DATASET_PROFILE: dataset_profile.collect,
    constants.ETL: etl.collect,
    constants.SYNTHETIC_GENERATION: generation.collect,
    constants.COMPARISON: comparison.collect,
    constants.PRIVACY: privacy.collect,
    constants.UTILITY: utility.collect,
    constants.EXPERIMENT: experiment.collect,
}


def collect_data(db: Session, settings: Settings, sources: ResolvedSources) -> dict[str, Any]:
    collector = COLLECTORS.get(sources.report_type)
    if collector is None:
        raise ValueError(f"No collector registered for {sources.report_type}")
    return collector(db, settings, sources)
