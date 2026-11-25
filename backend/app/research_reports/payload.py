from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ReportBlock:
    kind: str
    title: str = ""
    text: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    values: list[float] = field(default_factory=list)


@dataclass(frozen=True)
class ReportSection:
    heading: str
    blocks: list[ReportBlock] = field(default_factory=list)


@dataclass(frozen=True)
class ReportPayload:
    report_id: str
    report_type: str
    title: str
    generated_at: str
    template_version: str
    references: list[tuple[str, str]] = field(default_factory=list)
    sections: list[ReportSection] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["references"] = [{"label": label, "value": value} for label, value in self.references]
        return data
