import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Download, Eye, FlaskConical, ShieldCheck, UploadCloud } from 'lucide-react';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  LoadingState,
  PageHeader,
} from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { formatBytes, formatDateTime, formatNumber } from '../lib/format';

export const SynthMedDownloads = () => {
  const {
    synthSources,
    synthGenerated,
    refreshSynthMed,
    downloadSynthMedSource,
    downloadSynthMedGenerated,
  } = useDemo();
  const [loading, setLoading] = useState(true);

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

  return (
    <>
      <PageHeader
        eyebrow="Synthetic data"
        title="Download Centre"
        description="Download exact original source files and generated synthetic datasets from separate, authenticated sections."
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
          subtitle="Original uploaded bytes, never cleaned, modified or converted."
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
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
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
                  <tr key={dataset.id}>
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
        )}
      </Card>

      <Card id="generated-synthetic-datasets">
        <CardHeader
          title="Generated Synthetic Datasets"
          subtitle="Synthetic outputs are stored separately from source files."
          action={<Badge tone="purple">{synthGenerated.length} files</Badge>}
        />
        {synthGenerated.length === 0 ? (
          <EmptyState
            title="No generated datasets yet"
            description="Start a CTGAN generation job to create a synthetic dataset."
            action={
              <Link to="/synthmed/generate">
                <Button variant="secondary" icon={<FlaskConical size={15} />}>
                  View generation status
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
