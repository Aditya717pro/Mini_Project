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
            section("1. Pipeline Overview", [
                key_value_table(metadata, title="Job and version references"),
                table(["Stage", "Records in", "Records out", "Status"], data.get("stages") or [],
                      title="Record flow"),
            ]),
            section("2. Mapping Decisions", [
                table(["Source column", "Proposed target", "Final target", "Decision", "Confidence"],
                      data.get("mappings") or [], title="Recorded mapping decisions")
            ]),
            section("3. Transformations", [
                table(["Order", "Operation", "Column", "Details"], data.get("transformations") or [],
                      title="Persisted transformation log"),
                table(["Column", "From unit", "To unit", "Factor", "Rationale"],
                      data.get("unit_conversions") or [], title="Structured unit conversions"),
            ]),
            section("4. Execution Evidence", [
                table(["Time", "Stage", "Level", "Message"], data.get("logs") or [],
                      title="Persisted execution log"),
                table(["Check", "Before", "After"], data.get("before_after") or [],
                      title="Before and after profile"),
            ]),
            section("5. Limitations", [callout("\n".join(limitations), title="Interpretation limits")]),
        ],
    )
