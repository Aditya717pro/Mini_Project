from __future__ import annotations

DATASET_PROFILE = "dataset-profile"
ETL = "etl"
SYNTHETIC_GENERATION = "synthmed-generation"
COMPARISON = "synthmed-comparison"
PRIVACY = "synthmed-privacy"
UTILITY = "synthmed-utility"
EXPERIMENT = "synthmed-experiment"

REPORT_TYPES = (
    DATASET_PROFILE,
    ETL,
    SYNTHETIC_GENERATION,
    COMPARISON,
    PRIVACY,
    UTILITY,
    EXPERIMENT,
)

REPORT_TITLES = {
    DATASET_PROFILE: "Dataset Profile Report",
    ETL: "ETL and Harmonisation Report",
    SYNTHETIC_GENERATION: "Synthetic Data Generation Report",
    COMPARISON: "Original vs Synthetic Comparison Report",
    PRIVACY: "P3 Privacy Evaluation Report",
    UTILITY: "P4 TSTR/TRTR Utility Report",
    EXPERIMENT: "Complete Research Experiment Report",
}
