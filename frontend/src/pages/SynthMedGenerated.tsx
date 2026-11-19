import { Link } from 'react-router-dom';
import { Download, Eye, ShieldCheck, UploadCloud, Wand2 } from 'lucide-react';
import { Badge, Button, Card, CardHeader, EmptyState, PageHeader } from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { formatBytes, formatDateTime, formatNumber } from '../lib/format';

export const SynthMedGenerated = () => {
  const { synthGenerated, downloadSynthMedGenerated, synthSources, synthJobs } = useDemo();
  const activeJobs = synthJobs.filter((job) => !['Completed', 'Failed'].includes(job.status)).length;

  return (
    <>
      <PageHeader
        eyebrow="Synthetic data"
        title="Generated Datasets"
        description="Synthetic outputs from real CTGAN jobs are listed separately from uploaded source datasets."
        actions={
          <Link to="/synthmed/generate">
            <Button variant="secondary" icon={<Wand2 size={16} />}>
              Generate data
            </Button>
          </Link>
        }
      />

      {activeJobs > 0 ? (
        <Card className="job-summary-card">
          <CardHeader
            title="Generation jobs in progress"
            subtitle="Statuses are read from the backend; no simulated progress is shown."
            action={<Badge tone="info">{activeJobs} active</Badge>}
          />
        </Card>
      ) : null}

      <Card>
        <CardHeader
          title="Available synthetic datasets"
          subtitle="Open a dataset to preview records, download formats or review evaluation reports."
          action={<Badge tone="purple">{synthGenerated.length} datasets</Badge>}
        />
        {synthGenerated.length === 0 ? (
          <EmptyState
            title="No generated datasets yet"
            description={
              synthSources.length === 0
                ? 'Upload a source dataset first, then start a CTGAN generation job.'
                : 'Start a CTGAN generation job to create a synthetic dataset.'
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
                  <th>Method</th>
                  <th className="num">Records</th>
                  <th>Generated</th>
                  <th>Format</th>
                  <th className="num">Size</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {synthGenerated.map((dataset) => (
                  <tr key={dataset.id}>
                    <td>
                      <strong>{dataset.datasetName}</strong>
                      <div className="muted small">ID {dataset.id}</div>
                    </td>
                    <td>{dataset.sourceDatasetName}</td>
                    <td>{dataset.generationMethod || '—'}</td>
                    <td className="num">{formatNumber(dataset.recordCount)}</td>
                    <td>{formatDateTime(dataset.generationDate)}</td>
                    <td><Badge tone="purple">{dataset.fileFormat}</Badge></td>
                    <td className="num">{formatBytes(dataset.fileSizeBytes)}</td>
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
