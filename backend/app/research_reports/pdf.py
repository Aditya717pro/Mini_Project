from __future__ import annotations

import math
from dataclasses import dataclass

from app.research_reports.payload import ReportBlock, ReportPayload, ReportSection
from app.research_reports.sanitize import NOT_AVAILABLE, clean_label, clean_text

PAGE_WIDTH = 612.0
PAGE_HEIGHT = 792.0
MARGIN = 54.0
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN
TOP_Y = 726.0
BOTTOM_Y = 58.0
HEADER_Y = 756.0
FOOTER_Y = 34.0


@dataclass
class _Page:
    commands: list[str]


def _escape(text: str) -> str:
    cleaned = clean_text(text, default="", limit=1000)
    cleaned = cleaned.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return cleaned.encode("latin-1", errors="replace").decode("latin-1")


def _char_width(size: float) -> float:
    return size * 0.52


def _wrap(text: str, size: float, width: float) -> list[str]:
    clean = clean_text(text, default="", limit=1200)
    if not clean:
        return [""]
    max_chars = max(8, int(width / _char_width(size)))
    words = clean.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            lines.append(current)
        while len(word) > max_chars:
            lines.append(word[:max_chars])
            word = word[max_chars:]
        current = word
    if current:
        lines.append(current)
    return lines or [""]


def _text(
    x: float,
    y: float,
    text: str,
    *,
    size: float = 9.5,
    bold: bool = False,
    color: tuple[float, float, float] = (0.1, 0.12, 0.14),
) -> str:
    font = "F2" if bold else "F1"
    red, green, blue = color
    return f"BT /{font} {size:g} Tf {red:.3f} {green:.3f} {blue:.3f} rg {x:.2f} {y:.2f} Td ({_escape(text)}) Tj ET"


def _line(x1: float, y1: float, x2: float, y2: float, *, width: float = 0.7) -> str:
    return f"{width:g} w 0.65 0.72 0.75 RG {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S"


def _rect(x: float, y: float, width: float, height: float, color: tuple[float, float, float]) -> str:
    red, green, blue = color
    return f"{red:.3f} {green:.3f} {blue:.3f} rg {x:.2f} {y:.2f} {width:.2f} {height:.2f} re f"


class ReportPDFRenderer:
    def __init__(self, payload: ReportPayload):
        self.payload = payload
        self.pages: list[_Page] = []
        self.page = _Page([])
        self.y = TOP_Y

    def render(self) -> bytes:
        self._cover()
        self._table_of_contents()
        for section in self.payload.sections:
            self._section(section)
        self._finalize_pages()
        return self._write_pdf()

    def _new_page(self) -> None:
        self.pages.append(self.page)
        self.page = _Page([])
        self.y = TOP_Y

    def _ensure(self, height: float) -> None:
        if self.y - height < BOTTOM_Y:
            self._new_page()

    def _finalize_pages(self) -> None:
        self.pages.append(self.page)
        total = len(self.pages)
        for index, page in enumerate(self.pages, start=1):
            page.commands.insert(0, _line(MARGIN, HEADER_Y, PAGE_WIDTH - MARGIN, HEADER_Y))
            page.commands.insert(0, _text(MARGIN, HEADER_Y + 10, "MedDataHub + SynthMed", size=8, bold=True))
            page.commands.insert(
                0,
                _text(
                    PAGE_WIDTH - MARGIN - 180,
                    HEADER_Y + 10,
                    f"{self.payload.report_type} | {self.payload.report_id}",
                    size=7.5,
                ),
            )
            page.commands.append(_line(MARGIN, FOOTER_Y + 12, PAGE_WIDTH - MARGIN, FOOTER_Y + 12))
            page.commands.append(
                _text(MARGIN, FOOTER_Y, "Research documentation generated from persisted records", size=7.5)
            )
            page.commands.append(_text(PAGE_WIDTH - MARGIN - 70, FOOTER_Y, f"Page {index} of {total}", size=7.5))

    def _cover(self) -> None:
        self.page.commands.append(_rect(0, PAGE_HEIGHT - 96, PAGE_WIDTH, 96, (0.06, 0.23, 0.28)))
        self.page.commands.append(
            _text(MARGIN, PAGE_HEIGHT - 44, "RESEARCH REPORT", size=12, bold=True, color=(1, 1, 1))
        )
        self.page.commands.append(
            _text(MARGIN, PAGE_HEIGHT - 68, "MedDataHub + SynthMed", size=19, bold=True, color=(1, 1, 1))
        )
        y = PAGE_HEIGHT - 150
        for line in _wrap(self.payload.title, 19, CONTENT_WIDTH):
            self.page.commands.append(_text(MARGIN, y, line, size=19, bold=True))
            y -= 27
        y -= 14
        rows = [
            ("Report ID", self.payload.report_id),
            ("Report type", self.payload.report_type),
            ("Generated at", self.payload.generated_at),
            ("Template version", self.payload.template_version),
            *self.payload.references,
        ]
        for label, value in rows:
            self.page.commands.append(_text(MARGIN, y, f"{label}:", size=9.5, bold=True))
            value_lines = _wrap(clean_text(value), 9.5, CONTENT_WIDTH - 150)
            self.page.commands.append(_text(MARGIN + 150, y, value_lines[0], size=9.5))
            y -= 16
            for extra in value_lines[1:]:
                self.page.commands.append(_text(MARGIN + 150, y, extra, size=9.5))
                y -= 16
        self.page.commands.append(
            _text(
                MARGIN,
                96,
                "All values are derived from persisted records. Absent evidence is shown explicitly.",
                size=8.5,
            )
        )
        self._new_page()

    def _table_of_contents(self) -> None:
        self.page.commands.append(_text(MARGIN, self.y, "Contents", size=16, bold=True))
        self.y -= 26
        if not self.payload.sections:
            self.page.commands.append(_text(MARGIN, self.y, NOT_AVAILABLE, size=10))
            self.y -= 18
        for number, section in enumerate(self.payload.sections, start=1):
            self._ensure(18)
            label = f"{number}. {section.heading}"
            self.page.commands.append(_text(MARGIN, self.y, label, size=10.5))
            self.y -= 18
        self._new_page()

    def _section(self, section: ReportSection) -> None:
        self._ensure(58)
        self.page.commands.append(_rect(MARGIN, self.y - 6, 5, 19, (0.06, 0.42, 0.46)))
        self.page.commands.append(_text(MARGIN + 14, self.y, section.heading, size=14, bold=True))
        self.y -= 28
        self.page.commands.append(_line(MARGIN, self.y + 6, PAGE_WIDTH - MARGIN, self.y + 6))
        self.y -= 12
        for block in section.blocks:
            self._block(block)

    def _block(self, block: ReportBlock) -> None:
        if block.kind == "paragraph":
            self._paragraph(block)
        elif block.kind == "table":
            self._table(block)
        elif block.kind == "chart":
            self._chart(block)
        elif block.kind == "callout":
            self._callout(block)
        else:
            self._paragraph(block)

    def _paragraph(self, block: ReportBlock) -> None:
        if block.title:
            self._ensure(30)
            self.page.commands.append(_text(MARGIN, self.y, block.title, size=10.5, bold=True))
            self.y -= 17
        for line in _wrap(block.text or NOT_AVAILABLE, 9.5, CONTENT_WIDTH):
            self._ensure(15)
            self.page.commands.append(_text(MARGIN, self.y, line, size=9.5))
            self.y -= 14
        self.y -= 8

    def _callout(self, block: ReportBlock) -> None:
        lines = _wrap(block.text or NOT_AVAILABLE, 9.5, CONTENT_WIDTH - 26)
        height = 15 + 14 * len(lines)
        self._ensure(height + 8)
        self.page.commands.append(_rect(MARGIN, self.y - height + 10, CONTENT_WIDTH, height, (0.94, 0.96, 0.97)))
        cursor = self.y
        if block.title:
            self.page.commands.append(_text(MARGIN + 12, cursor, block.title, size=10, bold=True))
            cursor -= 16
        for line in lines:
            self.page.commands.append(_text(MARGIN + 12, cursor, line, size=9.5))
            cursor -= 14
        self.y -= height + 10

    def _table(self, block: ReportBlock) -> None:
        if block.title:
            self._ensure(28)
            self.page.commands.append(_text(MARGIN, self.y, block.title, size=10.5, bold=True))
            self.y -= 17
        columns = block.columns or ["Value"]
        rows = block.rows or [[NOT_AVAILABLE]]
        widths = self._column_widths(columns, rows)
        self._table_header(columns, widths)
        for row in rows:
            self._table_row(row, widths, columns)

    def _column_widths(self, columns: list[str], rows: list[list[str]]) -> list[float]:
        raw: list[float] = []
        for index, column in enumerate(columns):
            longest = len(clean_text(column))
            for row in rows:
                longest = max(longest, len(clean_text(row[index] if index < len(row) else "")))
            raw.append(max(45.0, min(220.0, longest * 5.2 + 18)))
        total = sum(raw)
        return [CONTENT_WIDTH * value / total for value in raw]

    def _table_header(self, columns: list[str], widths: list[float]) -> None:
        self._ensure(26)
        self.page.commands.append(_rect(MARGIN, self.y - 6, CONTENT_WIDTH, 20, (0.88, 0.92, 0.94)))
        x = MARGIN + 5
        for column, width in zip(columns, widths, strict=False):
            self.page.commands.append(
                _text(x, self.y, clean_label(column), size=8.8, bold=True)
            )
            x += width
        self.y -= 25

    def _table_row(self, row: list[str], widths: list[float], columns: list[str]) -> None:
        wrapped = [
            _wrap(row[index] if index < len(row) else NOT_AVAILABLE, 8.6, width - 10)
            for index, width in enumerate(widths)
        ]
        height = max(len(lines) for lines in wrapped) * 12 + 8
        if self.y - height < BOTTOM_Y:
            self._new_page()
            self._table_header(columns, widths)
        self.page.commands.append(_line(MARGIN, self.y + 4, PAGE_WIDTH - MARGIN, self.y + 4))
        cursor = self.y
        x = MARGIN + 5
        for lines, width in zip(wrapped, widths, strict=False):
            for line in lines:
                self.page.commands.append(_text(x, cursor, line, size=8.6))
                cursor -= 12
            x += width
        self.y -= height

    def _chart(self, block: ReportBlock) -> None:
        if block.title:
            self._ensure(28)
            self.page.commands.append(_text(MARGIN, self.y, block.title, size=10.5, bold=True))
            self.y -= 17
        labels = [clean_label(label) for label in block.labels[:10]]
        values = list(block.values[: len(labels)])
        if not labels or not values:
            self._paragraph(ReportBlock(kind="paragraph", text=NOT_AVAILABLE))
            return
        max_value = max(abs(value) for value in values)
        if max_value == 0:
            max_value = 1.0
        row_height = 28
        self._ensure(row_height * len(labels) + 12)
        for label, value in zip(labels, values, strict=False):
            if self.y - row_height < BOTTOM_Y:
                self._new_page()
            bar_width = (abs(value) / max_value) * 280.0
            self.page.commands.append(_text(MARGIN, self.y, label, size=8.8))
            self.page.commands.append(_rect(MARGIN + 175, self.y - 3, 280, 11, (0.90, 0.93, 0.94)))
            if bar_width > 0:
                self.page.commands.append(
                    _rect(MARGIN + 175, self.y - 3, bar_width, 11, (0.06, 0.42, 0.46))
                )
            self.page.commands.append(
                _text(MARGIN + 462, self.y, f"{value:.4g}" if math.isfinite(value) else NOT_AVAILABLE, size=8.8)
            )
            self.y -= row_height
        self.y -= 8

    def _write_pdf(self) -> bytes:
        first_content = 5
        page_numbers = [first_content + 2 * index for index in range(len(self.pages))]
        kids = " ".join(f"{number} 0 R" for number in page_numbers)
        objects: dict[int, bytes] = {
            1: b"<< /Type /Catalog /Pages 2 0 R >>",
            2: f"<< /Type /Pages /Kids [{kids}] /Count {len(self.pages)} >>".encode("ascii"),
            3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            4: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        }
        for index, page in enumerate(self.pages):
            content_number = first_content + 2 * index
            page_number = content_number + 1
            stream = "\n".join(page.commands).encode("latin-1", errors="replace")
            objects[content_number] = (
                b"<< /Length "
                + str(len(stream)).encode("ascii")
                + b" >>\nstream\n"
                + stream
                + b"\nendstream"
            )
            objects[page_number] = (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH:g} {PAGE_HEIGHT:g}] "
                f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_number} 0 R >>"
            ).encode("ascii")
        out = bytearray(b"%PDF-1.4\n")
        offsets: dict[int, int] = {}
        for number in sorted(objects):
            offsets[number] = len(out)
            out.extend(f"{number} 0 obj\n".encode("ascii"))
            out.extend(objects[number])
            out.extend(b"\nendobj\n")
        xref_offset = len(out)
        size = max(objects) + 1
        out.extend(f"xref\n0 {size}\n".encode("ascii"))
        out.extend(b"0000000000 65535 f \n")
        for number in range(1, size):
            out.extend(f"{offsets[number]:010d} 00000 n \n".encode("ascii"))
        out.extend(
            f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
        )
        return bytes(out)


def render_report(payload: ReportPayload) -> bytes:
    return ReportPDFRenderer(payload).render()
