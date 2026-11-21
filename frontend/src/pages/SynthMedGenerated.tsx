import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Download, Eye, RefreshCw, ShieldCheck, UploadCloud, Wand2 } from 'lucide-react';
import { Badge, Button, Card, CardHeader, EmptyState, LoadingState, PageHeader } from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { formatBytes, formatDateTime, formatNumber } from '../lib/format';
import type { SynthMedGeneratedDataset } from '../types';

export const SynthMedGenerated = () => {
  const { synthGenerated, downloadSynthMedGenerated, synthSources, synthJobs, refreshSynthMed } = useDemo();
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const activeJobs = synthJobs.filter((job) => !['Completed', 'Failed'].includes(job.status)).length;
  const jobFor = (generatedId: string) => synthJobs.find((job) => job.generatedDatasetId === generatedId);

  useEffect(() => {
    setLoading(true);
    void refreshSynthMed()
      .catch(() => undefined)
      .finally(() => setLoading(false));
  }, [refreshSynthMed]);

  useEffect(() => {
    if (activeJobs === 0) return;
    const timer = window.setInterval(() => {
      void refreshSynthMed().catch(() => undefined);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [activeJobs, refreshSynthMed]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await refreshSynthMed();
    } finally {
      setRefreshing(false);
    }
  };

  const handleDownload = async (dataset: SynthMedGeneratedDataset) => {
    setDownloadingId(dataset.id);
    try {
      await downloadSynthMedGenerated(dataset);
    } finally {
      setDownloadingId(null);
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="Synthetic data"
        title="Generated Datasets"
        description="Synthetic outputs from CTGAN and SDV models. You can preview, evaluate, and download each generated dataset directly."
        actions={
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
            <Button
              variant="secondary"
              icon={<RefreshCw size={15} className={refreshing || loading ? 'spin' : ''} />}
              disabled={refreshing || loading}
              onClick={() => void handleRefresh()}
              title="Refresh generated datasets"
            >
              Refresh
            </Button>
            <Link to="/synthmed/generate">
              <Button variant="primary" icon={<Wand2 size={16} />}>
                Generate data
              </Button>
            </Link>
          </div>
        }
      />

      {activeJobs > 0 ? (
        <Card className="job-summary-card">
          <CardHeader
            title="Generation jobs in progress"
            subtitle="Statuses are updated live from the backend."
            action={<Badge tone="info">{activeJobs} active</Badge>}
          />
        </Card>
      ) : null}

      <Card>
        <CardHeader
          title="Available synthetic datasets"
          subtitle="All generated synthetic data documents with direct download options on the right."
          action={<Badge tone="purple">{synthGenerated.length} datasets</Badge>}
        />
        {loading && synthGenerated.length === 0 ? (
          <LoadingState label="Loading generated datasets…" />
        ) : synthGenerated.length === 0 ? (
          <EmptyState
            title="No generated datasets yet"
            description={
              synthSources.length === 0
                ? 'Upload a source dataset first, then start a generation job.'
                : 'Start a generation job to create synthetic datasets.'
            }
            action={
              synthSources.length === 0 ? (
                <Link to="/synthmed/upload">
                  <Button icon={<UploadCloud size={15} />}>Upload source dataset</Button>
                </Link>
              ) : (
                <Link to="/synthmed/generate">
                  <Button icon={<Wand2 size={15} />}>Generate data</Button>
                </Link>
              )
            }
          />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Generated dataset</th>
                  <th>Source dataset</th>
                  <th>Mode</th>
                  <th>Model</th>
                  <th>Method</th>
                  <th className="num">Records</th>
                  <th>Generated</th>
                  <th>Format</th>
                  <th className="num">Size</th>
                  <th style={{ textAlign: 'right', minWidth: '220px' }}>Download &amp; Actions</th>
                </tr>
              </thead>
              <tbody>
                {synthGenerated.map((dataset) => {
                  const job = jobFor(dataset.id);
                  const mode = dataset.generationMode ?? job?.generationMode ?? 'Unconditional';
                  const model = dataset.selectedModel ?? job?.selectedModel ?? '—';
                  const isDownloading = downloadingId === dataset.id;

                  return (
                    <tr key={dataset.id}>
                      <td>
                        <strong>{dataset.datasetName}</strong>
                        <div className="muted small">ID {dataset.id}</div>
                      </td>
                      <td>{dataset.sourceDatasetName}</td>
                      <td>
                        <Badge tone={mode === 'Conditional' ? 'purple' : 'neutral'}>{mode}</Badge>
                        {job?.conditions.length ? (
                          <div className="muted small">{job.conditions.length} conditions</div>
                        ) : null}
                      </td>
                      <td>{model}</td>
                      <td>{dataset.generationMethod || '—'}</td>
                      <td className="num">{formatNumber(dataset.recordCount)}</td>
                      <td>{formatDateTime(dataset.generationDate)}</td>
                      <td><Badge tone="purple">{dataset.fileFormat}</Badge></td>
                      <td className="num">{formatBytes(dataset.fileSizeBytes)}</td>
                      <td style={{ textAlign: 'right' }}>
                        <div className="table-actions" style={{ justifyContent: 'flex-end' }}>
                          <Link to={`/synthmed/generated/${dataset.id}`}>
                            <Button variant="secondary" size="sm" icon={<Eye size={14} />}>View</Button>
                          </Link>
                          <Link to={`/synthmed/evaluation?dataset=${encodeURIComponent(dataset.id)}`}>
                            <Button variant="ghost" size="sm" icon={<ShieldCheck size={14} />}>Reports</Button>
                          </Link>
                          <Button
                            variant="primary"
                            size="sm"
                            icon={<Download size={14} />}
                            disabled={isDownloading}
                            title={`Download ${dataset.datasetName} (${dataset.fileFormat})`}
                            onClick={() => void handleDownload(dataset)}
                          >
                            {isDownloading ? 'Downloading…' : 'Download'}
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
};
