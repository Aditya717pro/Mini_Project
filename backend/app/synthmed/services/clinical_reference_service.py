"""Clinical reference intervals, provenance and record validation.

The built-in catalogue contains a small, documented set of reference intervals
for research/education use. Every entry carries its source, version and
approval state. References that require context the dataset does not provide
(age percentiles, pregnancy status, fasting state, verified unit, ...) are
reported as unavailable rather than guessed.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Any

import numpy as np
import pandas as pd

from app.synthmed.services.dataset_service import json_safe
from app.synthmed.services.medical_schema_service import MEASUREMENT_BY_NAME

CLINICAL_METHOD = "SynthMed documented reference-interval and relationship validation"
CLINICAL_LIMITATIONS = [
    "Reference intervals are screening aids for research datasets, not clinical decision support.",
    "A value outside a reference interval may be abnormal but clinically plausible; it is not automatically invalid.",
    "Passing configured numerical ranges does not establish clinical validity, safety or fitness for patient care.",
    "Relationship rules are applied only when the required measurements and context are present.",
    "Operational plausible limits are configurable data-quality bounds, not medical reference limits.",
]

ACC_AHA = "American College of Cardiology / American Heart Association"
ACC_AHA_URL = "https://www.acc.org/guidelines"
ACC_AHA_CITATION = "2017 ACC/AHA Hypertension Guideline, J Am Coll Cardiol 2018;71(6):e1-e2."
ACOG = "American College of Obstetricians and Gynecologists"
ACOG_URL = "https://www.acog.org/clinical"
ACOG_CITATION = "ACOG Practice Bulletin No. 202: Gestational Hypertension and Preeclampsia, 2019."
ADA = "American Diabetes Association"
ADA_URL = "https://diabetesjournals.org/care"
ADA_CITATION = "Standards of Care in Diabetes-2025, Diabetes Care 48(Suppl 1)."
AHA = "American Heart Association"
AHA_URL = "https://www.heart.org/"
AHA_CITATION = "American Heart Association, resting heart rate and paediatric heart-rate guidance."
WHO = "World Health Organization"
WHO_URL = "https://www.who.int/publications"
WHO_CITATION = "WHO, BMI classification and anaemia/haemoglobin guidance."
OPERATIONAL_SOURCE = "SynthMed operational screening configuration (data-quality only)"
CONVERSION_FACTORS: dict[str, dict[str, float]] = {
    "Blood_Glucose": {"mg/dL": 1.0, "mmol/L": 0.0555},
    "Total_Cholesterol": {"mg/dL": 1.0, "mmol/L": 0.02586},
    "HDL_Cholesterol": {"mg/dL": 1.0, "mmol/L": 0.02586},
    "LDL_Cholesterol": {"mg/dL": 1.0, "mmol/L": 0.02586},
    "Triglycerides": {"mg/dL": 1.0, "mmol/L": 0.01129},
    "Creatinine": {"mg/dL": 1.0, "µmol/L": 88.4},
    "Haemoglobin": {"g/dL": 1.0, "g/L": 10.0},
}


@dataclass(frozen=True)
class ReferenceRange:
    key: str
    measurement: str
    unit: str
    population: str
    context: str
    source_organization: str
    source_url: str
    citation: str
    version: str
    date: str
    approval_status: str = "Approved"
    age_min: float | None = None
    age_max: float | None = None
    sex: str = ""
    pregnancy: str = ""
    lower: float | None = None
    upper: float | None = None
    lower_inclusive: bool = True
    upper_inclusive: bool = True
    diagnostic_threshold: float | None = None
    diagnostic_meaning: str = ""
    plausible_lower: float | None = None
    plausible_upper: float | None = None
    conversion_factor: float | None = None
    notes: tuple[str, ...] = ()


def _bp(
    key: str,
    measurement: str,
    population: str,
    upper: float,
    context: str,
    source: str,
    url: str,
    citation: str,
    *,
    age_min=None,
    age_max=None,
    pregnancy="",
    notes=(),
) -> ReferenceRange:
    return ReferenceRange(
        key=key,
        measurement=measurement,
        unit="mmHg",
        population=population,
        context=context,
        source_organization=source,
        source_url=url,
        citation=citation,
        version="2017",
        date="2018-02",
        age_min=age_min,
        age_max=age_max,
        pregnancy=pregnancy,
        upper=upper,
        upper_inclusive=False,
        plausible_lower=50 if measurement == "Systolic_BP" else 30,
        plausible_upper=260 if measurement == "Systolic_BP" else 160,
        notes=notes,
    )


CATALOGUE: tuple[ReferenceRange, ...] = (
    _bp(
        "bp_systolic_adult",
        "Systolic_BP",
        "Adult",
        120,
        "resting",
        ACC_AHA,
        ACC_AHA_URL,
        ACC_AHA_CITATION,
        age_min=18,
        notes=("ACC/AHA normal category is <120 mmHg; lower reference limit is not defined by the guideline.",),
    ),
    _bp(
        "bp_diastolic_adult",
        "Diastolic_BP",
        "Adult",
        80,
        "resting",
        ACC_AHA,
        ACC_AHA_URL,
        ACC_AHA_CITATION,
        age_min=18,
        notes=("ACC/AHA normal category is <80 mmHg; interpretation uses the full BP reading.",),
    ),
    _bp(
        "bp_systolic_pregnancy",
        "Systolic_BP",
        "Pregnancy",
        140,
        "resting",
        ACOG,
        ACOG_URL,
        ACOG_CITATION,
        age_min=18,
        pregnancy="yes",
        notes=("ACOG gestational hypertension threshold; pregnancy status must be confirmed.",),
    ),
    _bp(
        "bp_diastolic_pregnancy",
        "Diastolic_BP",
        "Pregnancy",
        90,
        "resting",
        ACOG,
        ACOG_URL,
        ACOG_CITATION,
        age_min=18,
        pregnancy="yes",
        notes=("ACOG gestational hypertension threshold; pregnancy status must be confirmed.",),
    ),
    ReferenceRange(
        "bp_pediatric_unavailable",
        "Systolic_BP",
        "mmHg",
        "Pediatric",
        "resting",
        AHA,
        AHA_URL,
        "Pediatric blood pressure requires age, sex and height-percentile tables.",
        "2017",
        "2017-08",
        approval_status="Unavailable",
        age_max=18,
        plausible_lower=50,
        plausible_upper=260,
        notes=("Adult BP intervals are not applied to children.",),
    ),
    ReferenceRange(
        "bp_diastolic_pediatric_unavailable",
        "Diastolic_BP",
        "mmHg",
        "Pediatric",
        "resting",
        AHA,
        AHA_URL,
        "Pediatric blood pressure requires age, sex and height-percentile tables.",
        "2017",
        "2017-08",
        approval_status="Unavailable",
        age_max=18,
        plausible_lower=30,
        plausible_upper=160,
        notes=("Adult BP intervals are not applied to children.",),
    ),
    ReferenceRange(
        "glucose_fasting_mgdl",
        "Blood_Glucose",
        "mg/dL",
        "Adult",
        "fasting",
        ADA,
        ADA_URL,
        ADA_CITATION,
        "2025",
        "2025-01",
        age_min=18,
        upper=100,
        upper_inclusive=False,
        plausible_lower=20,
        plausible_upper=1000,
        diagnostic_threshold=126,
        diagnostic_meaning="Diabetes range requires confirmation on a separate occasion per ADA.",
        conversion_factor=0.0555,
        notes=("Normal fasting plasma glucose is <100 mg/dL per ADA.",),
    ),
    ReferenceRange(
        "glucose_fasting_mmol",
        "Blood_Glucose",
        "mmol/L",
        "Adult",
        "fasting",
        ADA,
        ADA_URL,
        ADA_CITATION,
        "2025",
        "2025-01",
        age_min=18,
        upper=5.6,
        upper_inclusive=False,
        plausible_lower=1.1,
        plausible_upper=55.5,
        diagnostic_threshold=7.0,
        diagnostic_meaning="Diabetes range requires confirmation on a separate occasion per ADA.",
        conversion_factor=0.0555,
        notes=("mmol/L value is derived from the ADA mg/dL interval with the 18:1 conversion.",),
    ),
    ReferenceRange(
        "glucose_random_unavailable",
        "Blood_Glucose",
        "mg/dL",
        "Adult",
        "random",
        ADA,
        ADA_URL,
        ADA_CITATION,
        "2025",
        "2025-01",
        approval_status="Unavailable",
        age_min=18,
        plausible_lower=20,
        plausible_upper=1000,
        diagnostic_threshold=200,
        diagnostic_meaning="ADA diabetes diagnostic threshold requires classic hyperglycaemic symptoms.",
        conversion_factor=0.0555,
        notes=("No healthy reference interval is defined for random glucose; do not apply fasting thresholds.",),
    ),
    ReferenceRange(
        "glucose_postprandial_mgdl",
        "Blood_Glucose",
        "mg/dL",
        "Adult",
        "postprandial_2h",
        ADA,
        ADA_URL,
        ADA_CITATION,
        "2025",
        "2025-01",
        age_min=18,
        upper=140,
        upper_inclusive=False,
        plausible_lower=20,
        plausible_upper=1000,
        diagnostic_threshold=200,
        diagnostic_meaning="2-hour OGTT diabetes threshold per ADA.",
        conversion_factor=0.0555,
        notes=("Based on the 2-hour 75 g OGTT normal value <140 mg/dL.",),
    ),
    ReferenceRange(
        "hr_adult_resting",
        "Heart_Rate",
        "bpm",
        "Adult",
        "resting",
        AHA,
        AHA_URL,
        AHA_CITATION,
        "2024",
        "2024-01",
        age_min=18,
        lower=60,
        upper=100,
        plausible_lower=20,
        plausible_upper=250,
        notes=("Resting adult reference commonly cited as 60-100 bpm.",),
    ),
    ReferenceRange(
        "hr_pregnancy_unavailable",
        "Heart_Rate",
        "bpm",
        "Pregnancy",
        "resting",
        AHA,
        AHA_URL,
        AHA_CITATION,
        "2024",
        "2024-01",
        approval_status="Unavailable",
        age_min=18,
        pregnancy="yes",
        plausible_lower=20,
        plausible_upper=250,
        notes=("Adult resting heart-rate intervals are not applied to pregnancy without a verified source.",),
    ),
    ReferenceRange(
        "hr_infant",
        "Heart_Rate",
        "bpm",
        "Pediatric",
        "resting",
        AHA,
        AHA_URL,
        AHA_CITATION,
        "2024",
        "2024-01",
        age_min=0,
        age_max=1,
        lower=80,
        upper=160,
        plausible_lower=20,
        plausible_upper=250,
    ),
    ReferenceRange(
        "hr_toddler",
        "Heart_Rate",
        "bpm",
        "Pediatric",
        "resting",
        AHA,
        AHA_URL,
        AHA_CITATION,
        "2024",
        "2024-01",
        age_min=1,
        age_max=3,
        lower=80,
        upper=130,
        plausible_lower=20,
        plausible_upper=250,
    ),
    ReferenceRange(
        "hr_preschool",
        "Heart_Rate",
        "bpm",
        "Pediatric",
        "resting",
        AHA,
        AHA_URL,
        AHA_CITATION,
        "2024",
        "2024-01",
        age_min=3,
        age_max=6,
        lower=80,
        upper=120,
        plausible_lower=20,
        plausible_upper=250,
    ),
    ReferenceRange(
        "hr_school",
        "Heart_Rate",
        "bpm",
        "Pediatric",
        "resting",
        AHA,
        AHA_URL,
        AHA_CITATION,
        "2024",
        "2024-01",
        age_min=6,
        age_max=13,
        lower=70,
        upper=110,
        plausible_lower=20,
        plausible_upper=250,
    ),
    ReferenceRange(
        "hr_adolescent",
        "Heart_Rate",
        "bpm",
        "Pediatric",
        "resting",
        AHA,
        AHA_URL,
        AHA_CITATION,
        "2024",
        "2024-01",
        age_min=13,
        age_max=18,
        lower=60,
        upper=100,
        plausible_lower=20,
        plausible_upper=250,
    ),
    ReferenceRange(
        "temperature_unavailable",
        "Body_Temperature",
        "",
        "General",
        "",
        WHO,
        WHO_URL,
        "No verified temperature reference interval is bundled; "
        "supply the measurement site, device and a reviewed source.",
        "n/a",
        "n/a",
        approval_status="Unavailable",
        plausible_lower=30,
        plausible_upper=45,
        notes=("Unit must be confirmed; Celsius and Fahrenheit are converted only with an explicit unit.",),
    ),
    ReferenceRange(
        "spo2_adult",
        "SpO2",
        "%",
        "Adult",
        "room_air",
        WHO,
        WHO_URL,
        "Pulse oximetry guidance; normal adult saturation is approximately 95-100% on room air.",
        "2011",
        "2011-01",
        age_min=18,
        lower=95,
        upper=100,
        plausible_lower=50,
        plausible_upper=100,
        notes=("Altitude and supplemental oxygen affect interpretation.",),
    ),
    ReferenceRange(
        "respiratory_rate_adult",
        "Respiratory_Rate",
        "breaths/min",
        "Adult",
        "resting",
        AHA,
        AHA_URL,
        AHA_CITATION,
        "2024",
        "2024-01",
        age_min=18,
        lower=12,
        upper=20,
        plausible_lower=4,
        plausible_upper=60,
    ),
    ReferenceRange(
        "bmi_adult",
        "BMI",
        "kg/m^2",
        "Adult",
        "standard",
        WHO,
        WHO_URL,
        WHO_CITATION,
        "2006",
        "2006-01",
        age_min=18,
        lower=18.5,
        upper=25,
        upper_inclusive=False,
        plausible_lower=10,
        plausible_upper=80,
        notes=(
            "WHO healthy BMI range is 18.5 to <25 kg/m^2 for adults; paediatric interpretation is not applied "
            "without verified growth-reference support.",
        ),
    ),
    ReferenceRange(
        "cholesterol_total",
        "Total_Cholesterol",
        "mg/dL",
        "Adult",
        "fasting",
        AHA,
        AHA_URL,
        AHA_CITATION,
        "2019",
        "2019-01",
        age_min=18,
        upper=200,
        upper_inclusive=False,
        plausible_lower=50,
        plausible_upper=600,
        conversion_factor=0.02586,
    ),
    ReferenceRange(
        "hdl_male",
        "HDL_Cholesterol",
        "mg/dL",
        "Adult",
        "fasting",
        AHA,
        AHA_URL,
        AHA_CITATION,
        "2019",
        "2019-01",
        age_min=18,
        sex="Male",
        lower=40,
        plausible_lower=10,
        plausible_upper=150,
        conversion_factor=0.02586,
    ),
    ReferenceRange(
        "hdl_female",
        "HDL_Cholesterol",
        "mg/dL",
        "Adult",
        "fasting",
        AHA,
        AHA_URL,
        AHA_CITATION,
        "2019",
        "2019-01",
        age_min=18,
        sex="Female",
        lower=50,
        plausible_lower=10,
        plausible_upper=150,
        conversion_factor=0.02586,
    ),
    ReferenceRange(
        "ldl_adult",
        "LDL_Cholesterol",
        "mg/dL",
        "Adult",
        "fasting",
        AHA,
        AHA_URL,
        AHA_CITATION,
        "2019",
        "2019-01",
        age_min=18,
        upper=100,
        plausible_lower=10,
        plausible_upper=400,
        conversion_factor=0.02586,
    ),
    ReferenceRange(
        "triglycerides_adult",
        "Triglycerides",
        "mg/dL",
        "Adult",
        "fasting",
        AHA,
        AHA_URL,
        AHA_CITATION,
        "2019",
        "2019-01",
        age_min=18,
        upper=150,
        plausible_lower=20,
        plausible_upper=1000,
        conversion_factor=0.01129,
    ),
    ReferenceRange(
        "haemoglobin_unavailable",
        "Haemoglobin",
        "",
        "Adult",
        "",
        WHO,
        WHO_URL,
        WHO_CITATION,
        "2011",
        "2011-01",
        approval_status="Unavailable",
        age_min=18,
        plausible_lower=3,
        plausible_upper=25,
        notes=("WHO defines anaemia thresholds but upper reference limits are laboratory- and method-specific.",),
    ),
    ReferenceRange(
        "creatinine_unavailable",
        "Creatinine",
        "",
        "Adult",
        "",
        WHO,
        WHO_URL,
        "Creatinine reference intervals are assay- and sex-specific; no verified interval is bundled.",
        "n/a",
        "n/a",
        approval_status="Unavailable",
        age_min=18,
        plausible_lower=0.1,
        plausible_upper=15,
        notes=("Do not apply an unverified creatinine reference interval.",),
    ),
)

BY_KEY = {entry.key: entry for entry in CATALOGUE}


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _matches_context(entry: ReferenceRange, context: str) -> bool:
    if not entry.context:
        return True
    wanted = str(context or "").strip().lower()
    if not wanted:
        return False
    if entry.context == wanted:
        return True
    aliases = {
        "postmeal": "postprandial_2h",
        "post_meal": "postprandial_2h",
        "after meal": "postprandial_2h",
        "ogtt_2h": "postprandial_2h",
        "random": "random",
        "fasting": "fasting",
        "rest": "resting",
    }
    return aliases.get(wanted) == entry.context


def reference_to_dict(entry: ReferenceRange) -> dict[str, Any]:
    return json_safe(
        {
            "key": entry.key,
            "measurement": entry.measurement,
            "unit": entry.unit,
            "population": entry.population,
            "ageMinYears": entry.age_min,
            "ageMaxYears": entry.age_max,
            "sex": entry.sex,
            "pregnancy": entry.pregnancy,
            "context": entry.context,
            "lower": entry.lower,
            "upper": entry.upper,
            "lowerInclusive": entry.lower_inclusive,
            "upperInclusive": entry.upper_inclusive,
            "plausibleLower": entry.plausible_lower,
            "plausibleUpper": entry.plausible_upper,
            "diagnosticThreshold": entry.diagnostic_threshold,
            "diagnosticMeaning": entry.diagnostic_meaning,
            "sourceOrganization": entry.source_organization,
            "sourceUrl": entry.source_url,
            "citation": entry.citation,
            "version": entry.version,
            "date": entry.date,
            "approvalStatus": entry.approval_status,
            "available": entry.approval_status == "Approved" and (entry.lower is not None or entry.upper is not None),
            "notes": list(entry.notes),
        }
    )


def reference_catalog() -> list[dict[str, Any]]:
    return [reference_to_dict(entry) for entry in CATALOGUE]


def available_references() -> list[dict[str, Any]]:
    return [item for item in reference_catalog() if item["available"]]


def convert_unit(value: float, from_unit: str, to_unit: str, measurement: str) -> tuple[float | None, str]:
    from_unit = str(from_unit or "").strip()
    to_unit = str(to_unit or "").strip()
    if not from_unit or not to_unit:
        return None, "Missing source or target unit."
    if from_unit == to_unit:
        return value, ""
    if measurement == "Body_Temperature" and {from_unit, to_unit} == {"°C", "°F"}:
        converted = (value * 9 / 5) + 32 if from_unit == "°C" else (value - 32) * 5 / 9
        return converted, f"Converted {from_unit} to {to_unit}."
    factors = CONVERSION_FACTORS.get(measurement, {})
    from_factor = factors.get(from_unit)
    to_factor = factors.get(to_unit)
    if from_factor and to_factor and from_factor > 0:
        return (
            value * to_factor / from_factor,
            f"Converted {from_unit} to {to_unit} using documented factor {to_factor / from_factor:.6g}.",
        )
    return None, f"No well-defined conversion from {from_unit!r} to {to_unit!r} for {measurement}."


def select_reference(
    measurement: str,
    *,
    age_years: float | None = None,
    sex: str = "",
    pregnant: bool | str | None = None,
    context: str = "",
    unit: str = "",
    reference_key: str = "",
    overrides: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Select the most specific configured reference for a measurement."""
    candidates = list(CATALOGUE)
    if overrides:
        for override in overrides:
            if not isinstance(override, dict) or not override.get("active", True):
                continue
            key = str(override.get("key") or "")
            base = BY_KEY.get(key)
            if base is None:
                continue
            changes: dict[str, Any] = {}
            for field, attr in (
                ("lower", "lower"),
                ("upper", "upper"),
                ("plausibleLower", "plausible_lower"),
                ("plausibleUpper", "plausible_upper"),
                ("approvalStatus", "approval_status"),
                ("sourceOrganization", "source_organization"),
                ("sourceUrl", "source_url"),
                ("citation", "citation"),
                ("version", "version"),
                ("date", "date"),
            ):
                if field in override and override[field] is not None:
                    changes[attr] = override[field]
            candidates = [replace(entry, **changes) if entry.key == key else entry for entry in candidates]

    if reference_key:
        selected = next((entry for entry in candidates if entry.key == reference_key), None)
        if selected is None:
            return {
                "available": False,
                "key": reference_key,
                "measurement": measurement,
                "reason": f"Configured reference key {reference_key!r} does not exist.",
                "warnings": [],
            }
        result = reference_to_dict(selected)
        result["warnings"] = []
        if unit and selected.unit and unit != selected.unit:
            converted, message = convert_unit(1.0, unit, selected.unit, measurement)
            if converted is None:
                result["available"] = False
                result["reason"] = message
        return result

    pregnant_bool = (
        pregnant if isinstance(pregnant, bool) else str(pregnant or "").strip().lower() in {"yes", "true", "1"}
    )
    sex_value = str(sex or "").strip().lower()
    age = _as_float(age_years)

    scored: list[tuple[int, ReferenceRange]] = []
    for entry in candidates:
        if entry.measurement != measurement:
            continue
        score = 0
        if pregnant_bool:
            if entry.pregnancy != "yes" and entry.population != "Pregnancy":
                continue
            score += 8
        elif entry.pregnancy == "yes":
            continue
        if age is not None:
            if entry.age_min is not None and age < entry.age_min:
                continue
            if entry.age_max is not None and age >= entry.age_max:
                continue
            if entry.population == "Pediatric":
                score += 4
            elif entry.population == "Adult" and age >= 18:
                score += 2
        elif entry.population == "Pediatric":
            continue
        if entry.sex:
            if not sex_value or entry.sex.lower() not in sex_value:
                continue
            score += 2
        if entry.context:
            if not _matches_context(entry, context):
                continue
            score += 3
        if unit and entry.unit and unit == entry.unit:
            score += 1
        scored.append((score, entry))

    if not scored:
        return {
            "available": False,
            "measurement": measurement,
            "reason": (
                "No approved reference is available for the supplied age, sex, pregnancy, context and unit. "
                "Verify the measurement context or provide an approved reference."
            ),
            "warnings": [],
        }
    scored.sort(key=lambda pair: pair[0], reverse=True)
    entry = scored[0][1]
    result = reference_to_dict(entry)
    warnings: list[str] = []
    if entry.approval_status != "Approved":
        result["available"] = False
        result["reason"] = f"Reference {entry.key} is {entry.approval_status}; do not apply it to generated values."
        warnings.append(f"Reference {entry.key} is {entry.approval_status}; values are not clinically verified.")
    if unit and entry.unit and unit != entry.unit:
        converted, message = convert_unit(1.0, unit, entry.unit, measurement)
        if converted is None:
            result["available"] = False
            result["reason"] = message
            warnings.append(message)
        else:
            warnings.append(message)
    result["warnings"] = warnings
    return result


def classify_value(value: Any, reference: dict[str, Any], *, unit: str, context: str) -> dict[str, Any]:
    """Classify a single measurement without hiding abnormal-but-plausible values."""
    number = _as_float(value)
    result: dict[str, Any] = {
        "value": json_safe(number if number is not None else value),
        "unit": unit,
        "context": context,
        "classification": "invalid",
        "warnings": [],
    }
    if number is None:
        result["warnings"].append("Measurement is missing, non-numeric or not finite.")
        return result
    if not unit:
        result["warnings"].append("Measurement unit is missing; no reference interval applied.")
        result["classification"] = "unverified"
        return result
    ref_unit = str(reference.get("unit") or "")
    if ref_unit and unit != ref_unit:
        converted, message = convert_unit(number, unit, ref_unit, str(reference.get("measurement") or ""))
        if converted is None:
            result["warnings"].append(message)
            result["classification"] = "invalid"
            return result
        number = converted
        result["valueInReferenceUnit"] = number
        result["referenceUnit"] = ref_unit
        result["warnings"].append(message)

    lower = _as_float(reference.get("plausibleLower"))
    upper = _as_float(reference.get("plausibleUpper"))
    if (lower is not None and number < lower) or (upper is not None and number > upper):
        result["classification"] = "implausible"
        result["warnings"].append("Value is outside the configured plausible screening limits.")
        return result
    if not reference.get("available"):
        result["classification"] = "unverified"
        result["warnings"].append(str(reference.get("reason") or "Reference interval unavailable."))
        return result
    ref_lower = _as_float(reference.get("lower"))
    ref_upper = _as_float(reference.get("upper"))
    below = ref_lower is not None and (
        number < ref_lower or (number == ref_lower and not reference.get("lowerInclusive", True))
    )
    above = ref_upper is not None and (
        number > ref_upper or (number == ref_upper and not reference.get("upperInclusive", True))
    )
    if below or above:
        result["classification"] = "abnormal_plausible"
        result["warnings"].append("Value is outside the selected reference interval but within plausible limits.")
        threshold = _as_float(reference.get("diagnosticThreshold"))
        if threshold is not None and (number >= threshold if ref_upper is not None and above else number <= threshold):
            result["warnings"].append(str(reference.get("diagnosticMeaning") or "Diagnostic threshold reached."))
    else:
        result["classification"] = "normal"
    return result


def _column_masks(frame: pd.DataFrame, column: str) -> tuple[pd.Series, pd.Series]:
    numeric = pd.to_numeric(frame[column], errors="coerce")
    return numeric, frame[column].isna()


def _age_series(frame: pd.DataFrame, column: str = "") -> pd.Series:
    if column and column in frame.columns:
        return pd.to_numeric(frame[column], errors="coerce")
    for candidate in ("Age", "age", "Age_Years"):
        if candidate in frame.columns:
            return pd.to_numeric(frame[candidate], errors="coerce")
    return pd.Series(np.nan, index=frame.index, dtype=float)


def _sex_series(frame: pd.DataFrame, column: str = "") -> pd.Series:
    if column and column in frame.columns:
        return frame[column].astype("string")
    for candidate in ("Gender", "gender", "Sex", "sex"):
        if candidate in frame.columns:
            return frame[candidate].astype("string")
    return pd.Series("", index=frame.index, dtype="string")


def _pregnancy_series(frame: pd.DataFrame, column: str = "") -> pd.Series:
    if column and column in frame.columns:
        return frame[column].astype("string")
    for candidate in ("Pregnancy", "pregnancy", "Pregnant", "pregnant"):
        if candidate in frame.columns:
            return frame[candidate].astype("string")
    return pd.Series("", index=frame.index, dtype="string")


def _trueish(series: pd.Series) -> pd.Series:
    return series.str.strip().str.lower().isin({"yes", "true", "1", "y"}).fillna(False)


def validate_clinical_records(
    frame: pd.DataFrame,
    *,
    generation_profile: str,
    clinical_variables: list[dict[str, Any]],
    overrides: Iterable[dict[str, Any]] | None = None,
    disease_rules: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate every generated row and return a detailed, auditable report."""
    variables: list[dict[str, Any]] = []
    row_class = {
        key: np.zeros(len(frame), dtype=bool)
        for key in ("normal", "abnormal_plausible", "implausible", "invalid", "unverified")
    }
    mandatory_fail = np.zeros(len(frame), dtype=bool)
    warnings: list[str] = []

    for variable in clinical_variables:
        if not isinstance(variable, dict) or not variable.get("enabled", True):
            continue
        column = str(variable.get("column") or "")
        measurement = str(variable.get("measurement") or "")
        unit = str(variable.get("unit") or "")
        context = str(variable.get("context") or "")
        if column not in frame.columns:
            warnings.append(f"Clinical variable column {column!r} is absent from generated output.")
            continue
        if measurement not in MEASUREMENT_BY_NAME:
            warnings.append(f"Measurement {measurement!r} is not supported by the clinical engine.")
            continue
        reference = select_reference(
            measurement,
            age_years=_as_float(variable.get("ageYears")),
            sex=str(variable.get("sex") or ""),
            pregnant=variable.get("pregnant"),
            context=context,
            unit=unit,
            reference_key=str(variable.get("referenceKey") or ""),
            overrides=overrides,
        )
        age = _age_series(frame, str(variable.get("ageColumn") or ""))
        sex = _sex_series(frame, str(variable.get("sexColumn") or ""))
        pregnant = _pregnancy_series(frame, str(variable.get("pregnantColumn") or ""))
        numeric, missing = _column_masks(frame, column)
        counts = {key: 0 for key in row_class}
        missing_units = 0 if unit else int(len(frame))
        inconsistent_units = 0
        messages: list[str] = []
        for index in range(len(frame)):
            if missing.iloc[index] and not pd.notna(numeric.iloc[index]):
                classification = "unverified" if generation_profile == "ClinicalDistribution" else "invalid"
                messages.append("Missing measurement value.")
            else:
                local_reference = reference
                if str(variable.get("ageColumn") or "") or "Age" in frame.columns:
                    age_value = age.iloc[index]
                    if pd.notna(age_value):
                        local_reference = select_reference(
                            measurement,
                            age_years=float(age_value),
                            sex=str(sex.iloc[index] or "") if str(sex.iloc[index]) else "",
                            pregnant=_trueish(pregnant.iloc[[index]]).iloc[0] if not pregnant.empty else False,
                            context=context,
                            unit=unit,
                            reference_key=str(variable.get("referenceKey") or ""),
                            overrides=overrides,
                        )
                result = classify_value(numeric.iloc[index], local_reference, unit=unit, context=context)
                classification = str(result["classification"])
                messages.extend(result["warnings"])
            counts[classification] += 1
            row_class[classification][index] = True
            if classification in {"invalid", "implausible"}:
                mandatory_fail[index] = True
            elif generation_profile == "NormalRange" and classification in {"abnormal_plausible", "unverified"}:
                mandatory_fail[index] = True
        variables.append(
            json_safe(
                {
                    "column": column,
                    "measurement": measurement,
                    "unit": unit,
                    "context": context,
                    "reference": reference,
                    "counts": counts,
                    "missingUnitRecords": missing_units,
                    "inconsistentUnitRecords": inconsistent_units,
                    "warnings": sorted(set(messages))[:20],
                }
            )
        )
        if not reference.get("available"):
            warnings.append(f"{column}: clinical reference interval unavailable; values are not clinically verified.")
        if not unit:
            warnings.append(f"{column}: unit not supplied; reference intervals cannot be applied.")

    relationship_checks = validate_relationships(frame, generation_profile=generation_profile, overrides=overrides)
    for check in relationship_checks:
        if check.get("failedRecords", 0):
            mandatory_fail |= np.asarray(check["_failures"], dtype=bool)
        if check.get("unavailable"):
            warnings.append(f"{check['name']}: {check.get('reason', 'not evaluated')}.")

    disease_checks = validate_disease_consistency(frame, disease_rules or [], generation_profile=generation_profile)
    for check in disease_checks.get("checks", []):
        if check.get("failedRecords", 0):
            mandatory_fail |= np.asarray(check["_failures"], dtype=bool)

    def public_check(check: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in check.items() if not key.startswith("_")}

    total = int(len(frame))
    return json_safe(
        {
            "method": CLINICAL_METHOD,
            "generationProfile": generation_profile,
            "totalRecords": total,
            "validRecords": int((~mandatory_fail).sum()),
            "rejectedRecords": int(mandatory_fail.sum()),
            "classificationCounts": {key: int(value.sum()) for key, value in row_class.items()},
            "outsideReferenceRecords": int(row_class["abnormal_plausible"].sum()),
            "outsidePlausibleLimitsRecords": int(row_class["implausible"].sum()),
            "invalidRecords": int(row_class["invalid"].sum()),
            "unverifiedRecords": int(row_class["unverified"].sum()),
            "missingUnitRecords": int(sum(item["missingUnitRecords"] for item in variables)),
            "inconsistentUnitRecords": int(sum(item["inconsistentUnitRecords"] for item in variables)),
            "implausibleCombinationRecords": int(
                sum(check.get("failedRecords", 0) for check in relationship_checks + disease_checks.get("checks", []))
            ),
            "variables": variables,
            "relationshipChecks": [public_check(check) for check in relationship_checks],
            "diseaseChecks": {key: value for key, value in disease_checks.items() if key != "checks"}
            | {"checks": [public_check(check) for check in disease_checks.get("checks", [])]},
            "warnings": sorted(set(warnings)),
            "limitations": CLINICAL_LIMITATIONS,
            "_mandatoryFailures": mandatory_fail.tolist(),
        }
    )


def validate_relationships(
    frame: pd.DataFrame, *, generation_profile: str, overrides: Iterable[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    def add(
        name: str, rule: str, source: str, mask: pd.Series | None, *, unavailable: bool = False, reason: str = ""
    ) -> None:
        failures = np.zeros(len(frame), dtype=bool) if mask is None else np.asarray(mask.fillna(False), dtype=bool)
        checks.append(
            json_safe(
                {
                    "name": name,
                    "rule": rule,
                    "source": source,
                    "applicableRecords": int((~failures).sum()) if mask is not None else 0,
                    "failedRecords": int(failures.sum()),
                    "unavailable": unavailable,
                    "reason": reason,
                    "_failures": failures.tolist(),
                }
            )
        )

    systolic = "Systolic_BP" if "Systolic_BP" in frame.columns else "SBP"
    diastolic = "Diastolic_BP" if "Diastolic_BP" in frame.columns else "DBP"
    if systolic in frame.columns and diastolic in frame.columns:
        high = pd.to_numeric(frame[systolic], errors="coerce")
        low = pd.to_numeric(frame[diastolic], errors="coerce")
        add(
            "blood_pressure_order",
            "Systolic blood pressure must be greater than diastolic blood pressure.",
            "Basic haemodynamic ordering; not a reference interval.",
            high.notna() & low.notna() & (high <= low),
        )
    else:
        add(
            "blood_pressure_order",
            "Systolic must exceed diastolic.",
            "Basic haemodynamic ordering.",
            None,
            unavailable=True,
            reason="Both blood pressure columns are not present.",
        )

    if "BMI" in frame.columns:
        height_col = next(
            (name for name in ("Height_m", "Height_cm", "Height", "height_m", "height_cm") if name in frame.columns),
            "",
        )
        weight_col = next((name for name in ("Weight_kg", "Weight", "weight_kg") if name in frame.columns), "")
        if height_col and weight_col:
            height_cm = pd.to_numeric(frame[height_col], errors="coerce")
            if "cm" in height_col.lower():
                height_m = height_cm / 100
            else:
                height_m = height_cm
            weight = pd.to_numeric(frame[weight_col], errors="coerce")
            bmi = pd.to_numeric(frame["BMI"], errors="coerce")
            expected = weight / (height_m * height_m).replace(0, np.nan)
            add(
                "bmi_consistency",
                "BMI must agree with weight / height^2 within 0.1 kg/m^2 when height and weight are present.",
                "Arithmetic identity of the BMI formula; tolerance 0.1 allows rounding.",
                (expected.notna() & bmi.notna() & ((expected - bmi).abs() > 0.1)),
            )
        else:
            add(
                "bmi_consistency",
                "BMI must agree with height and weight.",
                "Arithmetic identity.",
                None,
                unavailable=True,
                reason="Height and weight are not both present.",
            )

    lipids = ["Total_Cholesterol", "HDL_Cholesterol", "LDL_Cholesterol", "Triglycerides"]
    if all(column in frame.columns for column in lipids):
        total = pd.to_numeric(frame["Total_Cholesterol"], errors="coerce")
        hdl = pd.to_numeric(frame["HDL_Cholesterol"], errors="coerce")
        ldl = pd.to_numeric(frame["LDL_Cholesterol"], errors="coerce")
        failure = ((hdl.notna() & total.notna()) & (hdl > total + 0.5)) | (
            (ldl.notna() & total.notna()) & (ldl > total + 0.5)
        )
        add(
            "lipid_consistency",
            "HDL and LDL must not exceed total cholesterol in the same unit.",
            "Arithmetic constraint on lipid fractions.",
            failure,
        )
    else:
        add(
            "lipid_consistency",
            "Lipid fractions must not exceed total cholesterol.",
            "Arithmetic constraint.",
            None,
            unavailable=True,
            reason="The complete lipid panel is not present.",
        )

    glucose_context = next(
        (name for name in ("Glucose_Context", "glucose_context", "Measurement_Context") if name in frame.columns), ""
    )
    if "Blood_Glucose" in frame.columns and glucose_context:
        add(
            "glucose_context_recorded",
            "Every glucose measurement must carry its fasting, random or post-meal context.",
            "ADA Standards of Care: thresholds depend on measurement conditions.",
            frame[glucose_context].isna(),
        )
    elif "Blood_Glucose" in frame.columns:
        add(
            "glucose_context_recorded",
            "Glucose context must be available for clinical interpretation.",
            "ADA Standards of Care.",
            None,
            unavailable=True,
            reason="No glucose context column is present; clinical thresholds were not applied to random measurements.",
        )
    return checks


def validate_disease_consistency(
    frame: pd.DataFrame, rules: list[dict[str, Any]], *, generation_profile: str
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    disease_column = next(
        (name for name in ("Disease", "Diagnosis", "disease", "diagnosis") if name in frame.columns), ""
    )
    level_column = next(
        (name for name in ("Disease_Level", "disease_level", "Severity", "severity") if name in frame.columns), ""
    )
    if disease_column:
        observed = {str(value) for value in frame[disease_column].dropna().astype(str).unique()}
        checks.append(
            json_safe(
                {
                    "name": "disease_labels",
                    "rule": "Disease labels must come from the source dataset or an approved classification.",
                    "source": "Source dataset categories.",
                    "observedCategories": sorted(observed),
                    "failedRecords": 0,
                    "unavailable": False,
                    "_failures": np.zeros(len(frame), dtype=bool).tolist(),
                }
            )
        )
    else:
        checks.append(
            json_safe(
                {
                    "name": "disease_labels",
                    "rule": "Disease labels must come from the source dataset.",
                    "source": "Source dataset categories.",
                    "observedCategories": [],
                    "failedRecords": 0,
                    "unavailable": True,
                    "reason": "No disease column is present in the output schema.",
                    "_failures": np.zeros(len(frame), dtype=bool).tolist(),
                }
            )
        )
    if level_column:
        observed_levels = {str(value) for value in frame[level_column].dropna().astype(str).unique()}
        checks.append(
            json_safe(
                {
                    "name": "disease_level_labels",
                    "rule": "Disease_Level values must come from the source dataset or an approved rule.",
                    "source": "Source dataset categories.",
                    "observedCategories": sorted(observed_levels),
                    "failedRecords": 0,
                    "unavailable": False,
                    "_failures": np.zeros(len(frame), dtype=bool).tolist(),
                }
            )
        )
    reviewed = [rule for rule in rules if rule.get("reviewed") and rule.get("disease") and rule.get("column")]
    for index, rule in enumerate(reviewed):
        column = str(rule["column"])
        if column not in frame.columns:
            continue
        mask = (
            frame[disease_column].astype("string").eq(str(rule["disease"])).fillna(False)
            if disease_column
            else pd.Series(False, index=frame.index)
        )
        numeric = pd.to_numeric(frame[column], errors="coerce")
        failure = mask & numeric.notna()
        low = _as_float(rule.get("min"))
        high = _as_float(rule.get("max"))
        if low is not None:
            failure &= numeric >= low
        if high is not None:
            failure &= numeric <= high
        checks.append(
            json_safe(
                {
                    "name": f"reviewed_disease_rule_{index + 1}",
                    "rule": f"For {rule['disease']}, {column} must be outside [{low}, {high}].",
                    "source": str(rule.get("source") or "Configured and medically reviewed rule."),
                    "failedRecords": int(failure.sum()),
                    "unavailable": False,
                    "_failures": failure.tolist(),
                }
            )
        )
    return json_safe(
        {
            "method": "Source category preservation and explicitly configured reviewed rules",
            "diseaseColumn": disease_column,
            "diseaseLevelColumn": level_column,
            "rulesApplied": len(reviewed),
            "checks": checks,
            "limitations": [
                "Disease severity is never inferred from measurements unless an approved rule is configured.",
                "Rule-based exclusions require explicit clinical review and provenance.",
            ],
        }
    )
