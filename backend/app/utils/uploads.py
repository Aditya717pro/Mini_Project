from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

from app.models.enums import FileFormat

SUPPORTED_EXTENSIONS = {".csv": FileFormat.CSV, ".xlsx": FileFormat.XLSX, ".json": FileFormat.JSON}
MAX_HEADER_ROWS = 20


def extension_of(filename: str) -> str:
    return Path(filename).suffix.lower()


def format_for_extension(filename: str) -> FileFormat:
    extension = extension_of(filename)
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError("Only CSV, XLSX and JSON files are supported")
    return SUPPORTED_EXTENSIONS[extension]


def _decode_text(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("File is not valid UTF-8 text") from error


def _validate_csv(content: bytes) -> None:
    text = _decode_text(content)
    if "\x00" in text:
        raise ValueError("CSV content contains binary data")
    try:
        rows = list(csv.reader(io.StringIO(text), strict=True))
    except csv.Error as error:
        raise ValueError("CSV is malformed") from error
    rows = [row for row in rows[:MAX_HEADER_ROWS] if any(cell.strip() for cell in row)]
    if len(rows) < 2:
        raise ValueError("CSV must contain a header row and at least one data row")
    if not any(cell.strip() for cell in rows[0]):
        raise ValueError("CSV header row is empty")


def _json_records(content: bytes) -> list[dict]:
    try:
        payload = json.loads(_decode_text(content))
    except json.JSONDecodeError as error:
        raise ValueError("JSON could not be parsed") from error
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = next((value for value in payload.values() if isinstance(value, list)), [payload])
    else:
        raise ValueError("JSON must contain records")
    if not records or not all(isinstance(record, dict) for record in records):
        raise ValueError("JSON must contain a non-empty array of objects")
    return records


def _validate_xlsx(content: bytes) -> None:
    if not content.startswith(b"PK\x03\x04"):
        raise ValueError("XLSX content is missing a ZIP signature")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if "xl/workbook.xml" not in archive.namelist():
                raise ValueError("XLSX workbook structure is invalid")
    except zipfile.BadZipFile as error:
        raise ValueError("XLSX workbook is not a valid ZIP archive") from error


def validate_upload(filename: str, content: bytes, max_bytes: int) -> FileFormat:
    declared = format_for_extension(filename)
    if not content:
        raise ValueError("File is empty")
    if len(content) > max_bytes:
        raise ValueError(f"File exceeds the {max_bytes // (1024 * 1024)} MB upload limit")

    if declared == FileFormat.CSV:
        _validate_csv(content)
    elif declared == FileFormat.JSON:
        _json_records(content)
    else:
        _validate_xlsx(content)
    return declared
