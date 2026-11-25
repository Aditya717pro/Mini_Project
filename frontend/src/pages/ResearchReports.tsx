import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Download, FileText, RefreshCw, ShieldCheck } from 'lucide-react';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  LoadingState,
  PageHeader,
  SectionTitle,
  type Tone,
} from '../components/ui';
import { formatBytes, formatDateTime } from '../lib/format';
import { useDemo } from '../store/DemoStore';
import type {
  ResearchReport,
  ResearchReportGeneratePayload,
  ResearchReportStatus,
  ResearchReportType,
  SynthMedUtilityEvaluation,
} from '../types';

interface Option {
  value: string;
  label: string;
}

const REPORT_TYPES: { value: ResearchReportType; label: string; description: string }[] = [
  { value: 'dataset-profile', label: 'Dataset Profile PDF', description: 'Persisted schema, quality, and version context.' },
  { value: 'etl', label: 'ETL PDF', description: 'Mappings, transformations, and execution evidence.' },
  { value: 'synthmed-generation', label: 'Synthetic Generation PDF', description: 'Generation settings, versions, and evaluation record.' },
  { value: 'synthmed-comparison', label: 'Comparison PDF', description: 'Recorded source and synthetic distribution evidence.' },
  { value: 'synthmed-privacy', label: 'P3 Privacy PDF', description: 'Persisted privacy screening with explicit limitations.' },
  { value: 'synthmed-utility', label: 'P4 Utility PDF', description: 'Recorded TSTR and TRTR machine-learning utility.' },
  { value: 'synthmed-experiment', label: 'Complete Experiment PDF', description: 'End-to-end experiment lineage and evidence.' },
];

const REPORT_STATUS_TONE: Record<ResearchReportStatus, Tone> = {
  Queued: 'warning',
  Generating: 'info',
  Completed: 'success',
  Failed: 'danger',
};

const SelectField = ({
  label,
  value,
  onChange,
  options,
  placeholder,
  hint,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Option[];
  placeholder: string;
  hint?: string;
}) => (
  <label className="field">
    <span className="field-label">{label}</span>
    <select className="input" value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="">{placeholder}</option>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
    {hint ? <span className="field-hint">{hint}</span> : null}
  </label>
);

const shortId = (value: string) => (value.length > 18 ? `${value.slice(0, 8)}…${value.slice(-4)}` : value);

export const ResearchReports = () => {
  const {
    datasets,
    jobs,
    synthSources,
    synthGenerated,
    synthJobs,
    synthComparisons,
    synthExperiments,
    datasetVersions,
    synthVersions,
    listResearchReports,
    createResearchReport,
    downloadResearchReport,
    listSynthMedExperiments,
    listSynthMedUtilityEvaluations,
    notify,
  } = useDemo();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedType = searchParams.get('type');
  const [reportType, setReportType] = useState<ResearchReportType>(
    REPORT_TYPES.some((item) => item.value === requestedType) ? (requestedType as ResearchReportType) : 'dataset-profile',
  );
  const [reports, setReports] = useState<ResearchReport[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');
  const [datasetSource, setDatasetSource] = useState<'core' | 'synth'>('core');
  const [coreDatasetId, setCoreDatasetId] = useState('');
  const [synthSourceId, setSynthSourceId] = useState('');
  const [datasetVersionId, setDatasetVersionId] = useState('');
  const [etlJobId, setEtlJobId] = useState('');
  const [generationJobId, setGenerationJobId] = useState('');
  const [fallbackGeneratedId, setFallbackGeneratedId] = useState('');
  const [comparisonId, setComparisonId] = useState('');
  const [privacyGeneratedId, setPrivacyGeneratedId] = useState('');
  const [utilityEvaluationId, setUtilityEvaluationId] = useState('');
  const [utilityEvaluations, setUtilityEvaluations] = useState<SynthMedUtilityEvaluation[]>([]);
  const [experimentId, setExperimentId] = useState('');

  const reportLabel = useMemo(
    () => REPORT_TYPES.find((item) => item.value === reportType)?.label ?? 'Research report',
    [reportType],
  );

  const loadReports = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await listResearchReports(reportType);
      setReports(response.items);
      setCounts(response.counts);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Unable to load research reports.');
    } finally {
      setLoading(false);
    }
  }, [listResearchReports, reportType]);

  useEffect(() => {
    void loadReports();
  }, [loadReports]);

  useEffect(() => {
    void listSynthMedExperiments().catch(() => undefined);
    void listSynthMedUtilityEvaluations()
      .then((items) => setUtilityEvaluations(items))
      .catch(() => undefined);
  }, [listSynthMedExperiments, listSynthMedUtilityEvaluations]);

  useEffect(() => {
    if (!coreDatasetId && datasets.length > 0) setCoreDatasetId(datasets[0].id);
  }, [coreDatasetId, datasets]);

  useEffect(() => {
    if (!synthSourceId && synthSources.length > 0) setSynthSourceId(synthSources[0].id);
  }, [synthSourceId, synthSources]);

  useEffect(() => {
    if (!etlJobId && jobs.length > 0) setEtlJobId(jobs[0].id);
  }, [etlJobId, jobs]);

  useEffect(() => {
    if (!generationJobId && synthJobs.length > 0) setGenerationJobId(synthJobs[0].id);
  }, [generationJobId, synthJobs]);

  useEffect(() => {
    if (!fallbackGeneratedId && synthGenerated.length > 0) setFallbackGeneratedId(synthGenerated[0].id);
  }, [fallbackGeneratedId, synthGenerated]);

  useEffect(() => {
    if (!comparisonId && synthComparisons.length > 0) setComparisonId(synthComparisons[0].id);
  }, [comparisonId, synthComparisons]);

  useEffect(() => {
    if (!privacyGeneratedId && synthGenerated.length > 0) setPrivacyGeneratedId(synthGenerated[0].id);
  }, [privacyGeneratedId, synthGenerated]);

  useEffect(() => {
    if (!utilityEvaluationId && utilityEvaluations.length > 0) setUtilityEvaluationId(utilityEvaluations[0].id);
  }, [utilityEvaluationId, utilityEvaluations]);

  useEffect(() => {
    if (!experimentId && synthExperiments.length > 0) setExperimentId(synthExperiments[0].id);
  }, [experimentId, synthExperiments]);

  const datasetOptions: Option[] = [
    ...datasets.map((item) => ({ value: item.id, label: `${item.title} · ${shortId(item.id)}` })),
    ...synthSources.map((item) => ({ value: item.id, label: `${item.datasetName} · ${shortId(item.id)}` })),
  ];

  const versionOptions: Option[] =
    datasetSource === 'core'
      ? (datasetVersions[coreDatasetId]?.versions ?? []).map((item) => ({
          value: item.id,
          label: `${item.versionLabel} · ${shortId(item.id)}`,
        }))
      : (synthVersions[synthSourceId] ?? [])
          .filter((item) => item.datasetKind === 'source')
          .map((item) => ({ value: item.id, label: `${item.versionLabel} · ${shortId(item.id)}` }));

  const buildPayload = (): { payload: ResearchReportGeneratePayload; missing: string } => {
    if (reportType === 'dataset-profile') {
      const datasetId = datasetSource === 'core' ? coreDatasetId : synthSourceId;
      if (!datasetId) return { payload: {}, missing: 'Select a persisted dataset source.' };
      return {
        payload: { datasetId, datasetVersionId: datasetVersionId || null },
        missing: '',
      };
    }
    if (reportType === 'etl') {
      if (!etlJobId) return { payload: {}, missing: 'Select a persisted ETL job.' };
      return { payload: { etlJobId }, missing: '' };
    }
    if (reportType === 'synthmed-generation') {
      if (!generationJobId && !fallbackGeneratedId) {
        return { payload: {}, missing: 'Select a generation job or generated dataset.' };
      }
      return {
        payload: {
          generationJobId: generationJobId || null,
          generatedDatasetId: generationJobId ? null : fallbackGeneratedId,
        },
        missing: '',
      };
    }
    if (reportType === 'synthmed-comparison') {
      if (!comparisonId) return { payload: {}, missing: 'Select a persisted comparison.' };
      return { payload: { comparisonId }, missing: '' };
    }
    if (reportType === 'synthmed-privacy') {
      if (!privacyGeneratedId) return { payload: {}, missing: 'Select a persisted generated dataset.' };
      return { payload: { generatedDatasetId: privacyGeneratedId }, missing: '' };
    }
    if (reportType === 'synthmed-utility') {
      if (!utilityEvaluationId) return { payload: {}, missing: 'Select a persisted utility evaluation.' };
      return { payload: { utilityEvaluationId }, missing: '' };
    }
    if (!experimentId) return { payload: {}, missing: 'Select a persisted experiment.' };
    return { payload: { experimentId }, missing: '' };
  };

  const handleGenerate = async () => {
    const built = buildPayload();
    if (built.missing) {
      notify('error', 'Source required', built.missing);
      return;
    }
    setGenerating(true);
    try {
      const report = await createResearchReport(reportType, built.payload);
      await loadReports();
      navigate(`/reports/${report.reportId}`);
    } finally {
      setGenerating(false);
    }
  };

  const handleTypeChange = (next: ResearchReportType) => {
    setReportType(next);
    setDatasetVersionId('');
    setSearchParams(next === 'dataset-profile' ? {} : { type: next });
  };

  const renderSourceFields = () => {
    if (reportType === 'dataset-profile') {
      return (
        <>
          <label className="field">
            <span className="field-label">Dataset source</span>
            <select
              className="input"
              value={datasetSource}
              onChange={(event) => {
                setDatasetSource(event.target.value as 'core' | 'synth');
                setDatasetVersionId('');
              }}
            >
              <option value="core">Core datasets</option>
              <option value="synth">SynthMed source datasets</option>
            </select>
          </label>
          <SelectField
            label={datasetSource === 'core' ? 'Core dataset' : 'SynthMed source'}
            value={datasetSource === 'core' ? coreDatasetId : synthSourceId}
            onChange={datasetSource === 'core' ? setCoreDatasetId : setSynthSourceId}
            options={datasetOptions}
            placeholder="Select a persisted dataset"
          />
          <SelectField
            label="Version"
            value={datasetVersionId}
            onChange={setDatasetVersionId}
            options={versionOptions}
            placeholder="Latest persisted version"
            hint="Leave blank to use the current persisted version."
          />
        </>
      );
    }
    if (reportType === 'etl') {
      return (
        <SelectField
          label="ETL job"
          value={etlJobId}
          onChange={setEtlJobId}
          options={jobs.map((item) => ({ value: item.id, label: `${item.datasetTitle} · ${item.status}` }))}
          placeholder="Select a persisted ETL job"
        />
      );
    }
    if (reportType === 'synthmed-generation') {
      return (
        <>
          <SelectField
            label="Generation job"
            value={generationJobId}
            onChange={setGenerationJobId}
            options={synthJobs.map((item) => ({
              value: item.id,
              label: `${item.selectedModel ?? item.modelName ?? 'Model'} · ${item.status} · ${shortId(item.id)}`,
            }))}
            placeholder="Select a persisted generation job"
          />
          <SelectField
            label="Generated dataset fallback"
            value={fallbackGeneratedId}
            onChange={setFallbackGeneratedId}
            options={synthGenerated.map((item) => ({
              value: item.id,
              label: `${item.datasetName} · ${item.status} · ${shortId(item.id)}`,
            }))}
            placeholder="Select a generated dataset"
            hint="Used only when no generation job is selected."
          />
        </>
      );
    }
    if (reportType === 'synthmed-comparison') {
      return (
        <SelectField
          label="Comparison"
          value={comparisonId}
          onChange={setComparisonId}
          options={synthComparisons.map((item) => ({ value: item.id, label: `${item.name} · ${shortId(item.id)}` }))}
          placeholder="Select a persisted comparison"
        />
      );
    }
    if (reportType === 'synthmed-privacy') {
      return (
        <SelectField
          label="Generated dataset"
          value={privacyGeneratedId}
          onChange={setPrivacyGeneratedId}
          options={synthGenerated.map((item) => ({
            value: item.id,
            label: `${item.datasetName} · ${item.status} · ${shortId(item.id)}`,
          }))}
          placeholder="Select a persisted generated dataset"
        />
      );
    }
    if (reportType === 'synthmed-utility') {
      return (
        <SelectField
          label="Utility evaluation"
          value={utilityEvaluationId}
          onChange={setUtilityEvaluationId}
          options={utilityEvaluations.map((item) => ({
            value: item.id,
            label: `${item.evaluationName} · ${item.status} · ${shortId(item.id)}`,
          }))}
          placeholder="Select a persisted utility evaluation"
        />
      );
    }
    return (
      <SelectField
        label="Experiment"
        value={experimentId}
        onChange={setExperimentId}
        options={synthExperiments.map((item) => ({
          value: item.id,
          label: `${item.name} · ${item.status} · ${shortId(item.id)}`,
        }))}
        placeholder="Select a persisted experiment"
      />
    );
  };

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Reporting"
        title="Research Reports"
        description="Generate immutable research PDFs from persisted MedDataHub and SynthMed records. Every source selection below comes from records already stored in the workspace."
        actions={
          <Button variant="secondary" icon={<RefreshCw size={15} />} onClick={() => void loadReports()} disabled={loading}>
            Refresh history
          </Button>
        }
      />

      <Alert tone="info" title="Evidence-only reports">
        Reports reproduce persisted data and record version, experiment, and checksum references. Identifier-like columns are
        redacted, categorical values are withheld, and unavailable methods are marked NOT AVAILABLE or NOT EVALUATED.
      </Alert>

      <div className="grid-2 grid-2-wide">
        <Card>
          <CardHeader title="Generate report" subtitle={reportLabel} />
          <div className="card-body">
            <div className="form-grid">
              <label className="field span-2">
                <span className="field-label">Report type</span>
                <select
                  className="input"
                  value={reportType}
                  onChange={(event) => handleTypeChange(event.target.value as ResearchReportType)}
                >
                  {REPORT_TYPES.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
                <span className="field-hint">
                  {REPORT_TYPES.find((item) => item.value === reportType)?.description}
                </span>
              </label>
              {renderSourceFields()}
            </div>
            <div className="page-actions">
              <Button icon={<FileText size={15} />} onClick={() => void handleGenerate()} disabled={generating}>
                {generating ? 'Generating…' : `Generate ${reportLabel}`}
              </Button>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader title="Report history" subtitle={`${reports.length} report${reports.length === 1 ? '' : 's'} in this view`} />
          <div className="card-body compact-details">
            <div className="detail-list">
              {REPORT_TYPES.map((item) => (
                <div className="info-row" key={item.value}>
                  <span className="info-label">{item.label}</span>
                  <span className="info-value mono">{counts[item.value] ?? 0}</span>
                </div>
              ))}
            </div>
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader title="Generated PDFs" subtitle="Open a report record or download the immutable PDF." />
        {error ? (
          <div className="card-body">
            <Alert tone="danger" title="Report history unavailable">
              {error}
            </Alert>
          </div>
        ) : loading ? (
          <div className="card-body">
            <LoadingState label="Loading research reports…" />
          </div>
        ) : reports.length === 0 ? (
          <EmptyState
            title="No reports in this view"
            description="Generate a report from persisted records above, or choose a different report type."
          />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Report</th>
                  <th>Status</th>
                  <th>Template</th>
                  <th>Checksum</th>
                  <th>Size</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {reports.map((report) => (
                  <tr key={report.id}>
                    <td>
                      <Link className="table-title" to={`/reports/${report.reportId}`}>
                        {report.title}
                      </Link>
                      <span className="table-sub mono">{report.reportId}</span>
                      {report.error ? <span className="table-sub">{report.error}</span> : null}
                    </td>
                    <td>
                      <Badge tone={REPORT_STATUS_TONE[report.status]}>{report.status}</Badge>
                    </td>
                    <td className="mono">v{report.templateVersion}</td>
                    <td className="mono">{report.fileChecksum ? shortId(report.fileChecksum) : '—'}</td>
                    <td className="num">{report.fileSize ? formatBytes(report.fileSize) : '—'}</td>
                    <td>{report.createdAt ? formatDateTime(report.createdAt) : '—'}</td>
                    <td>
                      <div className="table-actions">
                        <Link className="btn btn-secondary btn-sm" to={`/reports/${report.reportId}`}>
                          Details
                        </Link>
                        <Button
                          variant="ghost"
                          size="sm"
                          icon={<Download size={14} />}
                          disabled={report.status !== 'Completed'}
                          onClick={() => void downloadResearchReport(report.reportId)}
                        >
                          PDF
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card>
        <CardHeader title="Research safeguards" subtitle="Applied by the reporting backend to every generated PDF." />
        <div className="card-body grid-2">
          <div className="detail-list">
            <SectionTitle>Data protection</SectionTitle>
            <div className="info-row">
              <span className="info-label">Patient identifiers</span>
              <span className="info-value">Redacted or omitted from tables and charts</span>
            </div>
            <div className="info-row">
              <span className="info-label">Raw patient rows</span>
              <span className="info-value">Never included</span>
            </div>
            <div className="info-row">
              <span className="info-label">Missing evidence</span>
              <span className="info-value">NOT AVAILABLE / NOT EVALUATED</span>
            </div>
          </div>
          <div className="detail-list">
            <SectionTitle>Integrity</SectionTitle>
            <div className="info-row">
              <span className="info-label">Version references</span>
              <span className="info-value">Persisted version identifiers in report metadata</span>
            </div>
            <div className="info-row">
              <span className="info-label">Checksum</span>
              <span className="info-value">SHA-256 verified before download</span>
            </div>
            <div className="info-row">
              <span className="info-label">History</span>
              <span className="info-value">New immutable record per generation attempt</span>
            </div>
          </div>
        </div>
      </Card>

      <div className="inline-actions">
        <Link className="btn btn-secondary btn-md" to="/synthmed/experiments">
          <ShieldCheck size={15} /> View experiments
        </Link>
      </div>
    </div>
  );
};
