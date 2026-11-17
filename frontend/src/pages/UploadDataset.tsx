import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  CheckCircle2,
  FileCheck2,
  FileJson,
  FileSpreadsheet,
  FileText,
  Info,
  Loader2,
  Lock,
  LogOut,
  RotateCcw,
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
import { useDemo, type UploadInput } from '../store/DemoStore';
import { domains } from '../data/mockData';
import { extractFile, MAX_FILE_BYTES, UploadValidationError } from '../lib/extract';
import { formatBytes, formatNumber } from '../lib/format';
import type { AccessLevel, Domain, ExtractPreview, FileFormat } from '../types';

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
  const { uploadDataset, notify, logout, user } = useDemo();
  const inputRef = useRef<HTMLInputElement>(null);
  const submitTimer = useRef<number | null>(null);

  const [file, setFile] = useState<File | null>(null);
  const [format, setFormat] = useState<FileFormat | null>(null);
  const [checksum, setChecksum] = useState('');
  const [preview, setPreview] = useState<ExtractPreview | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [extractError, setExtractError] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitProgress, setSubmitProgress] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [createdId, setCreatedId] = useState<string | null>(null);

  useEffect(() => {
    return () => {
      if (submitTimer.current) window.clearInterval(submitTimer.current);
    };
  }, []);

  const handleFile = useCallback(
    async (candidate: File) => {
      setExtractError('');
      setPreview(null);
      setChecksum('');
      setCreatedId(null);
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
    setCreatedId(null);
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
    if (!file || !preview || !format) next.file = 'Select and validate a dataset file first.';
    if (form.title.trim().length < 4) next.title = 'Provide a dataset title of at least 4 characters.';
    if (form.description.trim().length < 30) next.description = 'Describe the dataset in at least 30 characters.';
    if (!form.ageRange.trim()) next.ageRange = 'State the age range covered by the dataset.';
    if (!form.geography.trim()) next.geography = 'List at least one recorded geography.';
    if (form.intendedTasks.length === 0) next.intendedTasks = 'Select at least one intended research task.';
    if (!form.ethicsApproved) next.ethicsApproved = 'Confirm the synthetic/ethics declaration before upload.';
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!validateForm() || !file || !preview || !format) {
      notify('error', 'Upload not started', 'Fix the highlighted fields and try again.');
      return;
    }

    setSubmitting(true);
    setSubmitProgress(6);
    let progress = 6;
    submitTimer.current = window.setInterval(() => {
      progress = Math.min(100, progress + 14);
      setSubmitProgress(progress);
      if (progress >= 100) {
        if (submitTimer.current) window.clearInterval(submitTimer.current);
        const input: UploadInput = {
          file,
          checksum,
          preview,
          format,
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
        void (async () => {
          try {
            const id = await uploadDataset(input);
            setCreatedId(id);
            setSubmitting(false);
            setFile(null);
            setPreview(null);
            setFormat(null);
            setChecksum('');
            setForm(emptyForm);
            setErrors({});
            notify(
              'success',
              'Dataset uploaded and queued for ETL',
              'Review the suggested mappings in the ETL workspace before staging the processed output.',
            );
          } catch {
            setSubmitting(false);
            setSubmitProgress(0);
          }
        })();
      }
    }, 260);
  };

  const labelOptions = useMemo(() => preview?.columns.map((column) => column.name) ?? [], [preview]);

  return (
    <>
      <PageHeader
        eyebrow="Contribute data"
        title="Upload dataset"
        description="Validate a CSV, XLSX or JSON file locally, describe the dataset and queue it for the ETL pipeline."
        actions={
          <Link to="/repository">
            <Button variant="secondary">Dataset repository</Button>
          </Link>
        }
      />

      <DemoNotice text="Files are parsed in your browser for immediate feedback, then uploaded to the FastAPI backend for secure storage, checksum persistence and server-side ETL." />

      {createdId ? (
        <Card className="success-panel">
          <div className="success-icon"><CheckCircle2 size={26} /></div>
          <div>
            <h2>Dataset accepted for processing</h2>
            <p>
              <strong>{createdId}</strong> was stored by the backend and its ETL job is queued. Review the suggested
              mappings, run the pipeline, then submit the processed output for governance review.
            </p>
            <div className="success-actions">
              <Link to={`/datasets/${createdId}`}>
                <Button icon={<ArrowRight size={16} />}>View dataset record</Button>
              </Link>
              <Link to="/etl">
                <Button variant="secondary">Open ETL processing</Button>
              </Link>
              <Button
                variant="ghost"
                icon={<RotateCcw size={15} />}
                onClick={() => setCreatedId(null)}
              >
                Upload another
              </Button>
            </div>
          </div>
        </Card>
      ) : null}

      <form onSubmit={submit} className="upload-layout">
        <div className="upload-main">
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
              <InfoRow label="File">{file ? file.name : 'No file selected'}</InfoRow>
              <InfoRow label="Format">{format ?? '—'}</InfoRow>
              <InfoRow label="Rows / columns">{preview ? `${formatNumber(preview.rowCount)} / ${preview.columnCount}` : '—'}</InfoRow>
              <InfoRow label="Missing cells">{preview ? `${preview.missingPct}%` : '—'}</InfoRow>
              <InfoRow label="Checksum">{checksum ? <code className="code small">{checksum.slice(0, 24)}…</code> : '—'}</InfoRow>
              <InfoRow label="Access">{form.access}</InfoRow>
              <InfoRow label="Domain">{form.domain}</InfoRow>
              <InfoRow label="Label column">{form.labelColumn || 'None'}</InfoRow>
            </div>

            {submitting ? (
              <div className="submit-progress">
                <div className="submit-progress-head">
                  <Loader2 className="spin" size={16} />
                  <span>Validating metadata and creating ETL job… {submitProgress}%</span>
                </div>
                <ProgressBar value={submitProgress} />
              </div>
            ) : null}

            <div className="form-actions">
              <Button type="submit" disabled={extracting || submitting} icon={<UploadCloud size={16} />}>
                {submitting ? 'Submitting…' : 'Submit dataset'}
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
            <strong>Mock vs real</strong>
            <p>
              File validation and profiling are <strong>real</strong> and run in your browser. ETL progress, quality and
              readiness scores after submission are <strong>demonstration rules</strong> until the FastAPI ETL engine
              is connected.
            </p>
          </Card>
        </aside>
      </form>
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
