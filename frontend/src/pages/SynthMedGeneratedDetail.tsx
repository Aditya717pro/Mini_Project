import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Download, FileJson, FileSpreadsheet, FileText, ShieldCheck, Stethoscope } from 'lucide-react';
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
import {
  asConditionSatisfaction,
  conditionLabel,
  formatBytes,
  formatDateTime,
  formatNumber,
} from '../lib/format';
import type {
  FileFormat,
  SynthMedEvaluationReport,
  SynthMedGeneratedDatasetDetail,
  SynthMedGeneratedEvaluationSummary,
  SynthMedGeneratedPreview,
} from '../types';

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

const scorePercent = (value: unknown): string =>
  typeof value === 'number' && Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : '—';

const errorMessage = (error: unknown) => (error instanceof Error ? error.message : 'Unexpected API error');

export const SynthMedGeneratedDetail = () => {
  const { generatedId = '' } = useParams();
  const {
    getSynthMedGeneratedDetail,
    getSynthMedGeneratedPreview,
    getSynthMedGeneratedConditions,
    getSynthMedGeneratedEvaluation,
    downloadSynthMedGeneratedFormat,
    downloadSynthMedReport,
    exportSynthMedGenerated,
  } = useDemo();

  const [detail, setDetail] = useState<SynthMedGeneratedDatasetDetail | null>(null);
  const [preview, setPreview] = useState<SynthMedGeneratedPreview | null>(null);
  const [conditionReport, setConditionReport] = useState<SynthMedEvaluationReport | null>(null);
  const [evaluation, setEvaluation] = useState<SynthMedGeneratedEvaluationSummary | null>(null);
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

  useEffect(() => {
    if (!detail || detail.generationMode !== 'Conditional') {
      setConditionReport(null);
      return;
    }
    let active = true;
    void getSynthMedGeneratedConditions(generatedId)
      .then((result) => {
        if (active) setConditionReport(result);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [generatedId, detail?.generationMode, getSynthMedGeneratedConditions]);

  useEffect(() => {
    let active = true;
    void getSynthMedGeneratedEvaluation(generatedId)
      .then((result) => {
        if (active) setEvaluation(result);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [generatedId, getSynthMedGeneratedEvaluation]);

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

  const satisfaction = asConditionSatisfaction(conditionReport?.report ?? detail?.conditionSatisfaction);
  const passed = satisfaction?.passed ?? satisfaction?.allConditionsSatisfied;
  const quality = evaluation?.quality ?? null;
  const privacy = evaluation?.privacy ?? null;
  const evaluationSatisfaction = asConditionSatisfaction(evaluation?.conditions);

  return (
    <>
      <PageHeader
        eyebrow="Synthetic data"
        title={detail?.datasetName ?? 'Generated dataset'}
        description="Inspect synthetic records, model and condition details, downloads and evaluation reports."
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
              <InfoRow label="Selected model">{detail.selectedModel || detail.trainingConfig.model || '—'}</InfoRow>
              <InfoRow label="Generation mode">{detail.generationMode || 'Unconditional'}</InfoRow>
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
                  subtitle="Quality, privacy and condition satisfaction reports."
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
              <InfoRow label="Model">{detail.trainingConfig.model || detail.selectedModel || '—'}</InfoRow>
              <InfoRow label="Sampling strategy">{detail.trainingConfig.samplingStrategy || '—'}</InfoRow>
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

          {evaluation?.clinical ? (
            <Card>
              <CardHeader
                title="Clinical validation"
                subtitle="Provenance-aware screening of generated records; not a clinical decision-support result."
                action={<Badge tone={evaluation.clinical.schemaValidation.passed ? 'success' : 'danger'}>
                  {evaluation.clinical.schemaValidation.passed ? 'Schema passed' : 'Schema failed'}
                </Badge>}
              />
              <div className="info-list">
                <InfoRow label="Profile">{evaluation.generationProfile || detail.generationProfile || 'Standard'}</InfoRow>
                <InfoRow label="Method">{evaluation.clinical.clinicalValidation.method || '—'}</InfoRow>
                <InfoRow label="Records checked">{formatNumber(evaluation.clinical.clinicalValidation.totalRecords ?? 0)}</InfoRow>
                <InfoRow label="Attempts">
                  {evaluation.clinical.rejectionSampling.attempts ?? '—'} / {evaluation.clinical.rejectionSampling.maxAttempts ?? '—'}
                </InfoRow>
                <InfoRow label="Generated">{formatNumber(evaluation.clinical.rejectionSampling.sampledRecords ?? 0)}</InfoRow>
                <InfoRow label="Accepted">{formatNumber(evaluation.clinical.rejectionSampling.acceptedRecords ?? 0)}</InfoRow>
                <InfoRow label="Rejected">{formatNumber(evaluation.clinical.rejectionSampling.rejectedRecords ?? 0)}</InfoRow>
              </div>
              {evaluation.clinical.clinicalValidation.classificationCounts ? (
                <div className="stats-grid">
                  {Object.entries(evaluation.clinical.clinicalValidation.classificationCounts).map(([label, value]) => (
                    <div className="stat-card" key={label}>
                      <span className="stat-label">{label.replace(/_/g, ' ')}</span>
                      <strong>{formatNumber(value)}</strong>
                    </div>
                  ))}
                </div>
              ) : null}
              {evaluation.clinical.schemaValidation.errors.length ? (
                <Alert tone="danger" title="Approved output schema errors">
                  {evaluation.clinical.schemaValidation.errors.join('; ')}
                </Alert>
              ) : null}
              {evaluation.clinical.clinicalValidation.warnings?.length ? (
                <Alert tone="warning" title="Clinical warnings">
                  {evaluation.clinical.clinicalValidation.warnings.join('; ')}
                </Alert>
              ) : null}
              {evaluation.clinical.clinicalValidation.limitations?.length ? (
                <ul className="checklist">
                  {evaluation.clinical.clinicalValidation.limitations.map((limitation) => (
                    <li key={limitation}><Stethoscope size={14} />{limitation}</li>
                  ))}
                </ul>
              ) : null}
            </Card>
          ) : null}

          {detail.conditions.length ? (
            <Card>
              <CardHeader
                title="Requested conditions"
                subtitle="Exact equality constraints sent to the SDV sampling API."
                action={<Badge tone="purple">{detail.conditions.length} conditions</Badge>}
              />
              <ul className="checklist">
                {detail.conditions.map((condition, index) => (
                  <li key={index}><ShieldCheck size={14} />{conditionLabel(condition)}</li>
                ))}
              </ul>
            </Card>
          ) : null}

          {satisfaction ? (
            <Card>
              <CardHeader
                title="Condition satisfaction"
                subtitle={satisfaction.method ?? 'Measured from the generated records.'}
                action={
                  passed == null ? undefined : (
                    <Badge tone={passed ? 'success' : 'danger'}>{passed ? 'All conditions satisfied' : 'Not satisfied'}</Badge>
                  )
                }
              />
              {satisfaction.combined ? (
                <div className="info-list">
                  <InfoRow label="Conditions requested">{formatNumber(satisfaction.combined.requestedConditions ?? 0)}</InfoRow>
                  <InfoRow label="Generated records">{formatNumber(satisfaction.combined.totalGeneratedRecords)}</InfoRow>
                  <InfoRow label="Satisfying records">{formatNumber(satisfaction.combined.satisfyingRecords)}</InfoRow>
                  <InfoRow label="Satisfaction">{satisfaction.combined.satisfactionPercentage.toFixed(1)}%</InfoRow>
                </div>
              ) : null}
              {satisfaction.conditions?.length ? (
                <div className="table-wrap">
                  <table className="table table-compact">
                    <thead>
                      <tr>
                        <th>Condition</th>
                        <th className="num">Requested rows</th>
                        <th className="num">Satisfying rows</th>
                        <th className="num">Satisfaction</th>
                      </tr>
                    </thead>
                    <tbody>
                      {satisfaction.conditions.map((result) => (
                        <tr key={result.index}>
                          <td>{conditionLabel({ column: result.column, operator: result.operator, value: result.requestedValue })}</td>
                          <td className="num">{formatNumber(result.requestedRows)}</td>
                          <td className="num">{formatNumber(result.satisfyingRecords)}</td>
                          <td className="num">{result.satisfactionPercentage.toFixed(1)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
              {satisfaction.cohorts?.length ? (
                <ul className="checklist">
                  {satisfaction.cohorts.map((cohort) => (
                    <li key={cohort.index}>
                      <ShieldCheck size={14} />
                      {cohort.conditions.map((condition) => conditionLabel(condition)).join(' AND ')}:{' '}
                      {formatNumber(cohort.satisfyingRecords)}/{formatNumber(cohort.requestedRows)} rows ·{' '}
                      {cohort.passed ? 'Passed' : 'Failed'}
                    </li>
                  ))}
                </ul>
              ) : null}
            </Card>
          ) : null}

          <Card>
            <CardHeader
              title="Evaluation snapshot"
              subtitle={evaluation ? `Reports: ${evaluation.availableReports.join(', ') || 'none'}` : 'Loading report summary…'}
            />
            <div className="info-list">
              <InfoRow label="Generation mode">{evaluation?.generationMode || detail.generationMode || 'Unconditional'}</InfoRow>
              <InfoRow label="Generation profile">{evaluation?.generationProfile || detail.generationProfile || 'Standard'}</InfoRow>
              <InfoRow label="Selected model">{evaluation?.selectedModel || detail.selectedModel || '—'}</InfoRow>
              <InfoRow label="Quality score">{scorePercent(quality?.overallQualityScore)}</InfoRow>
              <InfoRow label="Privacy score">{scorePercent(privacy?.newRowSynthesisScore)}</InfoRow>
              <InfoRow label="Condition report">
                {evaluationSatisfaction
                  ? evaluationSatisfaction.passed === false
                    ? 'Failed'
                    : 'Passed'
                  : 'Not applicable'}
              </InfoRow>
            </div>
            {conditionReport ? (
              <div className="button-stack">
                <Button
                  variant="ghost"
                  size="sm"
                  icon={<Download size={14} />}
                  onClick={() => void downloadSynthMedReport(generatedId, 'conditions')}
                >
                  Download conditions report
                </Button>
              </div>
            ) : null}
          </Card>

          <Alert tone="warning" title="Review before release">
            Statistical similarity and heuristic privacy checks do not establish clinical validity or anonymity.
          </Alert>
        </>
      ) : null}
    </>
  );
};
