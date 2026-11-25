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
            section("1. Utility Evaluation Scope", [
                key_value_table(metadata, title="Evaluation references"),
                table(["Control", "Persisted detail"], data.get("methodology") or [],
                      title="Leakage controls and methodology"),
            ]),
            section("2. TSTR Results", [
                table(["Metric", "Value"], data.get("tstr_metrics") or [], title="Train synthetic, test real"),
                chart(data.get("tstr_labels") or [], data.get("tstr_values") or [],
                      title="TSTR metric magnitudes"),
            ]),
            section("3. TRTR Results", [
                table(["Metric", "Value"], data.get("trtr_metrics") or [], title="Train real, test real"),
                chart(data.get("trtr_labels") or [], data.get("trtr_values") or [],
                      title="TRTR metric magnitudes"),
            ]),
            section("4. Comparison and Warnings", [
                table(["Metric", "TSTR", "TRTR", "Gap"], data.get("comparison") or [],
                      title="Persisted comparison summary"),
                callout("\n".join(data.get("warnings") or []), title="Warnings"),
            ]),
            section("5. Limitations", [callout("\n".join(limitations), title="Interpretation limits")]),
        ],
    )
