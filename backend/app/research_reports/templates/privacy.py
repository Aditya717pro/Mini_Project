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
            section("1. Privacy Evaluation Scope", [
                key_value_table(metadata, title="Evaluation references"),
                callout(
                    "Privacy results are limited to the persisted evaluation method and metrics. A low "
                    "overlap or duplicate count does not prove anonymity, non-identifiability, or "
                    "differential privacy.",
                    title="Privacy claim boundary",
                ),
            ]),
            section("2. Recorded Metrics", [
                table(["Metric", "Value", "Interpretation"], data.get("metrics") or [],
                      title="Persisted privacy metrics"),
                table(["Check", "Value", "Notes"], data.get("overlap") or [],
                      title="Record overlap and duplication checks"),
            ]),
            section("3. Not Evaluated", [
                table(["Assessment", "Status", "Reason"], data.get("not_evaluated") or [],
                      title="Assessments without persisted evidence")
            ]),
            section("4. Limitations", [callout("\n".join(limitations), title="Interpretation limits")]),
        ],
    )
