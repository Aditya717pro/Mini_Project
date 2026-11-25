from __future__ import annotations

from typing import Any

from app.research_reports.templates.common import (
    build_payload,
    callout,
    chart,
    key_value_table,
    section,
    table,
)


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
            section("1. Comparison Scope", [
                key_value_table(metadata, title="Compared datasets"),
                callout(
                    "Reported metrics describe distributional similarity. They are not a clinical quality "
                    "score and do not demonstrate privacy or fitness for a specific research task.",
                    title="Interpretation statement",
                ),
            ]),
            section("2. Column-Level Metrics", [
                table(
                    [
                        "Column",
                        "Metric",
                        "Similarity",
                        "Original missing %",
                        "Synthetic missing %",
                        "Original unique",
                        "Synthetic unique",
                    ],
                    data.get("column_metrics") or [],
                    title="Persisted comparison metrics",
                )
            ]),
            section("3. Persisted Distribution Charts", [
                chart(data.get("chart_labels") or [], data.get("chart_values") or [],
                      title="Chart values recorded in the comparison report")
            ]),
            section("4. Clinical Context", [
                table(["Assessment", "Outcome", "Details"], data.get("clinical") or [],
                      title="Recorded clinical checks")
            ]),
            section("5. Limitations", [callout("\n".join(limitations), title="Interpretation limits")]),
        ],
    )
