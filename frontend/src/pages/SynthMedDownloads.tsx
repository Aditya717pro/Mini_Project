import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  CheckCircle2,
  Download,
  Eye,
  FlaskConical,
  ShieldCheck,
  UploadCloud,
  Wand2,
} from 'lucide-react';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  LoadingState,
  Modal,
  PageHeader,
  ProgressBar,
} from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { formatBytes, formatDateTime, formatNumber } from '../lib/format';
import type {
  SynthMedGenerationAnalysis,
  SynthMedGenerationJob,
  SynthMedGenerationStartPayload,
  SynthMedGenerationStatus,
} from '../types';

const TERMINAL_STATUSES: SynthMedGenerationStatus[] = ['Completed', 'Failed'];

const errorMessage = (error: unknown) => (error instanceof Error ? error.message : 'Unexpected API error');

const statusProgress: Record<string, number> = {
  Queued: 10,
  Extracting: 25,
  Analysing: 40,
  Training: 65,
  Generating: 80,
  Validating: 90,
  Evaluating: 95,
  Completed: 100,
};

const buildGenerationPayload = (
  analysis: SynthMedGenerationAnalysis,
  datasetName: string,
): SynthMedGenerationStartPayload => {
  const selectedColumns = analysis.columns.map((column) => column.name);
  const identifierColumns = analysis.potentialIdentifierColumns.filter((name) => selectedColumns.includes(name));
  return {
    sourceDatasetId: analysis.sourceDatasetId,
    datasetName: `${datasetName} synthetic cohort`,
    model: 'CTGAN',
    generationMode: 'Unconditional',
    conditions: [],
    selectedColumns,
    categoricalColumns: analysis.columns
      .filter((column) => column.kind === 'categorical' || column.kind === 'boolean')
      .map((column) => column.name),
    numericalColumns: analysis.columns.filter((column) => column.kind === 'numerical').map((column) => column.name),
    identifierColumns,
    primaryKey: identifierColumns[0] ?? null,
    seed: null,
    epochs: 20,
    batchSize: 100,
    recordCount: Math.min(1000, Math.max(1, analysis.totalRecords * 2)),
    preserveMissingness: true,
  };
};

export const SynthMedDownloads = () => {
  const {
    synthSources,
    synthGenerated,
    refreshSynthMed,
    downloadSynthMedSource,
    downloadSynthMedGenerated,
    analyseSynthMedGeneration,
    startSynthMedGeneration,
    getSynthMedGenerationJob,
  } = useDemo();
  const [loading, setLoading] = useState(true);
  const [selectedSourceId, setSelectedSourceId] = useState('');
  const [job, setJob] = useState<SynthMedGenerationJob | null>(null);
  const [starting, setStarting] = useState(false);
  const [generationError, setGenerationError] = useState('');
  const [downloadPromptOpen, setDownloadPromptOpen] = useState(false);

  useEffect(() => {
    let active = true;
    void refreshSynthMed()
      .catch(() => undefined)
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [refreshSynthMed]);

  useEffect(() => {
    if (!job || TERMINAL_STATUSES.includes(job.status)) return;
    let active = true;
    const timer = window.setInterval(() => {
      void getSynthMedGenerationJob(job.id)
        .then((updated) => {
          if (active) setJob(updated);
        })
        .catch((error: unknown) => {
          if (active) setGenerationError(errorMessage(error));
        });
    }, 2000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [job?.id, job?.status, getSynthMedGenerationJob]);

  useEffect(() => {
    if (job?.status !== 'Completed') return;
    let active = true;
    void refreshSynthMed()
      .catch(() => undefined)
      .finally(() => {
        if (active) setDownloadPromptOpen(true);
      });
    return () => {
      active = false;
    };
  }, [job?.id, job?.status, refreshSynthMed]);

  const selectedSource = synthSources.find((dataset) => dataset.id === selectedSourceId) ?? null;
  const generatedDataset = synthGenerated.find((dataset) => dataset.id === job?.generatedDatasetId) ?? null;
  const jobInProgress = Boolean(job && !TERMINAL_STATUSES.includes(job.status));

  const generate = async () => {
    if (!selectedSource || starting || jobInProgress) return;
    setGenerationError('');
    setDownloadPromptOpen(false);
    setStarting(true);
    try {
      const analysis = await analyseSynthMedGeneration(selectedSource.id);
      const modelable = analysis.columns.filter((column) => !column.constant && !column.potentialIdentifier);
      if (modelable.length === 0) {
        setGenerationError('This source has no modelable columns after identifiers and constants are excluded.');
        return;
      }
      const created = await startSynthMedGeneration(buildGenerationPayload(analysis, selectedSource.datasetName));
      setJob(created);
      await refreshSynthMed().catch(() => undefined);
    } catch (error) {
      setGenerationError(errorMessage(error));
    } finally {
      setStarting(false);
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="Synthetic data"
        title="Download Centre"
        description="Upload a source dataset, generate synthetic data from it, then download the original or the generated output from separate authenticated sections."
        actions={
          <Link to="/synthmed/upload">
            <Button variant="secondary" icon={<UploadCloud size={16} />}>
              Upload source dataset
            </Button>
          </Link>
        }
      />

      <Alert tone="info" title="Authorised downloads only">
        Download links require authentication and are restricted to datasets you own. Download activity is recorded in
        the audit log.
      </Alert>

      {loading ? (
        <Card>
          <LoadingState label="Loading SynthMed datasets…" />
        </Card>
      ) : null}

      <Card id="uploaded-source-datasets">
        <CardHeader
          title="Uploaded Source Datasets"
          subtitle="Select one source, then generate synthetic data from it. Original bytes are never modified."
          action={<Badge tone="neutral">{synthSources.length} files</Badge>}
        />
        {synthSources.length === 0 ? (
          <EmptyState
            title="No source datasets yet"
            description="Upload a CSV, XLSX or JSON source file to see it here."
            action={
              <Link to="/synthmed/upload">
                <Button>Upload source dataset</Button>
              </Link>
            }
          />
        ) : (
          <>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Use</th>
                    <th>Dataset name</th>
                    <th>Original filename</th>
                    <th>Format</th>
                    <th className="num">Size</th>
                    <th>Upload date</th>
                    <th>Uploaded by</th>
                    <th>Status</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {synthSources.map((dataset) => (
                    <tr key={dataset.id} className={selectedSourceId === dataset.id ? 'row-selected' : ''}>
                      <td>
                        <input
                          type="radio"
                          name="synthmed-source-selection"
                          checked={selectedSourceId === dataset.id}
                          onChange={() => {
                            setSelectedSourceId(dataset.id);
                            setJob(null);
                            setGenerationError('');
                            setDownloadPromptOpen(false);
                          }}
                          aria-label={`Select ${dataset.datasetName} for generation`}
                        />
                      </td>
                      <td>
                        <strong>{dataset.datasetName}</strong>
                        <div className="muted small">ID {dataset.id}</div>
                      </td>
                      <td><code className="code small">{dataset.originalFilename}</code></td>
                      <td><Badge tone="info">{dataset.fileFormat}</Badge></td>
                      <td className="num">{formatBytes(dataset.fileSizeBytes)}</td>
                      <td>{formatDateTime(dataset.uploadDate)}</td>
                      <td>{dataset.uploadedBy}</td>
                      <td><Badge tone="success">{dataset.uploadStatus}</Badge></td>
                      <td>
                        <Button
                          variant="secondary"
                          size="sm"
                          icon={<Download size={14} />}
                          onClick={() => void downloadSynthMedSource(dataset)}
                        >
                          Download
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="inline-controls">
              <Button
                variant="primary"
                size="sm"
                icon={<Wand2 size={14} />}
                disabled={!selectedSource || starting || jobInProgress}
                onClick={() => void generate()}
              >
                {starting ? 'Starting generation…' : 'Generate synthetic data'}
              </Button>
              <span className="muted small">
                {selectedSource
                  ? `Selected: ${selectedSource.datasetName}. Generation starts only when you click the button.`
                  : 'Select a source dataset to enable generation.'}
              </span>
            </div>
          </>
        )}
      </Card>

      {job ? (
        <Card id="synthmed-quick-generation-status">
          <CardHeader
            title="Synthetic data generation"
            subtitle={`Job ${job.id} · ${job.modelName} · ${job.requestedRecordCount} records requested`}
            action={
              <Badge tone={job.status === 'Failed' ? 'danger' : job.status === 'Completed' ? 'success' : 'purple'}>
                {job.status}
              </Badge>
            }
          />
          <ProgressBar value={statusProgress[job.status] ?? 10} tone={job.status === 'Failed' ? 'danger' : 'info'} />
          <p className="muted">
            {job.status === 'Completed'
              ? 'Generation finished. You can download the synthetic dataset below.'
              : job.status === 'Failed'
                ? job.error || 'The generation job failed.'
                : 'Generation is running. This page updates automatically; you can keep it open.'}
          </p>
          {job.status === 'Completed' && generatedDataset ? (
            <div className="inline-controls">
              <Link to={`/synthmed/generated/${generatedDataset.id}`}>
                <Button variant="secondary" size="sm" icon={<Eye size={14} />}>View dataset</Button>
              </Link>
              <Button
                variant="success"
                size="sm"
                icon={<Download size={14} />}
                onClick={() => void downloadSynthMedGenerated(generatedDataset)}
              >
                Download synthetic data
              </Button>
            </div>
          ) : null}
        </Card>
      ) : null}

      {generationError ? <Alert tone="danger" title="Generation failed">{generationError}</Alert> : null}
      {job?.status === 'Failed' && !generationError ? (
        <Alert tone="danger" title="Generation failed">{job.error || 'The generation job could not be completed.'}</Alert>
      ) : null}

      <Modal
        open={downloadPromptOpen && job?.status === 'Completed'}
        title="Synthetic data is ready"
        subtitle={generatedDataset ? generatedDataset.datasetName : 'Your generated dataset is available.'}
        onClose={() => setDownloadPromptOpen(false)}
        footer={
          <>
            {generatedDataset ? (
              <Link to={`/synthmed/generated/${generatedDataset.id}`}>
                <Button variant="secondary" icon={<Eye size={16} />}>View dataset</Button>
              </Link>
            ) : null}
            {generatedDataset ? (
              <Button variant="success" icon={<Download size={16} />} onClick={() => void downloadSynthMedGenerated(generatedDataset)}>
                Download now
              </Button>
            ) : null}
          </>
        }
      >
        <div className="success-title">
          <CheckCircle2 size={19} /> Generation completed for {selectedSource?.datasetName ?? 'the selected source'}.
        </div>
        <p className="muted">
          {generatedDataset
            ? `${formatNumber(generatedDataset.recordCount)} synthetic records are ready. Download the file now or find it later under Generated Synthetic Datasets.`
            : 'The generated dataset is ready and can be found under Generated Synthetic Datasets.'}
        </p>
      </Modal>

      <Card id="generated-synthetic-datasets">
        <CardHeader
          title="Generated Synthetic Datasets"
          subtitle="Synthetic outputs are stored separately from source files."
          action={<Badge tone="purple">{synthGenerated.length} files</Badge>}
        />
        {synthGenerated.length === 0 ? (
          <EmptyState
            title="No generated datasets yet"
            description="Select an uploaded source above and choose Generate synthetic data."
            action={
              <Link to="/synthmed/generate">
                <Button variant="secondary" icon={<FlaskConical size={15} />}>
                  Advanced generation options
                </Button>
              </Link>
            }
          />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Generated dataset</th>
                  <th>Source dataset</th>
                  <th>Method</th>
                  <th className="num">Records</th>
                  <th>Generated</th>
                  <th>Format</th>
                  <th className="num">Size</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {synthGenerated.map((dataset) => (
                  <tr key={dataset.id}>
                    <td>
                      <strong>{dataset.datasetName}</strong>
                      <div className="muted small">
                        {dataset.fileName || `${formatNumber(dataset.columnCount)} columns`}
                      </div>
                    </td>
                    <td>{dataset.sourceDatasetName}</td>
                    <td>{dataset.generationMethod || '—'}</td>
                    <td className="num">{formatNumber(dataset.recordCount)}</td>
                    <td>{formatDateTime(dataset.generationDate)}</td>
                    <td><Badge tone="purple">{dataset.fileFormat}</Badge></td>
                    <td className="num">{formatBytes(dataset.fileSizeBytes)}</td>
                    <td><Badge tone="success">{dataset.status}</Badge></td>
                    <td>
                      <div className="table-actions">
                        <Link to={`/synthmed/generated/${dataset.id}`}>
                          <Button variant="secondary" size="sm" icon={<Eye size={14} />}>View</Button>
                        </Link>
                        <Link to={`/synthmed/evaluation?dataset=${encodeURIComponent(dataset.id)}`}>
                          <Button variant="ghost" size="sm" icon={<ShieldCheck size={14} />}>Reports</Button>
                        </Link>
                        <Button
                          variant="secondary"
                          size="sm"
                          icon={<Download size={14} />}
                          disabled={!dataset.fileName}
                          title={dataset.fileName ? 'Download generated file' : 'Generated file is not available'}
                          onClick={() => void downloadSynthMedGenerated(dataset)}
                        >
                          Download
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
    </>
  );
};
