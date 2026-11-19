from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import pandas as pd
from sdmetrics.reports import DiagnosticReport, QualityReport
from sdmetrics.single_table import NewRowSynthesis
from sklearn.impute import SimpleImputer
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.synthmed.services.dataset_service import TABLE_NAME, json_safe


def _frame_properties(report: Any) -> dict[str, float]:
    properties = report.get_properties()
    if isinstance(properties, pd.DataFrame):
        rows = properties.to_dict(orient="records")
    else:
        rows = list(properties)
    scores: dict[str, float] = {}
    for row in rows:
        name = row.get("Property") if isinstance(row, dict) else None
        score = row.get("Score") if isinstance(row, dict) else None
        if name and score is not None:
            scores[str(name)] = json_safe(float(score))
    return scores


def _details(report: Any, *args: Any) -> list[dict[str, Any]]:
    try:
        details = report.get_details(*args)
    except Exception:
        try:
            details = report.get_details(table_name=TABLE_NAME)
        except Exception:
            return []
    if isinstance(details, pd.DataFrame):
        return json_safe(details.to_dict(orient="records"))
    return json_safe(details)


def build_quality_report(
    real_data: pd.DataFrame, synthetic_data: pd.DataFrame, metadata_dict: dict[str, Any]
) -> dict[str, Any]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        quality = QualityReport()
        quality.generate(
            {TABLE_NAME: real_data},
            {TABLE_NAME: synthetic_data},
            metadata_dict,
            verbose=False,
        )
        diagnostic = DiagnosticReport()
        diagnostic.generate(
            {TABLE_NAME: real_data},
            {TABLE_NAME: synthetic_data},
            metadata_dict,
            verbose=False,
        )
        quality_properties = _frame_properties(quality)
        diagnostic_properties = _frame_properties(diagnostic)
        column_level = _details(quality, "Column Shapes", TABLE_NAME)
        pair_level = _details(quality, "Column Pair Trends", TABLE_NAME)
        diagnostic_details: list[dict[str, Any]] = []
        for property_name in diagnostic_properties:
            for detail in _details(diagnostic, property_name, TABLE_NAME):
                row = dict(detail) if isinstance(detail, dict) else {"detail": detail}
                row["Property"] = property_name
                diagnostic_details.append(row)

        return {
            "method": "SDMetrics QualityReport and DiagnosticReport",
            "overallQualityScore": json_safe(quality.get_score()),
            "diagnosticScore": json_safe(diagnostic.get_score()),
            "propertyScores": json_safe(quality_properties),
            "diagnosticProperties": json_safe(diagnostic_properties),
            "columnLevel": column_level,
            "columnPairLevel": pair_level,
            "diagnostics": diagnostic_details,
            "explanations": {
                "overallQualityScore": (
                    "Average of SDMetrics column-shape and column-pair similarity scores; "
                    "1.0 is the closest match."
                ),
                "diagnosticScore": "Share of SDMetrics validity checks passed; 1.0 means all configured checks passed.",
                "columnLevel": "Per-column distribution similarity against the uploaded source data.",
                "columnPairLevel": "Pairwise correlation or association similarity against the uploaded source data.",
                "diagnostics": "Data validity diagnostics such as boundary and schema checks.",
            },
            "limitations": [
                "Statistical similarity does not mean the synthetic data is clinically valid.",
                "Scores are computed only over the columns and transformations used for training.",
            ],
        }


def _encoded_matrices(
    real_frame: pd.DataFrame,
    synthetic_frame: pd.DataFrame,
    numeric: list[str],
    categorical: list[str],
) -> tuple[np.ndarray, np.ndarray]:
    real_blocks: list[np.ndarray] = []
    synthetic_blocks: list[np.ndarray] = []
    if numeric:
        real_values = real_frame[numeric].apply(pd.to_numeric, errors="coerce")
        synthetic_values = synthetic_frame[numeric].apply(pd.to_numeric, errors="coerce")
        imputer = SimpleImputer(strategy="median", add_indicator=True).fit(real_values)
        scaler = StandardScaler().fit(imputer.transform(real_values))
        real_numeric = np.nan_to_num(
            scaler.transform(imputer.transform(real_values)), nan=0.0, posinf=0.0, neginf=0.0
        )
        synthetic_numeric = np.nan_to_num(
            scaler.transform(imputer.transform(synthetic_values)), nan=0.0, posinf=0.0, neginf=0.0
        )
        real_blocks.append(np.asarray(real_numeric, dtype=float))
        synthetic_blocks.append(np.asarray(synthetic_numeric, dtype=float))
    if categorical:
        real_values = real_frame[categorical].astype("string").fillna("__MISSING__")
        synthetic_values = synthetic_frame[categorical].astype("string").fillna("__MISSING__")
        encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False).fit(real_values)
        real_blocks.append(np.asarray(encoder.transform(real_values), dtype=float))
        synthetic_blocks.append(np.asarray(encoder.transform(synthetic_values), dtype=float))
    if not real_blocks:
        return (
            np.zeros((len(real_frame), 1), dtype=float),
            np.zeros((len(synthetic_frame), 1), dtype=float),
        )
    return np.hstack(real_blocks), np.hstack(synthetic_blocks)


def build_privacy_report(
    real_data: pd.DataFrame,
    synthetic_data: pd.DataFrame,
    metadata_dict: dict[str, Any],
    analysis: dict[str, Any],
    seed: int | None = None,
) -> dict[str, Any]:
    shared_columns = [column for column in real_data.columns if column in synthetic_data.columns]
    real_rows = set(real_data[shared_columns].astype("string").fillna("__NA__").itertuples(index=False, name=None))
    synthetic_rows = list(
        synthetic_data[shared_columns].astype("string").fillna("__NA__").itertuples(index=False, name=None)
    )
    exact_overlap = sum(1 for row in synthetic_rows if row in real_rows)
    synthetic_duplicates = len(synthetic_rows) - len(set(synthetic_rows))

    numeric = [column for column in shared_columns if pd.api.types.is_numeric_dtype(real_data[column])]
    categorical = [column for column in shared_columns if column not in numeric]
    real_encoded, synthetic_encoded = _encoded_matrices(
        real_data[shared_columns], synthetic_data[shared_columns], numeric, categorical
    )

    neighbours = NearestNeighbors(n_neighbors=1, algorithm="auto").fit(real_encoded)
    distances, _ = neighbours.kneighbors(synthetic_encoded)
    flat = np.asarray(distances).reshape(-1)
    finite = flat[np.isfinite(flat)]
    threshold = 0.05
    suspicious = int((finite < threshold).sum()) if finite.size else 0

    new_row_score: float | None = None
    new_row_error: str | None = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            new_row_score = json_safe(
                float(
                    NewRowSynthesis.compute(
                        real_data=real_data[shared_columns],
                        synthetic_data=synthetic_data[shared_columns],
                        metadata=metadata_dict["tables"][TABLE_NAME],
                    )
                )
            )
    except Exception as error:
        new_row_error = str(error)

    warnings_list: list[str] = []
    if exact_overlap:
        warnings_list.append(
            f"{exact_overlap} synthetic record(s) exactly match uploaded source records under modelled columns."
        )
    if suspicious:
        warnings_list.append(
            f"{suspicious} synthetic record(s) are unusually close to an uploaded source record under the "
            f"encoded {threshold} nearest-neighbour threshold."
        )
    if synthetic_duplicates:
        warnings_list.append(f"{synthetic_duplicates} duplicate synthetic record(s) were generated.")
    warnings_list.append("Synthetic medical data is not automatically anonymous.")

    return {
        "method": "Exact overlap, duplicate detection, nearest-neighbour distance and SDMetrics NewRowSynthesis",
        "exactOverlapRecords": exact_overlap,
        "exactOverlapPercentage": round(exact_overlap / len(synthetic_rows) * 100, 2) if synthetic_rows else 0.0,
        "syntheticDuplicateRecords": synthetic_duplicates,
        "realDuplicateRecords": int(analysis.get("duplicateRecords", 0)),
        "nearestNeighbourDistance": {
            "minimum": json_safe(float(finite.min())) if finite.size else None,
            "median": json_safe(float(np.median(finite))) if finite.size else None,
            "p90": json_safe(float(np.percentile(finite, 90))) if finite.size else None,
            "threshold": threshold,
            "suspiciousRecords": suspicious,
        },
        "newRowSynthesisScore": new_row_score,
        "newRowSynthesisError": new_row_error,
        "riskyColumns": {
            "identifiers": analysis.get("potentialIdentifierColumns", []),
            "quasiIdentifiers": analysis.get("quasiIdentifierColumns", []),
        },
        "warnings": warnings_list,
        "limitations": [
            "This is a heuristic screening, not a formal privacy guarantee.",
            "No differential privacy mechanism is implemented.",
            "A low re-identification signal does not prove that re-identification is impossible.",
            "Nearest-neighbour distances use a scale-normalised encoding of modelled columns only.",
        ],
    }
