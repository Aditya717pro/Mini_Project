import readXlsxFile from 'read-excel-file';
import type { ColumnProfile, ExtractPreview, FileFormat } from '../types';

export const MAX_FILE_BYTES = 25 * 1024 * 1024;
export const ACCEPTED_EXTENSIONS = ['.csv', '.xlsx', '.json'];

export class UploadValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'UploadValidationError';
  }
}

const extensionOf = (name: string) => {
  const index = name.lastIndexOf('.');
  return index === -1 ? '' : name.slice(index).toLowerCase();
};

export const formatFromFile = (file: File): FileFormat | null => {
  const ext = extensionOf(file.name);
  if (ext === '.csv') return 'CSV';
  if (ext === '.xlsx') return 'XLSX';
  if (ext === '.json') return 'JSON';
  return null;
};

export const validateFileBasics = (file: File) => {
  const format = formatFromFile(file);
  if (!format) {
    throw new UploadValidationError(
      `Unsupported file type “${extensionOf(file.name) || 'unknown'}”. Upload a CSV, XLSX or JSON file.`,
    );
  }
  if (file.size === 0) {
    throw new UploadValidationError('The selected file is empty.');
  }
  if (file.size > MAX_FILE_BYTES) {
    throw new UploadValidationError(
      `File is ${(file.size / 1024 / 1024).toFixed(1)} MB. The demo limit is 25 MB.`,
    );
  }
  return format;
};

const isBlank = (value: unknown) =>
  value === null ||
  value === undefined ||
  (typeof value === 'string' && value.trim() === '');

const normaliseCell = (value: unknown): unknown => {
  if (value instanceof Date) return value.toISOString().slice(0, 10);
  if (typeof value === 'string') return value.trim();
  return value ?? null;
};

const parseCsv = (text: string): string[][] => {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = '';
  let inQuotes = false;

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    if (inQuotes) {
      if (char === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 1;
        } else {
          inQuotes = false;
        }
      } else {
        field += char;
      }
      continue;
    }

    if (char === '"') {
      inQuotes = true;
    } else if (char === ',') {
      row.push(field);
      field = '';
    } else if (char === '\n') {
      row.push(field);
      rows.push(row);
      row = [];
      field = '';
    } else if (char === '\r') {
      if (text[i + 1] === '\n') i += 1;
      row.push(field);
      rows.push(row);
      row = [];
      field = '';
    } else {
      field += char;
    }
  }

  if (inQuotes) {
    throw new UploadValidationError('CSV appears to be malformed: an opening quote was never closed.');
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows;
};

const DATE_PATTERN = /^(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})([T ].*)?$/;
const BOOLEAN_TOKENS = new Set(['true', 'false', 'yes', 'no', 'y', 'n']);

const inferType = (values: unknown[]): ColumnProfile['inferredType'] => {
  const present = values.filter((value) => !isBlank(value));
  if (present.length === 0) return 'Empty';

  let numeric = 0;
  let dates = 0;
  let booleans = 0;

  present.forEach((raw) => {
    const value = String(normaliseCell(raw));
    if (value !== '' && Number.isFinite(Number(value))) numeric += 1;
    if (DATE_PATTERN.test(value.trim()) && Number.isNaN(Number(value))) dates += 1;
    if (BOOLEAN_TOKENS.has(value.trim().toLowerCase())) booleans += 1;
  });

  const ratio = (count: number) => count / present.length;
  if (ratio(booleans) >= 0.95) return 'Boolean';
  if (ratio(numeric) >= 0.9) return 'Numeric';
  if (ratio(dates) >= 0.8) return 'Date';
  if (ratio(numeric) >= 0.5 || ratio(dates) >= 0.5) return 'Mixed';
  return 'Text';
};

const buildPreview = (
  sheetName: string,
  headerRow: unknown[],
  dataRows: unknown[][],
): ExtractPreview => {
  const headers = headerRow.map((header, index) => {
    const cleaned = String(header ?? '').trim();
    return cleaned || `column_${index + 1}`;
  });

  const records: Record<string, unknown>[] = dataRows
    .filter((row) => row.some((cell) => !isBlank(cell)))
    .map((row) => {
      const record: Record<string, unknown> = {};
      headers.forEach((header, index) => {
        record[header] = normaliseCell(row[index]);
      });
      return record;
    });

  if (records.length === 0) {
    throw new UploadValidationError('No data rows were found below the header row.');
  }

  const columns: ColumnProfile[] = headers.map((name) => {
    const values = records.map((record) => record[name]);
    const missing = values.filter(isBlank).length;
    const present = values.filter((value) => !isBlank(value));
    const unique = new Set(present.map((value) => String(value)));
    return {
      name,
      inferredType: inferType(values),
      missing,
      missingPct: Math.round((missing / records.length) * 1000) / 10,
      uniqueSample: unique.size,
      sampleValues: Array.from(unique).slice(0, 3).map((value) => String(value).slice(0, 40)),
    };
  });

  const totalCells = records.length * headers.length;
  const missingCells = columns.reduce((sum, column) => sum + column.missing, 0);
  const seen = new Set<string>();
  let duplicateRows = 0;
  records.forEach((record) => {
    const key = JSON.stringify(headers.map((header) => record[header] ?? null));
    if (seen.has(key)) duplicateRows += 1;
    else seen.add(key);
  });

  return {
    sheetName,
    rowCount: records.length,
    columnCount: headers.length,
    missingCells,
    missingPct: totalCells === 0 ? 0 : Math.round((missingCells / totalCells) * 1000) / 10,
    duplicateRows,
    duplicatePct: Math.round((duplicateRows / records.length) * 1000) / 10,
    columns,
    previewRows: records.slice(0, 5),
  };
};

const extractCsv = async (file: File): Promise<ExtractPreview> => {
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer.slice(0, 4096));
  if (bytes.includes(0)) {
    throw new UploadValidationError('File content is binary but the extension is .csv.');
  }
  const text = new TextDecoder('utf-8', { fatal: false }).decode(buffer).replace(/^\uFEFF/, '');
  const rows = parseCsv(text).filter((row) => row.some((cell) => cell.trim() !== ''));
  if (rows.length < 2) {
    throw new UploadValidationError('CSV must contain a header row and at least one data row.');
  }
  return buildPreview('CSV data', rows[0], rows.slice(1));
};

const extractJson = async (file: File): Promise<ExtractPreview> => {
  const text = await file.text();
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new UploadValidationError('JSON could not be parsed. Check for syntax errors or truncation.');
  }

  let records: unknown;
  if (Array.isArray(parsed)) {
    records = parsed;
  } else if (parsed && typeof parsed === 'object') {
    const firstArray = Object.values(parsed as Record<string, unknown>).find((value) =>
      Array.isArray(value),
    );
    records = firstArray ?? [parsed];
  }

  if (!Array.isArray(records) || records.length === 0) {
    throw new UploadValidationError('JSON must contain a non-empty array of records.');
  }
  if (!records.every((item) => item !== null && typeof item === 'object' && !Array.isArray(item))) {
    throw new UploadValidationError('JSON records must be objects with named fields.');
  }

  const objects = records as Record<string, unknown>[];
  const headers = Array.from(new Set(objects.flatMap((record) => Object.keys(record))));
  if (headers.length === 0) {
    throw new UploadValidationError('JSON records do not contain any fields.');
  }
  const dataRows = objects.map((record) => headers.map((header) => record[header] ?? null));
  return buildPreview('JSON records', headers, dataRows);
};

const extractXlsx = async (file: File): Promise<ExtractPreview> => {
  const buffer = await file.arrayBuffer();
  const signature = new Uint8Array(buffer.slice(0, 4));
  if (!(signature[0] === 0x50 && signature[1] === 0x4b)) {
    throw new UploadValidationError('File content is not a valid XLSX workbook (missing ZIP signature).');
  }

  let rows: unknown[][];
  try {
    rows = (await readXlsxFile(buffer)) as unknown[][];
  } catch {
    throw new UploadValidationError('Workbook could not be read. It may be corrupt or password protected.');
  }

  const cleaned = rows.filter((row) => row.some((cell) => !isBlank(cell)));
  if (cleaned.length < 2) {
    throw new UploadValidationError('The first worksheet must contain a header row and data rows.');
  }
  return buildPreview('Worksheet 1', cleaned[0], cleaned.slice(1));
};

export const extractFile = async (
  file: File,
): Promise<{ preview: ExtractPreview; checksum: string; format: FileFormat }> => {
  const format = validateFileBasics(file);
  const buffer = await file.arrayBuffer();
  const digest = await crypto.subtle.digest('SHA-256', buffer);
  const checksum = Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');

  let preview: ExtractPreview;
  if (format === 'CSV') preview = await extractCsv(file);
  else if (format === 'JSON') preview = await extractJson(file);
  else preview = await extractXlsx(file);

  return { preview, checksum, format };
};
