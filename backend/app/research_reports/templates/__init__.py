from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.research_reports import constants
from app.research_reports.templates import comparison, dataset_profile, etl, experiment, generation, privacy, utility

BUILDERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    constants.DATASET_PROFILE: dataset_profile.build,
    constants.ETL: etl.build,
    constants.SYNTHETIC_GENERATION: generation.build,
    constants.COMPARISON: comparison.build,
    constants.PRIVACY: privacy.build,
    constants.UTILITY: utility.build,
    constants.EXPERIMENT: experiment.build,
}


def build_payload(data: dict[str, Any]) -> Any:
    report_type = str(data.get("report_type") or "")
    builder = BUILDERS.get(report_type)
    if builder is None:
        raise ValueError(f"No report template registered for {report_type}")
    return builder(data)
