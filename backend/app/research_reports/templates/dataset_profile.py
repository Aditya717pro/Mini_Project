from __future__ import annotations

from typing import Any

from app.research_reports.templates.common import build_payload, callout, key_value_table, section, table


def build(data: dict[str, Any]) -> Any:
    metadata = data.get("metadata") or {}
    limitations = data.get("limitations") or []
    return build_payload(
        report_id=data["report_id"],
        report_type=data["report_type"],
        title=data["title"],
        generated_at=data["generated_at"],
        template_version=data["template_version"],
        references=data.get("references") or [],
        sections=[
            section("1. Report Scope", [
                key_value_table(metadata, title="Dataset and source references"),
                callout(
                    "This profile summarises persisted schema and quality metadata. It does not present "
                    "patient-level records and does not establish clinical validity.",
                    title="Scope statement",
                ),
            ]),
            section("2. Dataset Structure", [
                table(
                    ["Column", "Type", "Kind", "Missing", "Missing %", "Unique", "Flag"],
                    data.get("schema_columns") or [],
                    title="Schema summary (identifier-like fields omitted)",
                )
            ]),
            section("3. Distribution Summary", [
                table(["Column", "Minimum", "Maximum", "Mean", "Median", "Std dev", "Missing"],
                      data.get("numerical") or [], title="Numerical fields"),
                table(["Column", "Most frequent value", "Count", "Distinct", "Missing"],
                      data.get("categorical") or [], title="Categorical fields"),
            ]),
            section("4. Recorded Quality Context", [
                table(["Dimension", "Score", "Method"], data.get("quality") or [],
                      title="Persisted quality assessments")
            ]),
            section("5. Limitations", [callout("\n".join(limitations), title="Interpretation limits")]),
        ],
    )
