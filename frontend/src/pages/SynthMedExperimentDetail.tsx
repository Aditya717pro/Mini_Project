import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { BarChart3, Download, GitBranch, RefreshCw, RotateCcw, Settings2, ShieldCheck } from 'lucide-react';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  InfoRow,
  LoadingState,
  Modal,
  PageHeader,
  SectionTitle,
  type Tone,
} from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { formatBytes, formatDateTime, formatNumber } from '../lib/format';
import type {
  SynthMedConfigSnapshot,
  SynthMedEvaluationReport,
  SynthMedExperimentHistory,
  SynthMedExperimentReport,
  SynthMedExperimentResponse,
  SynthMedGeneratedDatasetDetail,
  SynthMedGenerationJob,
  SynthMedUtilityEvaluation,
} from '../types';

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};

const cellText = (value: unknown): string => {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

const asStrings = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];

const scoreText = (value: unknown): string =>
  typeof value === 'number' && Number.isFinite(value)
    ? `${(value <= 1 ? value * 100 : value).toFixed(1)}${value <= 1 ? '%' : ''}`
    : cellText(value);

const statusTone = (status: string): Tone => {
  const value = status.toLowerCase();
  if (value.includes('complete') || value.includes('ready') || value.includes('passed')) return 'success';
  if (value.includes('fail') || value.includes('error') || value.includes('reject')) return 'danger';
  if (value.includes('run') || value.includes('process') || value.includes('queued')) return 'info';
  if (value.includes('review') || value.includes('pending')) return 'warning';
  return 'neutral';
};

const flattenMetrics = (value: unknown, prefix = ''): [string, unknown][] => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return [];
  return Object.entries(value).flatMap(([key, entry]) => {
    const label = prefix ? `${prefix}.${key}` : key;
    if (entry && typeof entry === 'object' && !Array.isArray(entry)) return flattenMetrics(entry, label);
    return [[label, entry] as [string, unknown]];
  });
};

const priorityMetrics = [
  'mae', 'mse', 'rmse', 'r2', 'r_squared',
  'accuracy', 'balancedaccuracy', 'balanced_accuracy',
  'precisionmacro', 'precision_macro', 'recallmacro', 'recall_macro',
  'f1macro', 'f1_macro', 'f1weighted', 'f1_weighted',
];

const MetricTable = ({ source }: { source: unknown }) => {
  const rows = flattenMetrics(source);
  if (rows.length === 0) return <div className="inline-empty">No metrics were returned for this evaluation.</div>;
  const priority = rows.filter(([key]) => priorityMetrics.includes(key.toLowerCase()));
  const ordered = priority.length
    ? [...priority, ...rows.filter(([key]) => !priority.includes(rows.find((row) => row[0] === key)!))]
    : rows;
  return (
    <div className="table-wrap">
      <table className="table table-compact">
        <thead><tr><th>Metric</th><th className="num">Value</th></tr></thead>
        <tbody>
          {ordered.map(([key, value]) => (
            <tr key={key}>
              <td><code className="code small">{key}</code></td>
              <td className="num">{scoreText(value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

const ConfigCard = ({ snapshots, experiment }: { snapshots: SynthMedConfigSnapshot[]; experiment: SynthMedExperimentResponse }) => {
  const snapshot = snapshots.find((item) => item.id === experiment.configurationSnapshotId)
    ?? snapshots[0]
    ?? experiment.configurationSnapshot;
  if (!snapshot) {
    return (
      <Card>
        <CardHeader title="Immutable configuration" subtitle="No snapshot was attached to this experiment." />
        <div className="inline-empty">The experiment record has no configuration snapshot ID.</div>
      </Card>
    );
  }
  const warnings = [...asStrings(snapshot.config.reuseWarnings), ...asStrings(snapshot.config.warnings)];
  return (
    <Card>
      <CardHeader
        title="Immutable configuration"
        subtitle="Stored at generation time; reuse starts from this exact snapshot."
        action={<Badge tone={snapshot.isImmutable ? 'success' : 'warning'}>{snapshot.isImmutable ? 'Immutable' : 'Mutable'}</Badge>}
      />
      <div className="info-list">
        <InfoRow label="Snapshot ID"><code className="code small">{snapshot.id}</code></InfoRow>
        <InfoRow label="Model">{snapshot.modelName || '—'}</InfoRow>
        <InfoRow label="Config hash"><code className="code small">{snapshot.configHash || '—'}</code></InfoRow>
        <InfoRow label="Generation job"><code className="code small">{snapshot.jobId ?? '—'}</code></InfoRow>
        <InfoRow label="Source dataset"><code className="code small">{snapshot.sourceDatasetId ?? '—'}</code></InfoRow>
        <InfoRow label="Created">{snapshot.createdAt ? formatDateTime(snapshot.createdAt) : '—'}</InfoRow>
      </div>
      {warnings.length ? <Alert tone="warning" title="Configuration warnings">{warnings.join('; ')}</Alert> : null}
      <SectionTitle>Stored parameters</SectionTitle>
      <div className="table-wrap">
        <table className="table table-compact">
          <thead><tr><th>Parameter</th><th>Value</th></tr></thead>
          <tbody>
            {Object.entries(snapshot.config)
              .filter(([key]) => !key.toLowerCase().includes('path') && !key.toLowerCase().includes('stored'))
              .map(([key, value]) => (
                <tr key={key}>
                  <td><code className="code small">{key}</code></td>
                  <td className="cell-wrap"><code className="code small">{cellText(value)}</code></td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
};

export const SynthMedExperimentDetail = () => {
  const { experimentId = '' } = useParams();
  const {
    getSynthMedExperiment,
    getSynthMedExperimentHistory,
    getSynthMedExperimentConfigurations,
    getSynthMedExperimentReport,
    downloadSynthMedExperimentReport,
    listSynthMedUtilityEvaluations,
    getSynthMedGeneratedDetail,
    getSynthMedPrivacyReport,
    downloadSynthMedReport,
    downloadSynthMedUtilityEvaluationReport,
    reuseSynthMedExperimentConfiguration,
  } = useDemo();

  const [experiment, setExperiment] = useState<SynthMedExperimentResponse | null>(null);
  const [history, setHistory] = useState<SynthMedExperimentHistory | null>(null);
  const [snapshots, setSnapshots] = useState<SynthMedConfigSnapshot[]>([]);
  const [report, setReport] = useState<SynthMedExperimentReport | null>(null);
  const [utility, setUtility] = useState<SynthMedUtilityEvaluation | null>(null);
  const [generatedDetail, setGeneratedDetail] = useState<SynthMedGeneratedDatasetDetail | null>(null);
  const [privacy, setPrivacy] = useState<SynthMedEvaluationReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reuseOpen, setReuseOpen] = useState(false);
  const [reuseAsNewExperiment, setReuseAsNewExperiment] = useState(true);
  const [reusing, setReusing] = useState(false);
  const [reuseJob, setReuseJob] = useState<SynthMedGenerationJob | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const base = await getSynthMedExperiment(experimentId);
      setExperiment(base);
      const [historyResult, snapshotsResult, reportResult, utilityResult, generatedResult, privacyResult] = await Promise.all([
        getSynthMedExperimentHistory(experimentId).catch(() => null),
        getSynthMedExperimentConfigurations(experimentId).catch(() => []),
        getSynthMedExperimentReport(experimentId).catch(() => null),
        listSynthMedUtilityEvaluations().catch(() => []),
        base.generatedDatasetId ? getSynthMedGeneratedDetail(base.generatedDatasetId).catch(() => null) : Promise.resolve(null),
        base.privacyReport.available && base.generatedDatasetId
          ? getSynthMedPrivacyReport(base.generatedDatasetId).catch(() => null)
          : Promise.resolve(null),
      ]);
      setHistory(historyResult);
      setSnapshots(snapshotsResult ?? []);
      setReport(reportResult);
      const matchingUtility = (utilityResult ?? []).find((item) => item.id === base.utilityEvaluation.id)
        ?? (utilityResult ?? []).filter((item) => item.generatedDatasetId === base.generatedDatasetId).slice(-1)[0]
        ?? null;
      setUtility(matchingUtility);
      setGeneratedDetail(generatedResult);
      setPrivacy(privacyResult);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unexpected API error');
    } finally {
      setLoading(false);
    }
  }, [
    experimentId,
    getSynthMedExperiment,
    getSynthMedExperimentHistory,
    getSynthMedExperimentConfigurations,
    getSynthMedExperimentReport,
    listSynthMedUtilityEvaluations,
    getSynthMedGeneratedDetail,
    getSynthMedPrivacyReport,
  ]);

  useEffect(() => {
    void load();
  }, [load]);

  const runReuse = async () => {
    setReusing(true);
    setReuseJob(null);
    try {
      const job = await reuseSynthMedExperimentConfiguration(experimentId, { reuseAsNewExperiment });
      setReuseJob(job);
    } catch {
      // Store already reports the error.
    } finally {
      setReusing(false);
    }
  };

  const preservation = generatedDetail?.sourcePreservation ?? null;
  const utilityMetrics = utility?.metrics ?? experiment?.utilityEvaluation.metrics ?? null;
  const utilityComparison = utility?.comparison ?? experiment?.utilityEvaluation.comparison ?? null;
  const reportAvailability = useMemo(
    () => Object.entries(experiment?.reportAvailability ?? {}).filter(([, available]) => available),
    [experiment],
  );
  const reuseWarnings = useMemo(
    () => asStrings((reuseJob?.config as { reuseWarnings?: unknown })?.reuseWarnings),
    [reuseJob],
  );

  return (
    <>
      <Link to="/synthmed/experiments" className="back-link"><RefreshCw size={15} /> Back to experiments</Link>
      <PageHeader
        eyebrow={`SynthMed experiment · ${experimentId.slice(0, 12)}`}
        title={experiment?.name ?? 'Experiment'}
        description={experiment?.description || 'Stored generation configuration, linked versions, lineage and evaluation reports.'}
        actions={
          experiment ? (
            <>
              <Button variant="secondary" icon={<RefreshCw size={15} />} onClick={() => void load()}>Refresh</Button>
              <Button
                variant="secondary"
                icon={<Download size={15} />}
                onClick={() => void downloadSynthMedExperimentReport(experiment.id)}
              >
                Download report
              </Button>
              <Button icon={<RotateCcw size={15} />} onClick={() => { setReuseJob(null); setReuseOpen(true); }}>
                Reuse configuration
              </Button>
            </>
          ) : undefined
        }
      />

      {error ? <Alert tone="danger" title="Could not load experiment">{error}</Alert> : null}
      {loading ? (
        <Card><LoadingState label="Loading experiment record…" /></Card>
      ) : !experiment ? (
        <Card>
          <EmptyState title="Experiment not found" description="No experiment was returned for this ID." />
        </Card>
      ) : (
        <>
          <div className="detail-badges">
            <Badge tone={statusTone(experiment.status)}>{experiment.status}</Badge>
            <Badge tone="purple">SynthMed experiment</Badge>
            <Badge>{report ? `Report ${formatDateTime(report.generatedAt)}` : 'Report not generated'}</Badge>
          </div>

          <Card>
            <CardHeader title="Experiment record" subtitle={experiment.description || 'Stored provenance record.'} />
            <div className="info-list">
              <InfoRow label="Experiment ID"><code className="code small">{experiment.id}</code></InfoRow>
              <InfoRow label="Owner"><code className="code small">{experiment.ownerId}</code></InfoRow>
              <InfoRow label="Status"><Badge tone={statusTone(experiment.status)}>{experiment.status}</Badge></InfoRow>
              <InfoRow label="Generation job">
                {experiment.generationJobId ? <code className="code small">{experiment.generationJobId}</code> : '—'}
              </InfoRow>
              <InfoRow label="Source dataset">
                {experiment.sourceDatasetId ? <code className="code small">{experiment.sourceDatasetId}</code> : '—'}
              </InfoRow>
              <InfoRow label="Generated dataset">
                {experiment.generatedDatasetId ? (
                  <Link to={`/synthmed/generated/${experiment.generatedDatasetId}`} className="inline-link">
                    <code className="code small">{experiment.generatedDatasetId}</code>
                  </Link>
                ) : '—'}
              </InfoRow>
              <InfoRow label="Source version">
                {experiment.sourceVersionId && experiment.sourceDatasetId ? (
                  <Link to={`/synthmed/datasets/${experiment.sourceDatasetId}/versions/${experiment.sourceVersionId}`} className="inline-link">
                    <code className="code small">{experiment.sourceVersionId}</code>
                  </Link>
                ) : experiment.sourceVersionId ? (
                  <code className="code small">{experiment.sourceVersionId}</code>
                ) : 'Not pinned to a version'}
              </InfoRow>
              <InfoRow label="Generated version">
                {experiment.generatedVersionId && experiment.generatedDatasetId ? (
                  <Link to={`/synthmed/datasets/${experiment.generatedDatasetId}/versions/${experiment.generatedVersionId}`} className="inline-link">
                    <code className="code small">{experiment.generatedVersionId}</code>
                  </Link>
                ) : 'Not pinned to a version'}
              </InfoRow>
              <InfoRow label="Comparison">
                {experiment.comparisonId && experiment.generatedDatasetId ? (
                  <Link to={`/synthmed/comparison/${experiment.comparisonId}`} className="inline-link">
                    <code className="code small">{experiment.comparisonId}</code>
                  </Link>
                ) : '—'}
              </InfoRow>
              <InfoRow label="Notes">{experiment.notes || '—'}</InfoRow>
              <InfoRow label="Updated">{experiment.updatedAt ? formatDateTime(experiment.updatedAt) : '—'}</InfoRow>
            </div>
            {Object.keys(asRecord(experiment.metadata)).length ? (
              <>
                <SectionTitle>Experiment metadata</SectionTitle>
                <div className="info-list">
                  {Object.entries(asRecord(experiment.metadata)).map(([key, value]) => (
                    <InfoRow key={key} label={key}>{cellText(value)}</InfoRow>
                  ))}
                </div>
              </>
            ) : null}
          </Card>

          <ConfigCard snapshots={snapshots} experiment={experiment} />

          <div className="grid-2 grid-2-wide">
            <Card>
              <CardHeader title="P3 privacy summary" subtitle="Heuristic privacy checks attached to this experiment." action={<ShieldCheck size={17} />} />
              <div className="info-list">
                <InfoRow label="Available"><Badge tone={experiment.privacyReport.available ? 'success' : 'neutral'}>{experiment.privacyReport.available ? 'Yes' : 'No'}</Badge></InfoRow>
                <InfoRow label="Report ID"><code className="code small">{experiment.privacyReport.id ?? '—'}</code></InfoRow>
                <InfoRow label="Method">{experiment.privacyReport.method || '—'}</InfoRow>
                <InfoRow label="Score">{scoreText(experiment.privacyReport.score)}</InfoRow>
              <InfoRow label="Report file">{experiment.privacyReport.reportAvailable ? 'Available' : '—'}</InfoRow>
              <InfoRow label="Created">{experiment.privacyReport.createdAt ? formatDateTime(experiment.privacyReport.createdAt) : '—'}</InfoRow>
            </div>
            {experiment.generatedDatasetId && experiment.privacyReport.reportAvailable ? (
              <div className="inline-actions">
                <Button
                  size="sm"
                  variant="secondary"
                  icon={<Download size={14} />}
                  onClick={() => void downloadSynthMedReport(experiment.generatedDatasetId!, 'privacy')}
                >
                  Download privacy report
                </Button>
              </div>
            ) : null}
            {privacy ? (
                <>
                  <SectionTitle>Privacy report snapshot</SectionTitle>
                  <MetricTable source={privacy.report} />
                </>
              ) : null}
            </Card>

            <Card>
              <CardHeader title="P4 utility summary" subtitle="TSTR / TRTR machine-learning utility metrics." action={<BarChart3 size={17} />} />
              <div className="info-list">
                <InfoRow label="Available"><Badge tone={experiment.utilityEvaluation.available ? 'success' : 'neutral'}>{experiment.utilityEvaluation.available ? 'Yes' : 'No'}</Badge></InfoRow>
                <InfoRow label="Evaluation ID"><code className="code small">{experiment.utilityEvaluation.id ?? utility?.id ?? '—'}</code></InfoRow>
                <InfoRow label="Status"><Badge tone={statusTone(utility?.status || experiment.utilityEvaluation.status || 'unknown')}>{utility?.status || experiment.utilityEvaluation.status || '—'}</Badge></InfoRow>
                <InfoRow label="Model">{utility?.modelName || experiment.utilityEvaluation.modelName || '—'}</InfoRow>
                <InfoRow label="Target column">{utility?.targetColumn || experiment.utilityEvaluation.targetColumn || '—'}</InfoRow>
                <InfoRow label="Evaluation type">
                  {utility?.evaluationType || experiment.utilityEvaluation.evaluationType || '—'}
                </InfoRow>
                <InfoRow label="Task type">
                  {String(asRecord(utility?.metrics).taskType ?? experiment.utilityEvaluation.taskType ?? '—')}
                </InfoRow>
              </div>
              {utility?.id ? (
                <div className="inline-actions">
                  <Button
                    size="sm"
                    variant="secondary"
                    icon={<Download size={14} />}
                    disabled={!experiment.reportAvailability.utilityReport}
                    onClick={() => void downloadSynthMedUtilityEvaluationReport(utility.id, 'json')}
                  >
                    JSON
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    icon={<Download size={14} />}
                    disabled={!experiment.reportAvailability.utilityCsvReport}
                    onClick={() => void downloadSynthMedUtilityEvaluationReport(utility.id, 'csv')}
                  >
                    CSV
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    icon={<Download size={14} />}
                    disabled={!experiment.reportAvailability.utilityPdfReport}
                    onClick={() => void downloadSynthMedUtilityEvaluationReport(utility.id, 'pdf')}
                  >
                    PDF
                  </Button>
                </div>
              ) : null}
              <SectionTitle>Metrics</SectionTitle>
              <MetricTable source={utilityMetrics} />
              {utilityComparison && Object.keys(asRecord(utilityComparison)).length ? (
                <>
                  <SectionTitle>Comparison</SectionTitle>
                  <MetricTable source={utilityComparison} />
                </>
              ) : null}
              {utility?.warnings.length ? (
                <Alert tone="warning" title="Utility warnings">{utility.warnings.join('; ')}</Alert>
              ) : null}
            </Card>
          </div>

          <Card>
            <CardHeader
              title="Comparison summary"
              subtitle="Distribution similarity recorded with the experiment."
              action={<Badge tone={experiment.comparisonSummary.available ? 'success' : 'neutral'}>{experiment.comparisonSummary.available ? 'Available' : 'None'}</Badge>}
            />
            <div className="info-list">
              <InfoRow label="Comparison ID"><code className="code small">{experiment.comparisonSummary.id ?? '—'}</code></InfoRow>
              <InfoRow label="Name">{experiment.comparisonSummary.name || '—'}</InfoRow>
              <InfoRow label="Score">{scoreText(experiment.comparisonSummary.score)}</InfoRow>
              <InfoRow label="Report">{experiment.comparisonSummary.reportAvailable ? 'Available' : '—'}</InfoRow>
            </div>
            {reportAvailability.length ? (
              <>
                <SectionTitle>Available reports</SectionTitle>
                <div className="chip-grid">
                  {reportAvailability.map(([name]) => <span className="chip" key={name}>{name}</span>)}
                </div>
              </>
            ) : null}
          </Card>

          {preservation ? (
            <Card>
              <CardHeader title="Source preservation" subtitle="Demographic and clinical distribution checks from the generated dataset." />
              <div className="info-list">
                {Object.entries(asRecord(preservation)).map(([key, value]) => (
                  <InfoRow key={key} label={key}>{cellText(value)}</InfoRow>
                ))}
              </div>
            </Card>
          ) : null}

          {generatedDetail?.schemaValidation ? (
            <Card>
              <CardHeader
                title="Schema validation"
                subtitle="Approved output columns recorded with the generated dataset."
                action={<Badge tone={generatedDetail.schemaValidation.passed ? 'success' : 'danger'}>{generatedDetail.schemaValidation.passed ? 'Passed' : 'Failed'}</Badge>}
              />
              {generatedDetail.schemaValidation.errors.length ? (
                <Alert tone="danger" title="Validation errors">{generatedDetail.schemaValidation.errors.join('; ')}</Alert>
              ) : (
                <div className="inline-empty">No schema validation errors were recorded.</div>
              )}
              {generatedDetail.validationStatus ? (
                <p className="muted small">Validation status: {generatedDetail.validationStatus}</p>
              ) : null}
              {generatedDetail.fileSizeBytes ? (
                <p className="muted small">Primary file size: {formatBytes(generatedDetail.fileSizeBytes)}</p>
              ) : null}
            </Card>
          ) : null}

          <Card>
            <CardHeader title="Attempt history" subtitle="Every attempt and status change recorded for this experiment." />
            {history && history.attempts.length ? (
              <div className="table-wrap">
                <table className="table table-compact">
                  <thead><tr><th>Attempt</th><th>Status</th><th>Created</th><th>Detail</th></tr></thead>
                  <tbody>
                    {history.attempts.map((attempt, index) => {
                      const row = asRecord(attempt);
                      return (
                        <tr key={index}>
                          <td>{formatNumber(index + 1)}</td>
                          <td><Badge tone={statusTone(cellText(row.status ?? row.action ?? 'recorded'))}>{cellText(row.status ?? row.action ?? 'Recorded')}</Badge></td>
                          <td>{cellText(row.createdAt ?? row.timestamp)}</td>
                          <td className="cell-wrap">{cellText(row.detail ?? row.message ?? row.note ?? attempt)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="inline-empty">No attempt history was returned for this experiment.</div>
            )}
          </Card>

          <Card>
            <CardHeader title="Linked lineage" subtitle="Version and report relationships recorded with the experiment." action={<GitBranch size={17} />} />
            {experiment.lineage.length ? (
              <div className="version-timeline">
                {experiment.lineage.map((event) => (
                  <div className="version-item" key={event.id}>
                    <span className="version-dot" />
                    <div className="version-body">
                      <div className="version-head"><strong>{event.eventType}</strong><span className="muted small">{formatDateTime(event.createdAt)}</span></div>
                      <p><code className="code small">{event.parentResourceId}</code> → <code className="code small">{event.childResourceId}</code></p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="inline-empty">No lineage events were returned for this experiment.</div>
            )}
          </Card>
        </>
      )}

      <Modal
        open={reuseOpen}
        title="Reuse configuration"
        subtitle="Start a new generation job from this experiment's stored immutable configuration."
        onClose={() => setReuseOpen(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setReuseOpen(false)}>Close</Button>
            <Button icon={<RotateCcw size={15} />} disabled={reusing} onClick={() => void runReuse()}>
              {reusing ? 'Reusing…' : 'Start job'}
            </Button>
          </>
        }
      >
        <div className="stack">
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={reuseAsNewExperiment}
              onChange={(event) => setReuseAsNewExperiment(event.target.checked)}
            />
            Create a new experiment record for the reused job
          </label>
          <Alert tone="info" title="No hidden regeneration">
            The backend validates the snapshot hash and returns any reuse warnings with the new job.
          </Alert>
          {reuseJob ? (
            <Card>
              <CardHeader title="Reuse job started" subtitle="The backend accepted the stored configuration." action={<Settings2 size={17} />} />
              <div className="info-list">
                <InfoRow label="Job ID"><code className="code small">{reuseJob.id}</code></InfoRow>
                <InfoRow label="Status"><Badge tone={statusTone(reuseJob.status)}>{reuseJob.status}</Badge></InfoRow>
                <InfoRow label="Model">{reuseJob.modelName}</InfoRow>
                <InfoRow label="Records requested">{formatNumber(reuseJob.requestedRecordCount)}</InfoRow>
              </div>
              {reuseWarnings.length ? <Alert tone="warning" title="Reuse warnings">{reuseWarnings.join('; ')}</Alert> : null}
              <Link to="/synthmed/generate"><Button variant="secondary" size="sm">Open generation workspace</Button></Link>
            </Card>
          ) : null}
        </div>
      </Modal>
    </>
  );
};
