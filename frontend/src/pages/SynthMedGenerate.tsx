import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, CheckCircle2, Cpu, ShieldCheck, Wand2 } from 'lucide-react';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  Field,
  InfoRow,
  LoadingState,
  PageHeader,
} from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { formatDateTime, formatNumber } from '../lib/format';
import type {
  SynthMedColumnAnalysis,
  SynthMedGenerationAnalysis,
  SynthMedGenerationJob,
  SynthMedGenerationStatus,
} from '../types';

type ColumnRole = 'Auto' | 'Numerical' | 'Categorical' | 'Identifier';

const TERMINAL_STATUSES: SynthMedGenerationStatus[] = ['Completed', 'Failed'];
const JOB_STAGES: SynthMedGenerationStatus[] = [
  'Queued',
  'Preprocessing',
  'Training',
  'Generating',
  'Validating',
  'Completed',
];

const jobTone = (
  status: SynthMedGenerationStatus,
): 'success' | 'info' | 'warning' | 'danger' | 'neutral' | 'purple' => {
  if (status === 'Completed') return 'success';
  if (status === 'Failed') return 'danger';
  if (status === 'Training' || status === 'Generating') return 'purple';
  if (status === 'Queued') return 'neutral';
  return 'info';
};

const kindLabel = (column: SynthMedColumnAnalysis): string => {
  if (column.constant) return 'Constant';
  if (column.potentialIdentifier) return 'Identifier';
  return column.kind.charAt(0).toUpperCase() + column.kind.slice(1);
};

const defaultRole = (column: SynthMedColumnAnalysis): ColumnRole => {
  if (column.potentialIdentifier) return 'Identifier';
  if (column.kind === 'numerical') return 'Numerical';
  if (column.kind === 'categorical') return 'Categorical';
  return 'Auto';
};

const errorMessage = (error: unknown) => (error instanceof Error ? error.message : 'Unexpected API error');

export const SynthMedGenerate = () => {
  const {
    synthSources,
    analyseSynthMedGeneration,
    startSynthMedGeneration,
    getSynthMedGenerationJob,
    refreshSynthMed,
  } = useDemo();

  const [sourceId, setSourceId] = useState('');
  const [analysis, setAnalysis] = useState<SynthMedGenerationAnalysis | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState('');
  const [selectedColumns, setSelectedColumns] = useState<string[]>([]);
  const [roles, setRoles] = useState<Record<string, ColumnRole>>({});
  const [datasetName, setDatasetName] = useState('');
  const [seed, setSeed] = useState('');
  const [epochs, setEpochs] = useState('20');
  const [batchSize, setBatchSize] = useState('100');
  const [recordCount, setRecordCount] = useState('1000');
  const [preserveMissingness, setPreserveMissingness] = useState(true);
  const [formError, setFormError] = useState('');
  const [starting, setStarting] = useState(false);
  const [job, setJob] = useState<SynthMedGenerationJob | null>(null);

  useEffect(() => {
    if (!sourceId && synthSources.length > 0) setSourceId(synthSources[0].id);
  }, [sourceId, synthSources]);

  useEffect(() => {
    let active = true;
    setJob(null);
    setFormError('');
    if (!sourceId) {
      setAnalysis(null);
      return;
    }
    setAnalysisLoading(true);
    setAnalysisError('');
    void analyseSynthMedGeneration(sourceId)
      .then((result) => {
        if (!active) return;
        setAnalysis(result);
        setDatasetName(`${result.datasetName} synthetic cohort`);
        setSelectedColumns(
          result.columns
            .filter((column) => !column.potentialIdentifier && !column.constant)
            .map((column) => column.name),
        );
        setRoles(Object.fromEntries(result.columns.map((column) => [column.name, defaultRole(column)])));
        setRecordCount(String(Math.min(1000, Math.max(1, result.totalRecords * 2))));
      })
      .catch((error: unknown) => {
        if (active) setAnalysisError(errorMessage(error));
      })
      .finally(() => {
        if (active) setAnalysisLoading(false);
      });
    return () => {
      active = false;
    };
  }, [sourceId, analyseSynthMedGeneration]);

  useEffect(() => {
    if (!job || TERMINAL_STATUSES.includes(job.status)) return;
    let cancelled = false;
    const timer = window.setInterval(() => {
      void getSynthMedGenerationJob(job.id)
        .then((updated) => {
          if (!cancelled) setJob(updated);
        })
        .catch((error: unknown) => {
          if (!cancelled) setFormError(errorMessage(error));
        });
    }, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [job?.id, job?.status, getSynthMedGenerationJob]);

  useEffect(() => {
    if (job?.status === 'Completed') void refreshSynthMed().catch(() => undefined);
  }, [job?.status, job?.id, refreshSynthMed]);

  const identifierColumns = useMemo(
    () =>
      analysis?.columns
        .filter((column) => column.potentialIdentifier || roles[column.name] === 'Identifier')
        .map((column) => column.name) ?? [],
    [analysis, roles],
  );

  const includedColumns = useMemo(
    () => selectedColumns.filter((column) => !identifierColumns.includes(column)),
    [selectedColumns, identifierColumns],
  );

  const categoricalColumns = useMemo(
    () => includedColumns.filter((column) => roles[column] === 'Categorical'),
    [includedColumns, roles],
  );

  const numericalColumns = useMemo(
    () => includedColumns.filter((column) => roles[column] === 'Numerical'),
    [includedColumns, roles],
  );

  const toggleColumn = (column: SynthMedColumnAnalysis) => {
    if (column.potentialIdentifier) return;
    setSelectedColumns((previous) =>
      previous.includes(column.name) ? previous.filter((name) => name !== column.name) : [...previous, column.name],
    );
  };

  const changeRole = (columnName: string, role: ColumnRole) => {
    setRoles((previous) => ({ ...previous, [columnName]: role }));
    setSelectedColumns((previous) =>
      role === 'Identifier'
        ? previous.filter((name) => name !== columnName)
        : previous.includes(columnName)
          ? previous
          : [...previous, columnName],
    );
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!analysis) return;
    const epochsValue = Number(epochs);
    const batchValue = Number(batchSize);
    const recordValue = Number(recordCount);
    const seedValue = seed.trim() ? Number(seed) : null;

    if (includedColumns.length === 0) {
      setFormError('Select at least one non-identifier column to train the model.');
      return;
    }
    if (!Number.isInteger(epochsValue) || epochsValue < 1 || epochsValue > 10000) {
      setFormError('Epochs must be a whole number between 1 and 10000.');
      return;
    }
    if (!Number.isInteger(batchValue) || batchValue < 20 || batchValue > 10000 || batchValue % 10 !== 0) {
      setFormError('Batch size must be a multiple of 10 between 20 and 10000.');
      return;
    }
    if (!Number.isInteger(recordValue) || recordValue < 1 || recordValue > 1000000) {
      setFormError('Record count must be a whole number between 1 and 1000000.');
      return;
    }
    if (seedValue !== null && !Number.isInteger(seedValue)) {
      setFormError('Seed must be a whole number or blank for a random seed.');
      return;
    }

    setFormError('');
    setStarting(true);
    try {
      const created = await startSynthMedGeneration({
        sourceDatasetId: analysis.sourceDatasetId,
        datasetName: datasetName.trim() || `${analysis.datasetName} synthetic`,
        selectedColumns: includedColumns,
        categoricalColumns,
        numericalColumns,
        identifierColumns,
        primaryKey: identifierColumns[0] ?? null,
        seed: seedValue,
        epochs: epochsValue,
        batchSize: batchValue,
        recordCount: recordValue,
        preserveMissingness,
      });
      setJob(created);
      await refreshSynthMed().catch(() => undefined);
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setStarting(false);
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="Synthetic data"
        title="Generate Synthetic Data"
        description="Train a real SDV CTGANSynthesizer on an authorised source dataset, then review quality and privacy reports before release."
        actions={
          <Link to="/synthmed/upload">
            <Button variant="secondary" icon={<Wand2 size={16} />}>
              Upload source dataset
            </Button>
          </Link>
        }
      />

      <Alert tone="info" title="Real CTGAN training on CPU">
        Generation uses SDV CTGANSynthesizer with reproducible seeds and CPU-only execution. Training happens as an
        authenticated background job; the page polls genuine job states instead of showing simulated progress.
      </Alert>

      <form className="upload-layout" onSubmit={(event) => void submit(event)}>
        <div className="upload-main">
          <Card>
            <CardHeader title="1. Select and analyse a source" subtitle="Schema detection runs on the server before training." />
            <Field
              label="Source dataset"
              htmlFor="synthmed-generation-source"
              required
              hint="Only source datasets uploaded by your account are listed."
            >
              <select
                id="synthmed-generation-source"
                className="input"
                value={sourceId}
                onChange={(event) => setSourceId(event.target.value)}
              >
                <option value="">Select a source dataset…</option>
                {synthSources.map((source) => (
                  <option key={source.id} value={source.id}>
                    {source.datasetName} · {source.originalFilename}
                  </option>
                ))}
              </select>
            </Field>

            {analysisLoading ? <LoadingState label="Analysing source schema…" /> : null}
            {analysisError ? <Alert tone="danger" title="Analysis failed">{analysisError}</Alert> : null}

            {analysis && !analysisLoading ? (
              <>
                <div className="profile-summary">
                  <div><span>Records</span><strong>{formatNumber(analysis.totalRecords)}</strong></div>
                  <div><span>Columns</span><strong>{formatNumber(analysis.totalColumns)}</strong></div>
                  <div><span>Duplicates</span><strong>{formatNumber(analysis.duplicateRecords)}</strong></div>
                  <div><span>Identifiers</span><strong>{analysis.potentialIdentifierColumns.length}</strong></div>
                  <div><span>Ready</span><strong>{analysis.generationReady ? 'Yes' : 'No'}</strong></div>
                </div>
                <p className="muted small">{analysis.guidance}</p>
                {!analysis.generationReady ? (
                  <Alert tone="warning" title="Review source suitability">
                    This source has no modelable columns after identifier and constant-column exclusion.
                  </Alert>
                ) : null}

                <div className="column-grid">
                  {analysis.columns.map((column) => {
                    const excluded = column.potentialIdentifier || column.constant;
                    const checked = selectedColumns.includes(column.name) && !excluded;
                    return (
                      <div className={`column-option ${checked ? 'selected' : ''}`} key={column.name}>
                        <div className="column-option-head">
                          <label>
                            <input
                              type="checkbox"
                              checked={checked}
                              disabled={excluded}
                              onChange={() => toggleColumn(column)}
                            />
                            <strong>{column.name}</strong>
                          </label>
                          <Badge tone={column.potentialIdentifier ? 'warning' : column.constant ? 'neutral' : 'info'}>
                            {kindLabel(column)}
                          </Badge>
                        </div>
                        <div className="column-option-meta">
                          <span>{formatNumber(column.uniqueCount)} unique</span>
                          <span>{column.missingPercentage}% missing</span>
                        </div>
                        {column.quasiIdentifier && !column.potentialIdentifier ? (
                          <span className="column-note">Possible quasi-identifier</span>
                        ) : null}
                        {column.potentialIdentifier ? (
                          <span className="column-note">Excluded and never reproduced</span>
                        ) : null}
                        {!excluded ? (
                          <select
                            className="input input-sm"
                            aria-label={`Role for ${column.name}`}
                            value={roles[column.name] ?? 'Auto'}
                            onChange={(event) => changeRole(column.name, event.target.value as ColumnRole)}
                          >
                            <option value="Auto">Auto</option>
                            <option value="Numerical">Numerical</option>
                            <option value="Categorical">Categorical</option>
                            <option value="Identifier">Treat as identifier</option>
                          </select>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              </>
            ) : null}
          </Card>

          <Card>
            <CardHeader title="2. Configure CTGAN training" subtitle="Conservative defaults can be adjusted for your cohort." />
            <div className="review-grid">
              <Field label="Generated dataset name" htmlFor="synthmed-generation-name" required>
                <input
                  id="synthmed-generation-name"
                  className="input"
                  value={datasetName}
                  onChange={(event) => setDatasetName(event.target.value)}
                  placeholder="Fictional synthetic cohort"
                />
              </Field>
              <Field
                label="Seed"
                htmlFor="synthmed-generation-seed"
                hint="Blank uses a random seed; the chosen value is recorded with the job."
              >
                <input
                  id="synthmed-generation-seed"
                  className="input"
                  type="number"
                  value={seed}
                  onChange={(event) => setSeed(event.target.value)}
                  placeholder="e.g. 42"
                />
              </Field>
              <Field
                label="Epochs"
                htmlFor="synthmed-generation-epochs"
                hint="More epochs usually improve fidelity but take longer."
              >
                <input
                  id="synthmed-generation-epochs"
                  className="input"
                  type="number"
                  min={1}
                  max={10000}
                  value={epochs}
                  onChange={(event) => setEpochs(event.target.value)}
                />
              </Field>
              <Field
                label="Batch size"
                htmlFor="synthmed-generation-batch"
                hint="CTGAN requires a multiple of 10 between 20 and 10000."
              >
                <input
                  id="synthmed-generation-batch"
                  className="input"
                  type="number"
                  min={20}
                  max={10000}
                  step={10}
                  value={batchSize}
                  onChange={(event) => setBatchSize(event.target.value)}
                />
              </Field>
              <Field label="Synthetic records" htmlFor="synthmed-generation-records" required>
                <input
                  id="synthmed-generation-records"
                  className="input"
                  type="number"
                  min={1}
                  max={1000000}
                  value={recordCount}
                  onChange={(event) => setRecordCount(event.target.value)}
                />
              </Field>
              <div className="field">
                <span className="field-label">Missing values</span>
                <label className="check-row">
                  <input
                    type="checkbox"
                    checked={preserveMissingness}
                    onChange={(event) => setPreserveMissingness(event.target.checked)}
                  />
                  Preserve missingness for SDV handling
                </label>
                <div className="field-hint">Missing values are never replaced with zero or a medical default.</div>
              </div>
            </div>
            {formError ? <Alert tone="danger" title="Generation not started">{formError}</Alert> : null}
            <div className="button-row">
              <Button
                type="submit"
                disabled={!analysis || !analysis.generationReady || starting}
                icon={<Wand2 size={16} />}
              >
                {starting ? 'Starting job…' : 'Start CTGAN generation'}
              </Button>
              <Link to="/synthmed/generated">
                <Button type="button" variant="secondary">View generated datasets</Button>
              </Link>
            </div>
          </Card>

          {job ? (
            <Card>
              <CardHeader
                title="3. Generation job"
                subtitle={`${job.modelName} · ${formatNumber(job.requestedRecordCount)} requested records`}
                action={<Badge tone={jobTone(job.status)}>{job.status}</Badge>}
              />
              <div className="pipeline-steps compact-steps">
                {JOB_STAGES.map((stage) => {
                  const currentIndex = JOB_STAGES.indexOf(job.status === 'Failed' ? 'Completed' : job.status);
                  const stageIndex = JOB_STAGES.indexOf(stage);
                  const done = job.status === 'Completed' || stageIndex < currentIndex;
                  const active = job.status !== 'Completed' && stageIndex === currentIndex;
                  return (
                    <li key={stage}>
                      <span>{done ? <CheckCircle2 size={14} /> : stageIndex + 1}</span>
                      <div>
                        <strong>{stage}</strong>
                        <p>{active ? 'Currently running on the server' : done ? 'Finished' : 'Waiting'}</p>
                      </div>
                    </li>
                  );
                })}
              </div>
              <div className="info-list">
                <InfoRow label="Job ID"><code className="code small">{job.id}</code></InfoRow>
                <InfoRow label="Requested records">{formatNumber(job.requestedRecordCount)}</InfoRow>
                <InfoRow label="Generated records">{formatNumber(job.generatedRecordCount)}</InfoRow>
                <InfoRow label="Epochs / batch size">{job.epochs} / {job.batchSize}</InfoRow>
                <InfoRow label="Seed">{job.seed ?? 'Random'}</InfoRow>
                <InfoRow label="Training duration">
                  {job.trainingDurationSeconds == null ? '—' : `${job.trainingDurationSeconds.toFixed(1)} s`}
                </InfoRow>
                {job.startedAt ? <InfoRow label="Started">{formatDateTime(job.startedAt)}</InfoRow> : null}
                {job.completedAt ? <InfoRow label="Completed">{formatDateTime(job.completedAt)}</InfoRow> : null}
              </div>
              {job.status === 'Failed' ? (
                <Alert tone="danger" title="Generation failed">
                  {job.error || 'The job failed without a detailed message.'}
                </Alert>
              ) : null}
              {job.status === 'Completed' && job.generatedDatasetId ? (
                <Link to={`/synthmed/generated/${job.generatedDatasetId}`}>
                  <Button icon={<ArrowRight size={16} />}>Open generated dataset</Button>
                </Link>
              ) : null}
            </Card>
          ) : null}
        </div>

        <aside className="upload-side">
          <Card>
            <CardHeader title="Generation controls" subtitle="Server-enforced" />
            <ul className="checklist">
              <li><Cpu size={14} /> CPU-only CTGAN training; no GPU required.</li>
              <li><ShieldCheck size={14} /> Identifier columns are excluded from modelling.</li>
              <li>Missing values are preserved, not zero-filled.</li>
              <li>Reports are generated before the dataset is released.</li>
            </ul>
          </Card>
          <Card>
            <CardHeader title="Selected columns" subtitle={`${includedColumns.length} of ${analysis?.totalColumns ?? 0}`} />
            {includedColumns.length === 0 ? (
              <p className="muted small">No columns selected.</p>
            ) : (
              <div className="chip-grid">
                {includedColumns.map((column) => (
                  <span className="chip" key={column}>{column}</span>
                ))}
              </div>
            )}
          </Card>
          <Card>
            <CardHeader title="Limits" subtitle="No clinical claims" />
            <p className="muted small">
              Synthetic data is statistically modelled, not clinically validated. Exact source files remain untouched in
              separate storage.
            </p>
          </Card>
        </aside>
      </form>
    </>
  );
};
