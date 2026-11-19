import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Download, FileJson, FileSpreadsheet, FileText, ShieldCheck } from 'lucide-react';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  InfoRow,
  LoadingState,
  PageHeader,
  Pagination,
} from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { formatBytes, formatDateTime, formatNumber } from '../lib/format';
import type { FileFormat, SynthMedGeneratedDatasetDetail, SynthMedGeneratedPreview } from '../types';

const PAGE_SIZE = 20;

const formatIcon = (format: FileFormat) => {
  if (format === 'CSV') return <FileText size={14} />;
  if (format === 'JSON') return <FileJson size={14} />;
  return <FileSpreadsheet size={14} />;
};

const cellText = (value: unknown): string => {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

const errorMessage = (error: unknown) => (error instanceof Error ? error.message : 'Unexpected API error');

export const SynthMedGeneratedDetail = () => {
  const { generatedId = '' } = useParams();
  const {
    getSynthMedGeneratedDetail,
    getSynthMedGeneratedPreview,
    downloadSynthMedGeneratedFormat,
    downloadSynthMedReport,
    exportSynthMedGenerated,
  } = useDemo();

  const [detail, setDetail] = useState<SynthMedGeneratedDatasetDetail | null>(null);
  const [preview, setPreview] = useState<SynthMedGeneratedPreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [page, setPage] = useState(1);
  const [exportFormat, setExportFormat] = useState<FileFormat>('CSV');
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    void getSynthMedGeneratedDetail(generatedId)
      .then((result) => {
        if (!active) return;
        setDetail(result);
        setExportFormat(result.availableFormats[0] ?? result.fileFormat ?? 'CSV');
      })
      .catch((reason: unknown) => {
        if (active) setError(errorMessage(reason));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [generatedId, getSynthMedGeneratedDetail]);

  useEffect(() => {
    let active = true;
    void getSynthMedGeneratedPreview(generatedId, page, PAGE_SIZE)
      .then((result) => {
        if (active) setPreview(result);
      })
      .catch((reason: unknown) => {
        if (active) setError(errorMessage(reason));
      });
    return () => {
      active = false;
    };
  }, [generatedId, page, getSynthMedGeneratedPreview]);

  const runExport = async () => {
    setExporting(true);
    try {
      await exportSynthMedGenerated(generatedId, exportFormat);
      setDetail(await getSynthMedGeneratedDetail(generatedId));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setExporting(false);
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="Synthetic data"
        title={detail?.datasetName ?? 'Generated dataset'}
        description="Inspect synthetic records, download available formats and open quality and privacy reports."
        actions={
          <Link to="/synthmed/generated">
            <Button variant="secondary" icon={<ArrowLeft size={16} />}>
              All generated datasets
            </Button>
          </Link>
        }
      />

      {loading ? (
        <Card><LoadingState label="Loading generated dataset…" /></Card>
      ) : null}
      {error ? <Alert tone="danger" title="Could not load dataset">{error}</Alert> : null}

      {detail ? (
        <>
          <Card>
            <CardHeader
              title="Dataset summary"
              subtitle={detail.modelName || detail.generationMethod}
              action={<Badge tone="success">{detail.status}</Badge>}
            />
            <div className="info-list">
              <InfoRow label="Generated dataset ID"><code className="code small">{detail.id}</code></InfoRow>
              <InfoRow label="Source dataset">{detail.sourceDatasetName}</InfoRow>
              <InfoRow label="Generation job"><code className="code small">{detail.generationJobId || '—'}</code></InfoRow>
              <InfoRow label="Records">{formatNumber(detail.recordCount)}</InfoRow>
              <InfoRow label="Columns">{formatNumber(detail.columnCount)}</InfoRow>
              <InfoRow label="Generated">{formatDateTime(detail.generationDate)}</InfoRow>
              <InfoRow label="Primary file">{detail.fileName || '—'}</InfoRow>
              <InfoRow label="Primary file size">{formatBytes(detail.fileSizeBytes)}</InfoRow>
              <InfoRow label="Training duration">
                {detail.trainingDurationSeconds == null ? '—' : `${detail.trainingDurationSeconds.toFixed(1)} s`}
              </InfoRow>
            </div>
          </Card>

          <div className="grid-2 grid-2-wide">
            <Card>
              <CardHeader
                title="Synthetic record preview"
                subtitle="Read-only view of the stored generated CSV."
                action={<Badge tone="purple">{preview ? formatNumber(preview.totalRecords) : '—'} records</Badge>}
              />
              {!preview ? (
                <LoadingState label="Loading preview…" />
              ) : (
                <>
                  <div className="table-wrap">
                    <table className="table table-compact">
                      <thead>
                        <tr>{preview.columns.map((column) => <th key={column}>{column}</th>)}</tr>
                      </thead>
                      <tbody>
                        {preview.rows.map((row, index) => (
                          <tr key={`${preview.page}-${index}`}>
                            {preview.columns.map((column) => (
                              <td key={column}>{cellText(row[column])}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <Pagination
                    page={preview.page}
                    pageCount={Math.max(1, Math.ceil(preview.totalRecords / preview.pageSize))}
                    onPageChange={setPage}
                    totalLabel={`${formatNumber(preview.totalRecords)} synthetic records`}
                  />
                </>
              )}
            </Card>

            <div className="stack">
              <Card>
                <CardHeader title="Downloads" subtitle="Formats stored with this generation job." />
                <div className="button-stack">
                  {detail.availableFormats.map((format) => (
                    <Button
                      key={format}
                      variant="secondary"
                      size="sm"
                      icon={formatIcon(format)}
                      onClick={() => void downloadSynthMedGeneratedFormat(generatedId, format)}
                    >
                      Download {format}
                    </Button>
                  ))}
                </div>
                <div className="divider" />
                <div className="field">
                  <span className="field-label">Create another format</span>
                  <div className="inline-controls">
                    <select
                      className="input input-sm"
                      value={exportFormat}
                      onChange={(event) => setExportFormat(event.target.value as FileFormat)}
                      aria-label="Export format"
                    >
                      <option value="CSV">CSV</option>
                      <option value="XLSX">XLSX</option>
                      <option value="JSON">JSON</option>
                    </select>
                    <Button
                      size="sm"
                      disabled={exporting}
                      icon={<Download size={14} />}
                      onClick={() => void runExport()}
                    >
                      {exporting ? 'Exporting…' : 'Export'}
                    </Button>
                  </div>
                </div>
              </Card>

              <Card>
                <CardHeader
                  title="Evaluation reports"
                  subtitle="Review before release."
                  action={<ShieldCheck size={17} />}
                />
                {detail.reportTypes.length === 0 ? (
                  <p className="muted small">No reports are attached to this dataset.</p>
                ) : (
                  <div className="button-stack">
                    {detail.reportTypes.map((reportType) => (
                      <Button
                        key={reportType}
                        variant="ghost"
                        size="sm"
                        icon={<Download size={14} />}
                        onClick={() => void downloadSynthMedReport(generatedId, reportType)}
                      >
                        Download {reportType} report
                      </Button>
                    ))}
                  </div>
                )}
                <Link to={`/synthmed/evaluation?dataset=${encodeURIComponent(generatedId)}`}>
                  <Button variant="secondary" size="sm">Open evaluation</Button>
                </Link>
              </Card>
            </div>
          </div>

          <Card>
            <CardHeader title="Training configuration" subtitle="Recorded with the generation job." />
            <div className="info-list">
              <InfoRow label="Epochs">{detail.trainingConfig.epochs ?? '—'}</InfoRow>
              <InfoRow label="Batch size">{detail.trainingConfig.batchSize ?? '—'}</InfoRow>
              <InfoRow label="Seed">{detail.trainingConfig.seed ?? 'Random'}</InfoRow>
              <InfoRow label="Missingness">
                {detail.trainingConfig.preserveMissingness ? 'Preserved' : 'Rows with missing values removed'}
              </InfoRow>
            </div>
            <div className="chip-grid">
              {detail.trainingConfig.includedColumns.map((column) => (
                <span className="chip" key={column}>{column}</span>
              ))}
            </div>
          </Card>

          <Alert tone="warning" title="Review before release">
            Statistical similarity and heuristic privacy checks do not establish clinical validity or anonymity.
          </Alert>
        </>
      ) : null}
    </>
  );
};
