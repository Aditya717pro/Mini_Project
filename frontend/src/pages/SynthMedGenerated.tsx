import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Database, Download, Eye, RefreshCw, ShieldCheck, Wand2 } from 'lucide-react';
import { Badge, Button, Card, CardHeader, EmptyState, LoadingState, PageHeader } from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { formatDateTime, formatNumber } from '../lib/format';
import type { SynthMedGeneratedDataset } from '../types';

export const SynthMedGenerated = () => {
  const { synthGenerated, downloadSynthMedGenerated, synthJobs, refreshSynthMed } = useDemo();
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
        title="Generated Synthetic Data"
        description="Review, download and add eligible synthetic outputs to My Repository. Registration is available only after generation is complete."
        actions={
          <div className="table-actions">
            <Button
              variant="secondary"
              icon={<RefreshCw size={15} className={refreshing || loading ? 'spin' : ''} />}
              disabled={refreshing || loading}
              onClick={() => void handleRefresh()}
            >
              Refresh
            </Button>
            <Link to="/synthmed">
              <Button variant="primary" icon={<Wand2 size={16} />}>Generate data</Button>
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
          title="Saved synthetic outputs"
          subtitle="Every row reflects a persisted generation result from SynthMed."
          action={<Badge tone="purple">{synthGenerated.length} datasets</Badge>}
        />
        {loading && synthGenerated.length === 0 ? (
          <LoadingState label="Loading generated datasets…" />
        ) : synthGenerated.length === 0 ? (
          <EmptyState
            title="No generated datasets yet"
            description="Choose an authorised repository dataset and run a real generation job to create the first synthetic output."
            action={<Link to="/synthmed"><Button icon={<Wand2 size={15} />}>Choose a source dataset</Button></Link>}
          />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Generated dataset</th>
                  <th>Source dataset</th>
                  <th>Model</th>
                  <th className="num">Records</th>
                  <th className="num">Columns</th>
                  <th>Generated</th>
                  <th>Status</th>
                  <th>Repository status</th>
                  <th style={{ textAlign: 'right', minWidth: '320px' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {synthGenerated.map((dataset) => {
                  const job = jobFor(dataset.id);
                  const registrationStatus = dataset.repositoryRegistrationStatus || 'Not registered';
                  const isRegistered =
                    registrationStatus === 'Registered in Repository' || Boolean(dataset.repositoryDatasetId);
                  const isComplete = dataset.status === 'Completed' || job?.status === 'Completed';
                  const generationStatus = job?.error || job?.status || dataset.status;
                  const isDownloading = downloadingId === dataset.id;

                  return (
                    <tr key={dataset.id} data-testid={`generated-row-${dataset.id}`}>
                      <td>
                        <strong>{dataset.datasetName}</strong>
                        <div className="muted small"><code className="code small">{dataset.id}</code></div>
                      </td>
                      <td>{dataset.sourceDatasetName}</td>
                      <td><Badge tone="purple">{dataset.selectedModel ?? job?.selectedModel ?? dataset.generationMethod ?? '—'}</Badge></td>
                      <td className="num">{formatNumber(dataset.recordCount)}</td>
                      <td className="num">{formatNumber(dataset.columnCount)}</td>
                      <td>{formatDateTime(dataset.generationDate)}</td>
                      <td><Badge tone={generationStatus === 'Failed' ? 'danger' : 'success'}>{generationStatus}</Badge></td>
                      <td>
                        <Badge tone={isRegistered ? 'success' : 'neutral'}>{registrationStatus}</Badge>
                        {dataset.repositoryDatasetId ? (
                          <div>
                            <Link
                              className="inline-link"
                              to={`/datasets/${dataset.repositoryDatasetId}`}
                              data-testid={`generated-row-registered-${dataset.id}`}
                            >
                              View repository dataset
                            </Link>
                          </div>
                        ) : null}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <div className="table-actions" style={{ justifyContent: 'flex-end' }}>
                          <Link to={`/synthmed/generated/${dataset.id}`}>
                            <Button
                              variant="secondary"
                              size="sm"
                              icon={<Eye size={14} />}
                              data-testid={`generated-row-preview-${dataset.id}`}
                            >
                              Preview
                            </Button>
                          </Link>
                          <Button
                            variant="primary"
                            size="sm"
                            icon={<Download size={14} />}
                            disabled={isDownloading}
                            data-testid={`generated-row-download-${dataset.id}`}
                            onClick={() => void handleDownload(dataset)}
                          >
                            {isDownloading ? 'Downloading…' : 'Download'}
                          </Button>
                          {isComplete && !isRegistered ? (
                            <Link to={`/upload?generatedId=${encodeURIComponent(dataset.id)}`}>
                              <Button
                                variant="success"
                                size="sm"
                                icon={<Database size={14} />}
                                data-testid={`generated-row-upload-${dataset.id}`}
                              >
                                Upload to Repository
                              </Button>
                            </Link>
                          ) : null}
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

      <Card>
        <CardHeader title="Governance" subtitle="Registration is a deliberate release step." />
        <p className="muted small">
          Synthetic outputs are research artefacts, not clinically validated records. Once registered, a dataset is
          visible in My Repository with provenance linking it back to the generated result and its source.
        </p>
        <p className="muted small">
          <ShieldCheck size={14} /> Registration appears only for completed, unregistered generated datasets.
        </p>
      </Card>
    </>
  );
};
