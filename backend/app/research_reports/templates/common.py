from __future__ import annotations

from typing import Any

from app.research_reports.payload import ReportBlock, ReportPayload, ReportSection
from app.research_reports.sanitize import NOT_AVAILABLE, clean_label, clean_number, clean_text


def paragraph(text: Any, *, title: str = "") -> ReportBlock:
    return ReportBlock(kind="paragraph", title=clean_text(title, default=""), text=clean_text(text))


def callout(text: Any, *, title: str = "") -> ReportBlock:
    return ReportBlock(kind="callout", title=clean_text(title, default=""), text=clean_text(text))


def table(columns: list[str], rows: list[list[Any]], *, title: str = "") -> ReportBlock:
    cleaned_rows: list[list[str]] = []
    for row in rows:
        cleaned_rows.append([clean_number(value) for value in row])
    return ReportBlock(
        kind="table",
        title=clean_text(title, default=""),
        columns=[clean_label(column) for column in columns],
        rows=cleaned_rows,
    )


def chart(labels: list[Any], values: list[Any], *, title: str = "") -> ReportBlock:
    numeric: list[float] = []
    for value in values:
        try:
            numeric.append(float(value))
        except (TypeError, ValueError):
            numeric.append(0.0)
    return ReportBlock(
        kind="chart",
        title=clean_text(title, default=""),
        labels=[clean_label(label) for label in labels],
        values=numeric,
    )


def key_value_table(values: dict[str, Any], *, title: str = "") -> ReportBlock:
    rows = [[clean_text(key), clean_number(value)] for key, value in values.items()]
    return table(["Field", "Value"], rows, title=title)


def section(heading: str, blocks: list[ReportBlock]) -> ReportSection:
    return ReportSection(heading=clean_text(heading, default="Report section"), blocks=blocks)


def build_payload(
    *,
    report_id: str,
    report_type: str,
    title: str,
    generated_at: str,
    template_version: str,
    references: list[tuple[str, Any]],
    sections: list[ReportSection],
) -> ReportPayload:
    return ReportPayload(
        report_id=clean_text(report_id, limit=80),
        report_type=clean_text(report_type, limit=60),
        title=clean_text(title, limit=180),
        generated_at=clean_text(generated_at, limit=80),
        template_version=clean_text(template_version, limit=40),
        references=[(clean_text(label), clean_text(value, limit=120)) for label, value in references],
        sections=sections,
    )


def unavailable_row(name: str) -> list[str]:
    return [clean_label(name), NOT_AVAILABLE]
