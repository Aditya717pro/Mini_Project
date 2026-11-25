"""Medical schema profiling for SynthMed.

This module identifies clinical columns, standardises names, detects units and
finds identifiers. It never assigns a clinical meaning to an unknown column and
never silently assumes a unit: ambiguous measurements are reported for
confirmation instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from app.synthmed.services.dataset_service import analyse_dataframe, json_safe

TABLE_NAME = "synthmed"

DEMOGRAPHIC_ALIASES: dict[str, tuple[str, ...]] = {
    "Age": ("age", "ages", "age_years", "ageyrs", "patient_age"),
    "Gender": ("gender", "sex", "sex_at_birth", "gender_identity"),
}

DISEASE_ALIASES: dict[str, tuple[str, ...]] = {
    "Disease": (
        "disease",
        "diagnosis",
        "diagnoses",
        "condition",
        "disease_name",
        "diagnosis_name",
        "primary_diagnosis",
    ),
    "Disease_Level": (
        "disease_level",
        "diseaselevel",
        "severity",
        "severity_level",
        "stage",
        "risk_level",
        "diagnosis_level",
    ),
}


@dataclass(frozen=True)
class MeasurementDefinition:
    canonical: str
    aliases: tuple[str, ...]
    units: tuple[str, ...]
    numerical: bool = True
    context: str = ""

    @property
    def all_names(self) -> tuple[str, ...]:
        return (self.canonical.lower(), *self.aliases)


MEASUREMENTS: tuple[MeasurementDefinition, ...] = (
    MeasurementDefinition(
        "Systolic_BP",
        ("sbp", "systolic", "systolicbp", "systolic_blood_pressure", "systolic_pressure"),
        ("mmHg",),
        context="resting",
    ),
    MeasurementDefinition(
        "Diastolic_BP",
        ("dbp", "diastolic", "diastolicbp", "diastolic_blood_pressure", "diastolic_pressure"),
        ("mmHg",),
        context="resting",
    ),
    MeasurementDefinition(
        "Blood_Glucose",
        (
            "bs",
            "glucose",
            "blood_glucose",
            "blood_sugar",
            "fasting_glucose",
            "random_glucose",
            "postprandial_glucose",
            "hba1c_glucose",
        ),
        ("mg/dL", "mmol/L"),
        context="Specify fasting, random or post-meal",
    ),
    MeasurementDefinition(
        "Heart_Rate", ("hr", "heart_rate", "pulse", "pulse_rate", "bpm_heart"), ("bpm",), context="resting"
    ),
    MeasurementDefinition(
        "Body_Temperature",
        ("temp", "temperature", "body_temp", "body_temperature", "temp_c", "temp_f"),
        ("°C", "°F"),
        context="measurement site and device",
    ),
    MeasurementDefinition(
        "SpO2",
        ("spo2", "oxygen_saturation", "o2_saturation", "oxygen_sat", "sao2"),
        ("%",),
        context="room air or supplemental oxygen",
    ),
    MeasurementDefinition(
        "Respiratory_Rate",
        ("rr", "respiratory_rate", "resp_rate", "breathing_rate"),
        ("breaths/min",),
        context="resting",
    ),
    MeasurementDefinition(
        "Haemoglobin",
        ("hemoglobin", "haemoglobin", "hb", "hgb"),
        ("g/dL", "g/L"),
        context="sex-specific reference required",
    ),
    MeasurementDefinition("BMI", ("bmi", "body_mass_index"), ("kg/m²",), context="adult"),
    MeasurementDefinition(
        "Total_Cholesterol", ("cholesterol", "total_cholesterol", "tc"), ("mg/dL", "mmol/L"), context="fasting"
    ),
    MeasurementDefinition(
        "HDL_Cholesterol", ("hdl", "hdl_cholesterol", "hdl_c"), ("mg/dL", "mmol/L"), context="fasting"
    ),
    MeasurementDefinition(
        "LDL_Cholesterol", ("ldl", "ldl_cholesterol", "ldl_c"), ("mg/dL", "mmol/L"), context="fasting"
    ),
    MeasurementDefinition(
        "Triglycerides", ("tg", "triglycerides", "triglyceride"), ("mg/dL", "mmol/L"), context="fasting"
    ),
    MeasurementDefinition(
        "Creatinine", ("creatinine", "serum_creatinine"), ("mg/dL", "µmol/L"), context="sex-specific reference required"
    ),
    MeasurementDefinition("Height", ("height", "height_cm", "height_m", "stature"), ("cm", "m"), context=""),
    MeasurementDefinition("Weight", ("weight", "weight_kg", "body_weight"), ("kg",), context=""),
)

MEASUREMENT_BY_NAME = {definition.canonical: definition for definition in MEASUREMENTS}

UNIT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"mm\s*hg", "mmHg"),
    (r"mg\s*/\s*dl", "mg/dL"),
    (r"mmol\s*/\s*l", "mmol/L"),
    (r"\bbpm\b|beats\s*/\s*min", "bpm"),
    (r"°\s*c|degrees?\s*celsius|\bcelsius\b|_c\b|\(c\)", "°C"),
    (r"°\s*f|degrees?\s*fahrenheit|\bfahrenheit\b|_f\b|\(f\)", "°F"),
    (r"kg\s*/\s*m\s*2|kg\s*/\s*m²|body_mass_index", "kg/m²"),
    (r"g\s*/\s*dl", "g/dL"),
    (r"g\s*/\s*l", "g/L"),
    (r"breaths?\s*/\s*min", "breaths/min"),
    (r"µ\s*mol\s*/\s*l|umol\s*/\s*l", "µmol/L"),
    (r"\bcm\b", "cm"),
    (r"\bkg\b", "kg"),
    (r"%|percent", "%"),
)

IDENTIFIER_NAME_PATTERN = re.compile(
    r"(^|[^a-z])("
    r"patient|patientid|mrn|nhs|ssn|uuid|guid|record|case|subject|member|"
    r"id|user_id|patient_id|medical_record|medicalrecord|"
    r"full_name|fullname|first_name|last_name|surname|name|doctor|hospital|"
    r"phone|mobile|telephone|contact|email|e_mail|address|street|house|housenumber|"
    r"building|flat|apartment|plot|door|city|district|state|pincode|postcode|zip|zipcode|"
    r"visit|encounter|admission|passport|license|licence|national_id|aadhaar|ic_number"
    r")([^a-z]|$)"
)

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_PATTERN = re.compile(r"(?:\+?\d[\d\s().-]{6,}\d)")
LONG_ID_PATTERN = re.compile(r"^(?:[A-Z]{1,4}[-_]?\d{4,}|\d{7,})$")


def _normalise_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


def _lookup_alias(name: str, groups: dict[str, tuple[str, ...]]) -> str:
    key = _normalise_name(name)
    for canonical, aliases in groups.items():
        if key in {_normalise_name(alias) for alias in aliases}:
            return canonical
    return ""


def _numeric_summary(series: pd.Series) -> dict[str, float | int | None]:
    numeric = pd.to_numeric(series, errors="coerce")
    finite = numeric[np.isfinite(numeric.to_numpy(dtype=float, na_value=np.nan))]
    if finite.empty:
        return {"count": 0, "min": None, "max": None, "median": None}
    values = finite.to_numpy(dtype=float)
    return {
        "count": int(values.size),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "median": float(np.median(values)),
    }


def _value_supports_measurement(measurement: str, series: pd.Series, unit: str) -> tuple[bool, str]:
    stats = _numeric_summary(series)
    if not stats["count"]:
        return True, "No numeric values available; name/unit evidence only."
    min_v = float(stats["min"])
    max_v = float(stats["max"])
    med = float(stats["median"])
    # Conservative plausibility envelopes; do not reject valid abnormal values.
    envelopes: dict[str, tuple[float, float]] = {
        "Systolic_BP": (40, 300),
        "Diastolic_BP": (20, 200),
        "Heart_Rate": (20, 300),
        "Respiratory_Rate": (4, 80),
        "SpO2": (50, 100),
        "Blood_Glucose": (20, 1000) if unit in {"mg/dL", ""} else (1, 60),
        "BMI": (8, 90),
        "Height": (30, 250) if unit in {"cm", ""} else (0.3, 2.5),
        "Weight": (1, 400),
        "Body_Temperature": (30, 45) if unit in {"°C", ""} else (85, 115),
        "Total_Cholesterol": (50, 800) if unit in {"mg/dL", ""} else (1, 20),
        "HDL_Cholesterol": (5, 200) if unit in {"mg/dL", ""} else (0.1, 6),
        "LDL_Cholesterol": (5, 500) if unit in {"mg/dL", ""} else (0.1, 15),
        "Triglycerides": (10, 2000) if unit in {"mg/dL", ""} else (0.1, 25),
        "Haemoglobin": (3, 25) if unit in {"g/dL", ""} else (30, 250),
        "Creatinine": (0.1, 20) if unit in {"mg/dL", ""} else (10, 2000),
    }
    if measurement not in envelopes:
        return True, "No value envelope configured."
    low, high = envelopes[measurement]
    if max_v < low or min_v > high:
        return False, (
            f"Observed values [{min_v:.3g}, {max_v:.3g}] outside plausible envelope "
            f"for {measurement} ({low}-{high} {unit or 'expected unit'})."
        )
    # Guard common confusions
    if measurement == "BMI" and med > 60 and unit in {"kg/m^2", "kg/m²", ""}:
        return False, "Median too high for BMI; column may be weight or another measure."
    if measurement in {"Height", "Weight"} and unit == "" and measurement == "Height" and med < 3:
        # likely meters, acceptable
        pass
    return True, f"Observed values [{min_v:.3g}, {max_v:.3g}] consistent with {measurement}."


def _mapping_confidence(
    *, name_match: bool, unit: str, unit_confidence: str, value_ok: bool, reason: str
) -> tuple[str, str]:
    if not name_match:
        return "Low", "No recognised name alias."
    if not value_ok:
        return "Rejected", reason
    if unit and unit_confidence == "From column name":
        return "High", "Name and explicit unit matched."
    if unit and unit_confidence in {"Inferred from observed values", "Typical unit for measurement"} and value_ok:
        return "Medium", f"Name matched; {unit_confidence.lower()}; values plausible."
    if value_ok:
        return (
            "Medium" if unit else "Low",
            "Name matched; values plausible but unit ambiguous."
            if not unit
            else "Name and values plausible.",
        )
    return "Low", reason


def standardise_name(column: str, series: pd.Series | None = None) -> tuple[str, str, str, dict[str, Any]]:
    """Return (standardised name, role, measurement key, mapping metadata).

    Mapping uses name, data type, unit hints and actual values. Unknown or ambiguous
    columns are never auto-approved as clinical measurements.
    """
    meta: dict[str, Any] = {
        "confidence": "Low",
        "reason": "Unrecognised column.",
        "unit": "",
        "unitConfidence": "Unknown",
    }
    demographic = _lookup_alias(column, DEMOGRAPHIC_ALIASES)
    if demographic:
        if series is not None and demographic == "Age":
            stats = _numeric_summary(series)
            if stats["count"] and (float(stats["min"]) < 0 or float(stats["max"]) > 130):
                return column, "Unclassified", "", {
                    "confidence": "Rejected",
                    "reason": "Age alias but values outside human age envelope.",
                    "unit": "",
                    "unitConfidence": "Not a measurement",
                }
        meta = {
            "confidence": "High",
            "reason": "Recognised demographic alias.",
            "unit": "",
            "unitConfidence": "Not a measurement",
        }
        return demographic, "Demographic", "", meta
    disease = _lookup_alias(column, DISEASE_ALIASES)
    if disease:
        meta = {
            "confidence": "High",
            "reason": "Recognised disease/severity alias.",
            "unit": "",
            "unitConfidence": "Not a measurement",
        }
        return disease, disease, "", meta

    key = _normalise_name(column)
    for definition in MEASUREMENTS:
        aliases = {_normalise_name(alias) for alias in definition.all_names}
        name_match = any(key == alias or key.startswith(f"{alias}_") for alias in aliases) or key.startswith(
            f"{_normalise_name(definition.canonical)}_"
        )
        if not name_match:
            continue
        unit, unit_confidence, _ = detect_unit(
            column,
            series if series is not None else pd.Series(dtype="float64"),
            definition.canonical,
        )
        value_ok, reason = _value_supports_measurement(
            definition.canonical,
            series if series is not None else pd.Series(dtype="float64"),
            unit,
        )
        confidence, map_reason = _mapping_confidence(
            name_match=name_match,
            unit=unit,
            unit_confidence=unit_confidence,
            value_ok=value_ok,
            reason=reason,
        )
        meta = {
            "confidence": confidence,
            "reason": map_reason,
            "unit": unit,
            "unitConfidence": unit_confidence,
            "valueCheck": reason,
        }
        if confidence == "Rejected":
            return column, "Unclassified", "", meta
        # Ambiguous unit measurements are mapped but require confirmation before clinical validation.
        return definition.canonical, "ClinicalMeasurement", definition.canonical, meta
    return column, "Unclassified", "", meta


def detect_identifier_name(column: str) -> bool:
    key = _normalise_name(column)
    return bool(IDENTIFIER_NAME_PATTERN.search(f"_{key}_"))


def detect_identifier_content(series: pd.Series) -> tuple[bool, str]:
    values = series.dropna().astype(str).str.strip()
    values = values[values != ""]
    if values.empty:
        return False, ""
    sample = values.head(200)
    email_share = sample.str.match(EMAIL_PATTERN).mean()
    if email_share >= 0.1:
        return True, "email_address_pattern"
    phone_share = sample.str.match(PHONE_PATTERN).mean()
    if phone_share >= 0.4:
        return True, "phone_number_pattern"
    id_share = sample.str.match(LONG_ID_PATTERN).mean()
    if id_share >= 0.5:
        return True, "identifier_like_token_pattern"
    return False, ""


def detect_unit(column: str, series: pd.Series, measurement: str) -> tuple[str, str, bool]:
    """Return (unit, confidence, requires_confirmation)."""
    key = str(column).lower().replace(" ", "_")
    for pattern, unit in UNIT_PATTERNS:
        if re.search(pattern, key):
            return unit, "From column name", False
    definition = MEASUREMENT_BY_NAME.get(measurement)
    if measurement == "Body_Temperature":
        numeric = pd.to_numeric(series, errors="coerce").dropna()
        if not numeric.empty:
            median = float(numeric.median())
            if 33 <= median <= 43:
                return "°C", "Inferred from observed values", True
            if 92 <= median <= 110:
                return "°F", "Inferred from observed values", True
        return "", "Unknown", True
    if definition and len(definition.units) == 1:
        return definition.units[0], "Typical unit for measurement", True
    if definition and len(definition.units) > 1:
        numeric = pd.to_numeric(series, errors="coerce").dropna()
        if not numeric.empty:
            med = float(numeric.median())
            if measurement in {"Height"} and 30 <= med <= 250:
                return "cm", "Inferred from observed values", True
            if measurement in {"Height"} and 0.3 <= med <= 2.5:
                return "m", "Inferred from observed values", True
            if measurement in {
                "Blood_Glucose",
                "Total_Cholesterol",
                "HDL_Cholesterol",
                "LDL_Cholesterol",
                "Triglycerides",
            } and med > 30:
                return "mg/dL", "Inferred from observed values", True
            if measurement in {
                "Blood_Glucose",
                "Total_Cholesterol",
                "HDL_Cholesterol",
                "LDL_Cholesterol",
                "Triglycerides",
            } and med <= 30:
                return "mmol/L", "Inferred from observed values", True
            if measurement == "Haemoglobin" and med <= 25:
                return "g/dL", "Inferred from observed values", True
            if measurement == "Haemoglobin" and med > 25:
                return "g/L", "Inferred from observed values", True
        return "", "Ambiguous unit", True
    return "", "Unknown", True


def _column_stats(series: pd.Series) -> dict[str, Any]:
    numeric = pd.to_numeric(series, errors="coerce")
    finite = numeric[np.isfinite(numeric.to_numpy(dtype=float, na_value=np.nan))] if len(numeric) else numeric
    stats: dict[str, Any] = {
        "min": None,
        "max": None,
        "mean": None,
        "median": None,
        "stdDev": None,
        "uniqueCount": int(series.nunique(dropna=True)),
        "categoricalValues": [],
    }
    if not finite.empty:
        values = finite.to_numpy(dtype=float)
        stats.update(
            {
                "min": json_safe(float(np.min(values))),
                "max": float(np.max(values)),
                "mean": float(np.mean(values)),
                "median": float(np.median(values)),
                "stdDev": float(np.std(values, ddof=0)),
            }
        )
    categories = series.dropna().astype(str).str.strip()
    categories = categories[categories != ""].value_counts().head(20)
    stats["categoricalValues"] = [{"value": str(value), "count": int(count)} for value, count in categories.items()]
    return json_safe(stats)


def profile_medical_schema(frame: pd.DataFrame) -> dict[str, Any]:
    """Profile each source column for clinical identity, unit and suitability."""
    analysis = analyse_dataframe(frame)
    analysis_by_name = {item["name"]: item for item in analysis["columns"]}
    columns: list[dict[str, Any]] = []
    excluded_identifiers: list[str] = []
    approved_output: list[str] = []
    warnings: list[str] = []

    for column in frame.columns:
        info = analysis_by_name.get(column, {})
        standardised, role, measurement, mapping_meta = standardise_name(column, frame[column])
        name_identifier = detect_identifier_name(column)
        content_identifier, content_reason = (
            detect_identifier_content(frame[column]) if not name_identifier else (False, "")
        )
        identifier = bool(name_identifier or content_identifier or info.get("potentialIdentifier"))
        unit = str(mapping_meta.get("unit") or "") if measurement else ""
        unit_confidence = str(
            mapping_meta.get("unitConfidence")
            or ("Not a measurement" if not measurement else "Unknown")
        )
        if measurement and not unit:
            detected_unit, detected_conf, _ = detect_unit(column, frame[column], measurement)
            unit, unit_confidence = detected_unit, detected_conf
        unit_confirmation = bool(measurement and unit_confidence != "From column name")
        context = MEASUREMENT_BY_NAME[measurement].context if measurement else ""

        column_warnings: list[str] = []
        mapping_rejected = mapping_meta.get("confidence") == "Rejected"
        if identifier:
            column_warnings.append("Identifier detected; excluded from training and generated output.")
            excluded_identifiers.append(column)
        if mapping_rejected:
            column_warnings.append(f"Mapping rejected: {mapping_meta.get('reason')}")
        if measurement and unit_confirmation:
            column_warnings.append(f"Unit is {unit_confidence.lower()}; confirm before clinical validation.")
        if measurement == "Blood_Glucose":
            column_warnings.append("Glucose requires a fasting, random or post-meal context before interpretation.")
        if measurement == "Body_Temperature" and not unit:
            column_warnings.append("Temperature unit is unknown; Celsius and Fahrenheit must not be mixed.")
        if role == "Unclassified" and not identifier:
            column_warnings.append(
                "Column is not a recognised demographic, disease or clinical measurement; not approved by default."
            )

        approved = (
            role in {"Demographic", "Disease", "Disease_Level", "ClinicalMeasurement"}
            and not identifier
            and not mapping_rejected
        )
        if role == "ClinicalMeasurement" and mapping_meta.get("confidence") == "Low":
            approved = False
            column_warnings.append("Clinical mapping confidence too low; not auto-approved.")
        if approved:
            approved_output.append(column)

        entries: dict[str, Any] = {
            "originalName": column,
            "standardisedName": standardised,
            "role": "Identifier" if identifier else role,
            "measurement": measurement,
            "dataType": str(frame[column].dtype),
            "kind": info.get("kind", "unknown"),
            "unit": unit,
            "unitConfidence": unit_confidence,
            "requiresUnitConfirmation": bool(unit_confirmation),
            "requiredClinicalContext": context,
            "mappingConfidence": mapping_meta.get("confidence"),
            "mappingReason": mapping_meta.get("reason"),
            "valueCheck": mapping_meta.get("valueCheck", ""),
            "missingCount": int(info.get("missingCount", 0)),
            "missingPercentage": float(info.get("missingPercentage", 0.0)),
            "uniqueCount": int(info.get("uniqueCount", 0)),
            "constant": bool(info.get("constant", False)),
            "contentIdentifierReason": content_reason,
            "approvedForOutput": approved,
            "warnings": column_warnings,
            **_column_stats(frame[column]),
        }
        if unit_confirmation:
            warnings.append(f"{column}: unit requires confirmation.")
        if content_identifier and not name_identifier:
            warnings.append(f"{column}: identifier-like values detected ({content_reason}).")
        columns.append(entries)

    return json_safe(
        {
            "totalColumns": int(len(frame.columns)),
            "columns": columns,
            "approvedOutputColumns": approved_output,
            "excludedIdentifierColumns": sorted(set(excluded_identifiers)),
            "demographicColumns": [item["originalName"] for item in columns if item["role"] == "Demographic"],
            "diseaseColumns": [item["originalName"] for item in columns if item["role"] == "Disease"],
            "diseaseLevelColumns": [item["originalName"] for item in columns if item["role"] == "Disease_Level"],
            "clinicalMeasurementColumns": [
                item["originalName"] for item in columns if item["role"] == "ClinicalMeasurement"
            ],
            "columnsRequiringConfirmation": [
                item["originalName"] for item in columns if item["requiresUnitConfirmation"]
            ],
            "warnings": warnings,
            "notes": [
                "Column mapping uses name, data type, unit hints and observed values; "
                "unknown/ambiguous columns are not auto-approved.",
                "Units detected by name or typical value require user confirmation before being treated as verified.",
                "Identifier detection covers direct identifiers and common renamed equivalents.",
            ],
        }
    )


def prohibited_output_columns(columns: list[str]) -> list[str]:
    return [column for column in columns if detect_identifier_name(column)]


NON_MEDICAL_NAME_PATTERN = re.compile(
    r"(^|_)(name|email|phone|mobile|telephone|address|street|city|district|state|zip|pincode|postcode|"
    r"hospital|doctor|visit|admission|encounter|insurance|billing|account|ssn|aadhaar|passport|license|licence|mrn)(_|$)"
)


def validate_strict_output_schema(
    frame: pd.DataFrame,
    *,
    approved_columns: list[str],
    identifier_columns: list[str] | None = None,
) -> dict[str, Any]:
    """Validate the exact final schema and scan values for reproduced identifiers."""
    identifier_columns = identifier_columns or []
    approval = [str(c) for c in approved_columns]
    approval_set = set(approval)
    names = [str(c) for c in frame.columns]
    prohibited = prohibited_output_columns(names)
    unapproved = [column for column in names if column not in approval_set]
    non_medical = [column for column in names if NON_MEDICAL_NAME_PATTERN.search(_normalise_name(column))]
    order_mismatch = names != approval
    missing_approved = [column for column in approval if column not in names]
    content_hits: list[dict[str, Any]] = []
    for column in names:
        if column in identifier_columns:
            continue
        values = frame[column].dropna().astype(str).str.strip()
        values = values[values != ""]
        if values.empty:
            continue
        sample = values.head(500)
        emails = int(sample.str.match(EMAIL_PATTERN).sum())
        phones = int(sample.str.match(PHONE_PATTERN).sum())
        tokens = int(sample.str.match(LONG_ID_PATTERN).sum())
        if emails or phones or tokens:
            content_hits.append({"column": column, "emails": emails, "phones": phones, "identifierTokens": tokens})
    errors: list[str] = []
    if prohibited:
        errors.append("Prohibited identifier-style columns: " + ", ".join(prohibited))
    if unapproved:
        errors.append("Unapproved output columns: " + ", ".join(unapproved))
    if non_medical:
        errors.append("Non-medical/identifier-like column names: " + ", ".join(sorted(set(non_medical))))
    if content_hits:
        errors.append("Identifier-like values found in output: " + ", ".join(item["column"] for item in content_hits))
    if missing_approved:
        errors.append("Approved output columns missing from final output: " + ", ".join(missing_approved))
    if order_mismatch and not unapproved and not missing_approved:
        errors.append("Output column order differs from approved schema.")
    return json_safe(
        {
            "passed": not errors,
            "errors": errors,
            "columnCount": len(names),
            "approvedColumns": approval,
            "actualColumns": names,
            "prohibitedColumns": prohibited,
            "unapprovedColumns": unapproved,
            "nonMedicalColumns": sorted(set(non_medical)),
            "missingApprovedColumns": missing_approved,
            "contentHits": content_hits,
            "notes": [
                "Approved columns are the demographic, disease and clinical measurements selected for this job.",
                "Generated output must contain only approved medical columns and no identifiers/PII.",
                "Content scanning covers email, phone and long identifier-like tokens in the final output only.",
            ],
        }
    )
