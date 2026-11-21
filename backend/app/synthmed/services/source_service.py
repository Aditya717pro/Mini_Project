from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.enums import UserRole
from app.models.user import User
from app.services.audit_service import log_audit
from app.synthmed.models import SynthMedGeneratedDataset, SynthMedSourceDataset
from app.synthmed.schemas import (
    SynthMedDownloadsResponse,
    SynthMedGeneratedDatasetResponse,
    SynthMedSourceDatasetResponse,
)
from app.synthmed.services.storage_service import SynthMedStorageService

ALLOWED_EXTENSIONS = {".csv": "CSV", ".xlsx": "XLSX", ".json": "JSON"}
UUID_PATTERN = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

ALLOWED_MIME_TYPES = {
    ".csv": {"text/csv", "application/vnd.ms-excel", "text/plain", "application/csv"},
    ".xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
        "application/octet-stream",
    },
    ".json": {"application/json", "text/json", "text/plain", "application/octet-stream"},
}


def _iso(value) -> str:
    return value.isoformat() if value else ""


def _checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _validate_dataset_id(dataset_id: str) -> str:
    if not UUID_PATTERN.fullmatch(dataset_id or ""):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    try:
        return str(UUID(dataset_id))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.") from error



def _normalize_mime(content_type: str | None) -> str:
    if not content_type:
        return ""
    return content_type.split(";")[0].strip().lower()


def _validate_extension(filename: str) -> tuple[str, str]:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Unsupported file format. Upload a CSV, XLSX, or JSON file.",
        )
    return ext, ALLOWED_EXTENSIONS[ext]


def _validate_mime(ext: str, content_type: str | None) -> str:
    mime = _normalize_mime(content_type)
    if mime and mime not in ALLOWED_MIME_TYPES[ext]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unsupported MIME type '{mime}' for {ALLOWED_EXTENSIONS[ext]} files.",
        )
    return mime


def _csv_stats(content: bytes) -> tuple[int, int]:
    try:
        text = content.decode("utf-8-sig")
        rows = [row for row in csv.reader(io.StringIO(text), strict=True) if any(cell.strip() for cell in row)]
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="CSV file content is invalid."
        ) from error
    if len(rows) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="CSV must contain a header row and at least one data row.",
        )
    header = rows[0]
    if not any(cell.strip() for cell in header):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="CSV header row is empty."
        )
    return max(len(rows) - 1, 0), len(header)


def _json_stats(content: bytes) -> tuple[int, int]:
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="JSON file content is invalid."
        ) from error
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = next((value for value in payload.values() if isinstance(value, list)), [payload])
    else:
        records = []
    if not records or not all(isinstance(record, dict) for record in records):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="JSON must contain a non-empty array of objects.",
        )
    columns = len({key for record in records for key in record.keys()})
    return len(records), columns


def _xlsx_stats(content: bytes) -> tuple[int, int]:
    if not content.startswith(b"PK\x03\x04"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="XLSX file content is invalid."
        )
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if "xl/workbook.xml" not in archive.namelist():
                raise ValueError("missing workbook")
            shared_strings: list[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                import xml.etree.ElementTree as ET

                root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                for si in root.findall("m:si", ns):
                    text = "".join(node.text or "" for node in si.findall(".//m:t", ns))
                    shared_strings.append(text)
            sheet_name = next(
                (
                    name
                    for name in archive.namelist()
                    if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
                ),
                None,
            )

            if sheet_name is None:
                raise ValueError("missing sheet")
            import xml.etree.ElementTree as ET

            root = ET.fromstring(archive.read(sheet_name))
            ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            rows = root.findall(".//m:sheetData/m:row", ns)
            if len(rows) < 2:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="XLSX must contain a header row and at least one data row.",
                )

            def cell_value(cell) -> str:
                value_node = cell.find("m:v", ns)
                if value_node is None:
                    inline = cell.find("m:is/m:t", ns)
                    return (inline.text or "") if inline is not None else ""
                raw = value_node.text or ""
                if cell.attrib.get("t") == "s":
                    try:
                        return shared_strings[int(raw)]
                    except Exception:
                        return raw
                return raw

            header_cells = rows[0].findall("m:c", ns)
            header = [cell_value(cell).strip() for cell in header_cells]
            column_count = len([value for value in header if value]) or len(header_cells)
            data_rows = 0
            for row in rows[1:]:
                values = [cell_value(cell).strip() for cell in row.findall("m:c", ns)]
                if any(values):
                    data_rows += 1
            if data_rows == 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="XLSX must contain at least one data row.",
                )
            return data_rows, column_count
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="XLSX file content is invalid."
        ) from error


def _validate_and_profile(file_format: str, content: bytes) -> tuple[int, int]:
    if file_format == "CSV":
        return _csv_stats(content)
    if file_format == "JSON":
        return _json_stats(content)
    return _xlsx_stats(content)


def to_source_response(dataset: SynthMedSourceDataset) -> SynthMedSourceDatasetResponse:
    return SynthMedSourceDatasetResponse(
        id=dataset.id,
        datasetName=dataset.dataset_name,
        description=dataset.description or "",
        originalFilename=dataset.original_filename,
        fileFormat=dataset.file_format,
        fileSizeBytes=dataset.file_size_bytes,
        uploadDate=_iso(dataset.created_at),
        uploadedBy=dataset.owner.full_name if dataset.owner else "Unknown",
        uploadStatus=dataset.upload_status,
        checksumSha256=dataset.checksum_sha256,
        rowCount=dataset.row_count,
        columnCount=dataset.column_count,
    )


def to_generated_response(dataset: SynthMedGeneratedDataset) -> SynthMedGeneratedDatasetResponse:
    return SynthMedGeneratedDatasetResponse(
        id=dataset.id,
        sourceDatasetId=dataset.source_dataset_id,
        datasetName=dataset.dataset_name,
        sourceDatasetName=dataset.source_dataset_name,

        generationMethod=dataset.generation_method,
        generationMode=dataset.generation_mode,
        selectedModel=dataset.selected_model,
        recordCount=dataset.record_count,

        columnCount=dataset.column_count,
        generationDate=_iso(dataset.created_at),
        fileFormat=dataset.file_format,
        fileSizeBytes=dataset.file_size_bytes,
        fileName=Path(dataset.stored_path).name if dataset.stored_path else "",
        status=dataset.status,

    )


def create_source_upload(
    db: Session,
    *,
    settings: Settings,
    user: User,
    upload: UploadFile,
    dataset_name: str,
    description: str,
    request: Request | None = None,
) -> SynthMedSourceDataset:
    filename = getattr(upload, "filename", None) or "upload"

    ext, file_format = _validate_extension(filename)
    mime = _validate_mime(ext, getattr(upload, "content_type", None))

    declared_size = getattr(upload, "size", None)
    if isinstance(declared_size, int) and declared_size > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds the {settings.max_upload_bytes // (1024 * 1024)} MB upload limit.",
        )
    content = upload.file.read(settings.max_upload_bytes + 1)
    if not content:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="The uploaded file is empty.")
    if len(content) > settings.max_upload_bytes:

        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds the {settings.max_upload_bytes // (1024 * 1024)} MB upload limit.",
        )

    row_count, column_count = _validate_and_profile(file_format, content)
    dataset_id = str(uuid4())
    storage = SynthMedStorageService(settings)
    relative_path = ""

    try:
        _, relative_path = storage.save_source(dataset_id, filename, content)

        dataset = SynthMedSourceDataset(
            id=dataset_id,
            owner_id=user.id,
            dataset_name=dataset_name.strip() or Path(filename).stem,
            description=(description or "").strip(),
            original_filename=Path(filename).name,
            stored_path=relative_path,
            file_format=file_format,
            file_size_bytes=len(content),
            checksum_sha256=_checksum(content),
            row_count=row_count,
            column_count=column_count,
            upload_status="Uploaded",
            content_type=mime,
        )
        db.add(dataset)
        log_audit(
            db,
            action="synthmed.source_uploaded",
            resource_type="synthmed_source_dataset",
            resource_id=dataset.id,
            actor_id=user.id,
            details={
                "filename": dataset.original_filename,
                "format": dataset.file_format,
                "size_bytes": dataset.file_size_bytes,
                "checksum": dataset.checksum_sha256,
            },
            request=request,
        )
        db.commit()
        db.refresh(dataset)
        return dataset
    except Exception:
        db.rollback()
        try:
            storage.remove_source(relative_path)
        except Exception:
            pass
        raise



def list_sources(db: Session, *, user: User) -> list[SynthMedSourceDataset]:
    stmt = (
        select(SynthMedSourceDataset)
        .where(SynthMedSourceDataset.owner_id == user.id)
        .order_by(SynthMedSourceDataset.created_at.desc())
    )
    return list(db.scalars(stmt).unique())


def get_source(db: Session, dataset_id: str) -> SynthMedSourceDataset:
    dataset = db.get(SynthMedSourceDataset, _validate_dataset_id(dataset_id))

    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source dataset not found.")
    return dataset


def ensure_source_access(dataset: SynthMedSourceDataset, user: User) -> None:
    if user.role != UserRole.ADMINISTRATOR and dataset.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot access this source dataset.")


def list_generated(db: Session, *, user: User) -> list[SynthMedGeneratedDataset]:
    stmt = (
        select(SynthMedGeneratedDataset)
        .where(SynthMedGeneratedDataset.owner_id == user.id)
        .order_by(SynthMedGeneratedDataset.created_at.desc())
    )
    return list(db.scalars(stmt).unique())


def get_generated(db: Session, dataset_id: str) -> SynthMedGeneratedDataset:
    dataset = db.get(SynthMedGeneratedDataset, _validate_dataset_id(dataset_id))

    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generated dataset not found.")
    return dataset


def ensure_generated_access(dataset: SynthMedGeneratedDataset, user: User) -> None:
    if user.role != UserRole.ADMINISTRATOR and dataset.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot access this generated dataset.")


def downloads_payload(db: Session, *, user: User) -> SynthMedDownloadsResponse:
    return SynthMedDownloadsResponse(
        sources=[to_source_response(item) for item in list_sources(db, user=user)],
        generated=[to_generated_response(item) for item in list_generated(db, user=user)],
    )
