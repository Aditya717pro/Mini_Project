import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  ArrowRight,
  FileCheck2,
  FileJson,
  FileSpreadsheet,
  FileText,
  Info,
  Loader2,
  Lock,
  LogOut,
  ShieldCheck,
  UploadCloud,
  X,
} from 'lucide-react';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  DemoBadge,
  DemoNotice,
  Field,
  InfoRow,
  PageHeader,
  ProgressBar,
  SectionTitle,
} from '../components/ui';
import { api } from '../lib/api';
import { useDemo, type UploadInput } from '../store/DemoStore';
import { domains } from '../data/mockData';
import { extractFile, MAX_FILE_BYTES, UploadValidationError } from '../lib/extract';
import { formatBytes, formatNumber } from '../lib/format';
import type {
  AccessLevel,
  Domain,
  EtlJob,
  ExtractPreview,
  FileFormat,
  MappingDecisionInput,
  SynthMedGeneratedDatasetDetail,
} from '../types';

const ACCESS_OPTIONS: { value: AccessLevel; title: string; description: string }[] = [
  {
    value: 'Open',
    title: 'Open',
    description: 'Metadata and file available to all authenticated researchers after governance approval.',
  },
  {
    value: 'Controlled',
    title: 'Controlled',
    description: 'Metadata is public; record-level access requires an approved data-use request.',
  },
  {
    value: 'Restricted',
    title: 'Restricted',
    description: 'Metadata summary only. Access requires sponsor and ethics approval.',
  },
];

const TASK_OPTIONS = [
  'Preterm birth risk modelling',
  'Growth trajectory modelling',
  'Readmission prediction',
  'Mental health screening',
  'Vaccination coverage analysis',
  'Anaemia risk prediction',
  'Phenotype clustering',
  'Care utilisation analysis',
];

type AutoEtlStage =
  | 'idle'
  | 'uploading'
  | 'profiling'
  | 'mapping'
  | 'approving'
  | 'running'
  | 'completed'
  | 'failed';

const AUTO_ETL_STEPS: { key: AutoEtlStage; label: string; description: string }[] = [
  { key: 'uploading', label: 'Extract', description: 'Store the file and create the governed ETL job.' },
  { key: 'profiling', label: 'Profile', description: 'Inspect columns, types, missing values and duplicate rows.' },
  { key: 'mapping', label: 'Transform', description: 'Apply reviewed column decisions to the transformation plan.' },
  { key: 'running', label: 'Load', description: 'Stage the processed output and complete the real ETL run.' },
];

const AUTO_ETL_PROGRESS: Record<AutoEtlStage, number> = {
  idle: 0,
  uploading: 12,
  profiling: 38,
  mapping: 58,
  approving: 76,
  running: 92,
  completed: 100,
  failed: 100,
};

interface FormState {
  title: string;
  description: string;
  domain: Domain;
  access: AccessLevel;
  tags: string;
  ageRange: string;
  geography: string;
  studyDesign: string;
  license: string;
  ethicsApproved: boolean;
  dataDictionaryAvailable: boolean;
  intendedTasks: string[];
  labelColumn: string;
}

const emptyForm: FormState = {
  title: '',
  description: '',
  domain: "Women's health",
  access: 'Controlled',
  tags: '',
  ageRange: '',
  geography: '',
  studyDesign: '',
  license: 'CC BY-NC 4.0',
  ethicsApproved: false,
  dataDictionaryAvailable: false,
  intendedTasks: [],
  labelColumn: '',
};

const formatIcon = (format: FileFormat) => {
  if (format === 'CSV') return <FileText size={22} />;
  if (format === 'JSON') return <FileJson size={22} />;
  return <FileSpreadsheet size={22} />;
};

export const UploadDataset = () => {
  const { uploadDataset, getSynthMedGeneratedDetail, notify, logout, user, refresh } = useDemo();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const generatedDatasetId = searchParams.get('generatedId') || '';
  const inputRef = useRef<HTMLInputElement>(null);
  const [generatedDetail, setGeneratedDetail] = useState<SynthMedGeneratedDatasetDetail | null>(null);

  const [file, setFile] = useState<File | null>(null);
  const [format, setFormat] = useState<FileFormat | null>(null);
  const [checksum, setChecksum] = useState('');
  const [preview, setPreview] = useState<ExtractPreview | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [extractError, setExtractError] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [generatedError, setGeneratedError] = useState('');
  const [autoEtlStage, setAutoEtlStage] = useState<AutoEtlStage>('idle');
  const [autoEtlJob, setAutoEtlJob] = useState<EtlJob | null>(null);
  const [autoEtlError, setAutoEtlError] = useState('');

  useEffect(() => {
    if (!generatedDatasetId) return;
    let active = true;
    setGeneratedError('');
    void getSynthMedGeneratedDetail(generatedDatasetId)
      .then((detail) => {
        if (!active) return;
        setGeneratedDetail(detail);
        setForm((prev) => ({
          ...prev,
          title: prev.title || detail.datasetName || 'Synthetic dataset',
          description:
            prev.description ||
            `Synthetic cohort generated from ${detail.sourceDatasetName} using ${detail.selectedModel || detail.modelName || 'SynthMed'}.`,
          access: 'Controlled',
          ethicsApproved: true,
          intendedTasks: ['General clinical research'],
        }));
      })
      .catch((error: unknown) => {
        if (active) setGeneratedError(error instanceof Error ? error.message : 'Generated dataset could not be loaded.');
      });
    return () => {
      active = false;
    };
  }, [generatedDatasetId, getSynthMedGeneratedDetail]);

  const handleFile = useCallback(
    async (candidate: File) => {
      setExtractError('');
      setPreview(null);
      setChecksum('');
      setFile(candidate);
      setExtracting(true);
      try {
        const result = await extractFile(candidate);
        setPreview(result.preview);
        setChecksum(result.checksum);
        setFormat(result.format);
        const baseName = candidate.name.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ');
        setForm((prev) => ({
          ...prev,
          title: prev.title || baseName.slice(0, 120),
          labelColumn:
            prev.labelColumn ||
            result.preview.columns.find((column) =>
              /(outcome|label|target|diagnosis|flag|status|score)/i.test(column.name),
            )?.name ||
            '',
        }));
        notify('success', 'File validated locally', `${candidate.name} · ${formatNumber(result.preview.rowCount)} rows profiled in the browser.`);
      } catch (error) {
        const message =
          error instanceof UploadValidationError
            ? error.message
            : 'The file could not be parsed. Check that it is not corrupt or password protected.';
        setExtractError(message);
        setFormat(null);
        notify('error', 'File validation failed', message);
      } finally {
        setExtracting(false);
      }
    },
    [notify],
  );

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragOver(false);
    const dropped = event.dataTransfer.files?.[0];
    if (dropped) void handleFile(dropped);
  };

  const onInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    const selected = event.target.files?.[0];
    if (selected) void handleFile(selected);
    event.target.value = '';
  };

  const clearFile = () => {
    setFile(null);
    setPreview(null);
    setFormat(null);
    setChecksum('');
    setExtractError('');
  };

  const setField = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => {
      const next = { ...prev };
      delete next[key as string];
      return next;
    });
  };

  const toggleTask = (task: string) => {
    setForm((prev) => ({
      ...prev,
      intendedTasks: prev.intendedTasks.includes(task)
        ? prev.intendedTasks.filter((item) => item !== task)
        : [...prev.intendedTasks, task],
    }));
  };

  const validateForm = () => {
    const next: Record<string, string> = {};
    if (!generatedDatasetId && (!file || !preview || !format)) next.file = 'Select and validate a dataset file first.';
    if (form.title.trim().length < 4) next.title = 'Provide a dataset title of at least 4 characters.';
    if (form.description.trim().length < 30) next.description = 'Describe the dataset in at least 30 characters.';
    if (!form.ageRange.trim()) next.ageRange = 'State the age range covered by the dataset.';
    if (!form.geography.trim()) next.geography = 'List at least one recorded geography.';
    if (form.intendedTasks.length === 0) next.intendedTasks = 'Select at least one intended research task.';
    if (!form.ethicsApproved) next.ethicsApproved = 'Confirm the synthetic/ethics declaration before upload.';
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const waitForEtlCompletion = async (jobId: string): Promise<EtlJob> => {
    for (let attempt = 0; attempt < 120; attempt += 1) {
      const job = await api.getJob(jobId);
      setAutoEtlJob(job);
      if (job.status === 'Completed') return job;
      if (['Failed', 'Cancelled', 'Rejected'].includes(job.status)) {
        throw new Error(job.errorMessage || job.rejectionReason || `ETL job ended as ${job.status}.`);
      }
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    throw new Error('The ETL job did not finish in time. Open ETL processing to check its status.');
  };

  const runAutoEtl = async (jobId: string, researchTask: string) => {
    setAutoEtlStage('profiling');
    let job = await api.profileJob(jobId);
    setAutoEtlJob(job);

    setAutoEtlStage('mapping');
    const decisions: MappingDecisionInput[] = job.mappings.map((mapping) => {
      const target = (mapping.proposedTarget || mapping.target || '').trim();
      return {
        source: mapping.source,
        decision: target ? 'Approved' : 'Unmapped',
        target: target || null,
        note: 'Automatic review from the upload form metadata',
      };
    });
    job = await api.recordMappingDecisions(jobId, decisions);
    setAutoEtlJob(job);

    setAutoEtlStage('approving');
    job = await api.approveMappings(jobId, 'Automatic review from the upload form metadata');
    setAutoEtlJob(job);

    setAutoEtlStage('running');
    await api.runJob(jobId, researchTask);
    const completed = await waitForEtlCompletion(jobId);
    setAutoEtlJob(completed);
    setAutoEtlStage('completed');
    await refresh();
    navigate(
      `/?uploaded=1&datasetId=${encodeURIComponent(completed.datasetId)}&jobId=${encodeURIComponent(completed.id)}`,
    );
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!validateForm() || (!generatedDatasetId && (!file || !preview || !format))) {
      notify('error', 'Upload not started', 'Fix the highlighted fields and try again.');
      return;
    }

    const input: UploadInput = {
      file: generatedDatasetId ? undefined : file ?? undefined,
      checksum: generatedDatasetId ? undefined : checksum,
      preview: generatedDatasetId ? undefined : preview ?? undefined,
      format: generatedDatasetId ? undefined : format ?? undefined,
      generatedDatasetId: generatedDatasetId || undefined,
      title: form.title,
      description: form.description,
      domain: form.domain,
      access: form.access,
      tags: form.tags
        .split(',')
        .map((tag) => tag.trim().toLowerCase())
        .filter(Boolean),
      ageRange: form.ageRange,
      geography: form.geography,
      studyDesign: form.studyDesign,
      license: form.license,
      ethicsApproved: form.ethicsApproved,
      dataDictionaryAvailable: form.dataDictionaryAvailable,
      intendedTasks: form.intendedTasks,
      labelColumn: form.labelColumn,
    };

    setSubmitting(true);
    setAutoEtlError('');
    setAutoEtlStage('uploading');
    try {
      const result = await uploadDataset(input);
      setFile(null);
      setPreview(null);
      setFormat(null);
      setChecksum('');
      setErrors({});
      await runAutoEtl(result.jobId, form.intendedTasks[0] || 'General clinical research');
    } catch (error) {
      setAutoEtlStage('failed');
      setAutoEtlError(error instanceof Error ? error.message : 'The upload pipeline could not be completed.');
      setSubmitting(false);
    }
  };

  const labelOptions = useMemo(() => preview?.columns.map((column) => column.name) ?? [], [preview]);

  return (
    <>
      <PageHeader
        eyebrow="Contribute data"
        title="Upload to Repository"
        description="Register a local file or a generated synthetic dataset, then extract, transform, validate and load it through the governed ETL pipeline."
        actions={
          <Link to="/repository">
            <Button variant="secondary">My Repository</Button>
          </Link>
        }
      />

      <DemoNotice text="Local files are parsed in your browser for immediate feedback. Generated datasets are resolved by ID on the server. Both entry points create the same real ETL job." />

      {generatedDatasetId ? (
        <Card data-testid="upload-generated-banner">
          <CardHeader title="Generated dataset selected" subtitle="The stored synthetic file will be resolved by ID on the server" />
          {generatedError ? <Alert tone="danger" title="Generated dataset unavailable">{generatedError}</Alert> : null}
          <div className="review-grid">
            <InfoRow label="Generated dataset ID"><code className="code small">{generatedDatasetId}</code></InfoRow>
            <InfoRow label="Name">{generatedDetail?.datasetName || 'Loading…'}</InfoRow>
            <InfoRow label="Source">{generatedDetail?.sourceDatasetName || '—'}</InfoRow>
            <InfoRow label="Model">{generatedDetail?.selectedModel || generatedDetail?.modelName || '—'}</InfoRow>
            <InfoRow label="Records">{generatedDetail ? formatNumber(generatedDetail.recordCount) : '—'}</InfoRow>
            <InfoRow label="Storage">Server-side generated file</InfoRow>
          </div>
        </Card>
      ) : null}

      {autoEtlStage !== 'idle' ? (
        <Card data-testid="auto-etl-panel">
          <CardHeader
            title={autoEtlStage === 'failed' ? 'Upload pipeline stopped' : 'Processing your upload'}
            subtitle="Extract, transform and load are running against the real ETL service."
          />
          {autoEtlError ? <Alert tone="danger" title="ETL could not finish">{autoEtlError}</Alert> : null}
          <ProgressBar
            value={AUTO_ETL_PROGRESS[autoEtlStage]}
            tone={autoEtlStage === 'failed' ? 'danger' : autoEtlStage === 'completed' ? 'success' : 'info'}
            height={10}
          />
          <div className="auto-etl-steps">
            {AUTO_ETL_STEPS.map((step, index) => {
              const activeIndex = AUTO_ETL_STEPS.findIndex((item) => item.key === autoEtlStage);
              const currentIndex = autoEtlStage === 'approving' ? 2 : activeIndex;
              const state = autoEtlStage === 'failed' && index === Math.max(currentIndex, 0)
                ? 'Failed'
                : index < currentIndex || autoEtlStage === 'completed'
                  ? 'Completed'
                  : index === currentIndex
                    ? 'Running'
                    : 'Queued';
              return (
                <div key={step.key} className={`auto-etl-step ${state.toLowerCase()}`} data-testid={`auto-etl-step-${step.key}`}>
                  <span className="auto-etl-step-index">{index + 1}</span>
                  <div>
                    <strong>{step.label}</strong>
                    <span>{step.description}</span>
                  </div>
                  <Badge tone={state === 'Completed' ? 'success' : state === 'Failed' ? 'danger' : state === 'Running' ? 'info' : 'neutral'}>
                    {state}
                  </Badge>
                </div>
              );
            })}
          </div>
          {autoEtlJob ? (
            <div className="review-grid">
              <InfoRow label="Dataset ID"><code className="code small">{autoEtlJob.datasetId}</code></InfoRow>
              <InfoRow label="ETL job ID"><code className="code small">{autoEtlJob.id}</code></InfoRow>
              <InfoRow label="Backend status">{autoEtlJob.status}</InfoRow>
              <InfoRow label="Rows out">{formatNumber(autoEtlJob.rowsOut)}</InfoRow>
            </div>
          ) : null}
          {autoEtlStage === 'failed' ? (
            <div className="form-actions">
              <Link to="/etl"><Button icon={<ArrowRight size={16} />}>Open ETL processing</Button></Link>
              <Button variant="secondary" onClick={() => setAutoEtlStage('idle')}>Try another upload</Button>
            </div>
          ) : null}
        </Card>
      ) : null}

      {autoEtlStage === 'idle' ? (
      <form onSubmit={submit} className="upload-layout">
        <div className="upload-main">
          {!generatedDatasetId ? (
          <Card>
            <CardHeader title="1 · Select a file" subtitle="CSV, XLSX or JSON · maximum 25 MB" action={<DemoBadge label="Local parse" />} />
            {!file ? (
              <div
                className={`dropzone ${dragOver ? 'dropzone-active' : ''}`}
                onDragOver={(event) => {
                  event.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={onDrop}
                onClick={() => inputRef.current?.click()}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') inputRef.current?.click();
                }}
                role="button"
                tabIndex={0}
                aria-label="Choose a dataset file"
              >
                <div className="dropzone-icon"><UploadCloud size={26} /></div>
                <strong>Drop your dataset here, or browse files</strong>
                <span>CSV · XLSX · JSON — up to {formatBytes(MAX_FILE_BYTES)}</span>
                <span className="dropzone-note">Files are validated for extension, content signature, size and parseability.</span>
              </div>
            ) : (
              <div className="file-card">
                <div className="file-icon">{format ? formatIcon(format) : <FileText size={22} />}</div>
                <div className="file-meta">
                  <strong>{file.name}</strong>
                  <span>
                    {formatBytes(file.size)} · {format ?? 'Detecting format'}
                    {extracting ? ' · Parsing…' : preview ? ` · ${formatNumber(preview.rowCount)} rows · ${preview.columnCount} columns` : ''}
                  </span>
                  {checksum ? <code className="checksum">SHA-256 {checksum}</code> : null}
                </div>
                {extracting ? <Loader2 className="spin" size={18} /> : (
                  <button type="button" className="icon-btn" onClick={clearFile} aria-label="Remove file">
                    <X size={16} />
                  </button>
                )}
              </div>
            )}
            <input
              ref={inputRef}
              type="file"
              accept=".csv,.xlsx,.json"
              onChange={onInputChange}
              hidden
            />
            {errors.file ? <div className="field-error">{errors.file}</div> : null}
            {extractError ? (
              <Alert tone="danger" title="File rejected">
                {extractError}
              </Alert>
            ) : null}

            {preview ? (
              <>
                <div className="profile-summary">
                  <div><span>Rows</span><strong>{formatNumber(preview.rowCount)}</strong></div>
                  <div><span>Columns</span><strong>{preview.columnCount}</strong></div>
                  <div><span>Missing cells</span><strong>{preview.missingPct}%</strong></div>
                  <div><span>Duplicate rows</span><strong>{formatNumber(preview.duplicateRows)}</strong></div>
                  <div><span>Sheet</span><strong>{preview.sheetName}</strong></div>
                </div>
                <SectionTitle>Detected columns</SectionTitle>
                <div className="table-wrap table-scroll">
                  <table className="table table-compact">
                    <thead>
                      <tr>
                        <th>Column</th>
                        <th>Inferred type</th>
                        <th className="num">Missing</th>
                        <th className="num">Unique</th>
                        <th>Sample values</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.columns.map((column) => (
                        <tr key={column.name}>
                          <td><code className="code">{column.name}</code></td>
                          <td><Badge tone={column.inferredType === 'Mixed' ? 'warning' : 'neutral'}>{column.inferredType}</Badge></td>
                          <td className="num">{column.missingPct}%</td>
                          <td className="num">{formatNumber(column.uniqueSample)}</td>
                          <td className="muted small">{column.sampleValues.join(' · ') || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="field-hint">
                  Types are inferred from the first parsed rows and may not reflect clinical definitions. Confirm
                  mappings in the ETL review stage.
                </p>
              </>
            ) : null}
          </Card>
          ) : null}

          <Card>
            <CardHeader title="2 · Describe the dataset" subtitle="Metadata is required for discovery, governance and AI-readiness" />
            <div className="form-grid">
              <Field label="Dataset title" required error={errors.title} htmlFor="title">
                <input
                  id="title"
                  className="input"
                  value={form.title}
                  onChange={(event) => setField('title', event.target.value)}
                  placeholder="e.g. Adolescent Asthma Follow-up Cohort"
                />
              </Field>
              <Field label="Medical domain" required htmlFor="domain">
                <select
                  id="domain"
                  className="input"
                  value={form.domain}
                  onChange={(event) => setField('domain', event.target.value as Domain)}
                >
                  {domains.map((domain) => (
                    <option key={domain} value={domain}>{domain}</option>
                  ))}
                </select>
              </Field>
              <div className="field span-2">
                <Field label="Description" required error={errors.description} htmlFor="description">
                  <textarea
                    id="description"
                    className="input textarea"
                    rows={4}
                    value={form.description}
                    onChange={(event) => setField('description', event.target.value)}
                    placeholder="Describe the population, collection method, variables and any known limitations."
                  />
                </Field>
              </div>
              <Field label="Age range" required error={errors.ageRange} htmlFor="ageRange">
                <input
                  id="ageRange"
                  className="input"
                  value={form.ageRange}
                  onChange={(event) => setField('ageRange', event.target.value)}
                  placeholder="e.g. 0–17 years"
                />
              </Field>
              <Field label="Geography" required error={errors.geography} hint="Comma-separated countries or regions actually recorded." htmlFor="geography">
                <input
                  id="geography"
                  className="input"
                  value={form.geography}
                  onChange={(event) => setField('geography', event.target.value)}
                  placeholder="e.g. Kenya, Tanzania"
                />
              </Field>
              <Field label="Study design" htmlFor="studyDesign">
                <input
                  id="studyDesign"
                  className="input"
                  value={form.studyDesign}
                  onChange={(event) => setField('studyDesign', event.target.value)}
                  placeholder="e.g. Retrospective cohort"
                />
              </Field>
              <Field label="Licence" htmlFor="license">
                <input
                  id="license"
                  className="input"
                  value={form.license}
                  onChange={(event) => setField('license', event.target.value)}
                />
              </Field>
              <Field label="Tags" hint="Comma-separated, used for repository search." htmlFor="tags">
                <input
                  id="tags"
                  className="input"
                  value={form.tags}
                  onChange={(event) => setField('tags', event.target.value)}
                  placeholder="asthma, paediatrics, admissions"
                />
              </Field>
              <Field label="Candidate label column" hint="Used by the readiness assessment. Optional." htmlFor="labelColumn">
                <select
                  id="labelColumn"
                  className="input"
                  value={form.labelColumn}
                  onChange={(event) => setField('labelColumn', event.target.value)}
                >
                  <option value="">No label column</option>
                  {labelOptions.map((column) => (
                    <option key={column} value={column}>{column}</option>
                  ))}
                </select>
              </Field>
            </div>

            <SectionTitle>Access classification</SectionTitle>
            <div className="access-options">
              {ACCESS_OPTIONS.map((option) => (
                <label key={option.value} className={`access-option ${form.access === option.value ? 'selected' : ''}`}>
                  <input
                    type="radio"
                    name="access"
                    value={option.value}
                    checked={form.access === option.value}
                    onChange={() => setField('access', option.value)}
                  />
                  <div>
                    <strong>{option.title === 'Open' ? <>{option.title} <Info size={13} /></> : option.title}</strong>
                    <span>{option.description}</span>
                  </div>
                </label>
              ))}
            </div>
            <Alert tone="warning">
              Uploading does not publish a dataset. Every dataset enters governance review, and file downloads remain
              disabled for pending or rejected datasets.
            </Alert>

            <SectionTitle>Intended AI research tasks</SectionTitle>
            <div className="chip-grid">
              {TASK_OPTIONS.map((task) => (
                <button
                  key={task}
                  type="button"
                  className={`chip ${form.intendedTasks.includes(task) ? 'chip-selected' : ''}`}
                  onClick={() => toggleTask(task)}
                  aria-pressed={form.intendedTasks.includes(task)}
                >
                  {task}
                </button>
              ))}
            </div>
            {errors.intendedTasks ? <div className="field-error">{errors.intendedTasks}</div> : null}

            <div className="checkbox-stack">
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.dataDictionaryAvailable}
                  onChange={(event) => setField('dataDictionaryAvailable', event.target.checked)}
                />
                <span>A data dictionary is available for this dataset.</span>
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.ethicsApproved}
                  onChange={(event) => setField('ethicsApproved', event.target.checked)}
                />
                <span>
                  I confirm this file contains <strong>synthetic data only</strong>, contains no real patient
                  information, and that the metadata I provided is accurate.
                </span>
              </label>
              {errors.ethicsApproved ? <div className="field-error">{errors.ethicsApproved}</div> : null}
            </div>
          </Card>

          <Card>
            <CardHeader title="3 · Review and submit" subtitle="A dataset ID, checksum and ETL job are created on submit" />
            <div className="review-grid">
              <InfoRow label="Source">{generatedDatasetId ? `Generated dataset ${generatedDatasetId}` : file ? file.name : 'No file selected'}</InfoRow>
              <InfoRow label="Format">{generatedDetail?.fileFormat ?? format ?? '—'}</InfoRow>
              <InfoRow label="Rows / columns">{generatedDetail ? `${formatNumber(generatedDetail.recordCount)} / ${generatedDetail.columnCount}` : preview ? `${formatNumber(preview.rowCount)} / ${preview.columnCount}` : '—'}</InfoRow>
              <InfoRow label="Missing cells">{preview ? `${preview.missingPct}%` : 'Server profile on submit'}</InfoRow>
              <InfoRow label="Checksum">{checksum ? <code className="code small">{checksum.slice(0, 24)}…</code> : generatedDetail ? <code className="code small">server-verified</code> : '—'}</InfoRow>
              <InfoRow label="Access">{form.access}</InfoRow>
              <InfoRow label="Domain">{form.domain}</InfoRow>
              <InfoRow label="Label column">{form.labelColumn || 'None'}</InfoRow>
            </div>

            {submitting ? (
              <div className="submit-progress-head">
                <Loader2 className="spin" size={16} />
                <span>Creating the repository record and real ETL job…</span>
              </div>
            ) : null}

            <div className="form-actions">
              <Button type="submit" disabled={extracting || submitting} icon={<UploadCloud size={16} />}>
                {submitting ? 'Submitting…' : 'Upload to Repository'}
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setForm(emptyForm);
                  clearFile();
                  setErrors({});
                }}
              >
                Reset form
              </Button>
            </div>
          </Card>
        </div>

        <aside className="upload-side">
          <Card>
            <CardHeader title="Before you upload" subtitle="Data contribution checklist" />
            <ul className="checklist">
              <li><ShieldCheck size={16} /><span>Use synthetic data only. Never upload identifiable patient records.</span></li>
              <li><FileCheck2 size={16} /><span>First worksheet is used for XLSX; include a clear header row.</span></li>
              <li><Lock size={16} /><span>Choose an access class. Uploading never makes a file public automatically.</span></li>
              <li><Info size={16} /><span>Original files are preserved. Transformations are documented, not silent.</span></li>
            </ul>
          </Card>

          <Card>
            <CardHeader title="Pipeline preview" subtitle="What happens after submission" />
            <ol className="pipeline-steps">
              <li><span>1</span><div><strong>Extract</strong><p>Parse file, infer types, compute row/column and missing-value profiles.</p></div></li>
              <li><span>2</span><div><strong>Transform</strong><p>Suggest column mappings. Uncertain mappings require your approval.</p></div></li>
              <li><span>3</span><div><strong>Load</strong><p>Store a new version, write logs and stage quality reports.</p></div></li>
              <li><span>4</span><div><strong>Governance review</strong><p>An authorised reviewer approves access classification before publication.</p></div></li>
            </ol>
          </Card>

          <Card className="note-card">
            <strong>Real pipeline</strong>
            <p>
              Repository records, checksums, ETL jobs, mapping decisions, processed versions and validation reports are
              created by the FastAPI backend. No upload is published automatically.
            </p>
          </Card>
        </aside>
      </form>
      ) : null}
      {user ? (
        <Button
          type="button"
          variant="ghost"
          icon={<LogOut size={16} />}
          onClick={() => logout()}
          style={{ marginTop: 16 }}
        >
          Sign out
        </Button>
      ) : null}
    </>
  );
};
