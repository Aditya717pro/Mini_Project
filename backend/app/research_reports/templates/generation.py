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
            section("1. Generation Overview", [
                key_value_table(metadata, title="Job and dataset references"),
                callout(
                    "Synthetic records are modelled outputs. They are not real patient records and must not "
                    "be treated as clinically validated observations.",
                    title="Synthetic data statement",
                ),
            ]),
            section("2. Configuration", [
                table(["Setting", "Value"], data.get("configuration") or [], title="Persisted generation settings"),
                table(["Setting", "Value"], data.get("environment") or [], title="Recorded model and library versions"),
            ]),
            section("3. Job Evidence", [
                table(["Metric", "Value"], data.get("job_metrics") or [], title="Execution metrics"),
                table(["Report type", "Method", "Score", "Created at"], data.get("evaluation_reports") or [],
                      title="Persisted evaluation reports"),
            ]),
            section("4. Clinical and Version Context", [
                table(
                    ["Check", "Outcome", "Details"],
                    data.get("clinical") or [],
                    title="Persisted clinical validation",
                ),
                table(["Kind", "Version", "Label", "Records", "Checksum"], data.get("versions") or [],
                      title="Dataset version references"),
            ]),
            section("5. Limitations", [callout("\n".join(limitations), title="Interpretation limits")]),
        ],
    )
