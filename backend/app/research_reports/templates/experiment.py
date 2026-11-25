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
            section("1. Experiment Overview", [
                key_value_table(metadata, title="Experiment references"),
                callout(
                    "This report consolidates persisted experiment lineage and evaluation outputs. It does "
                    "not replace clinical review, privacy review, or governed access decisions.",
                    title="Scope statement",
                ),
            ]),
            section("2. Configuration Snapshot", [
                table(["Setting", "Value"], data.get("configuration") or [],
                      title="Immutable configuration snapshot")
            ]),
            section("3. Lineage and Versions", [
                table(["Event", "Parent", "Child", "Created at"], data.get("lineage") or [],
                      title="Persisted lineage events"),
                table(["Kind", "Version", "Records", "Checksum"], data.get("versions") or [],
                      title="Referenced dataset versions"),
            ]),
            section("4. Evaluation Outputs", [
                table(["Output", "Available", "Reference", "Status"], data.get("outputs") or [],
                      title="Persisted evaluation outputs"),
                table(["Metric", "TSTR", "TRTR", "Gap"], data.get("utility_metrics") or [],
                      title="Utility comparison summary"),
            ]),
            section("5. Limitations", [callout("\n".join(limitations), title="Interpretation limits")]),
        ],
    )
