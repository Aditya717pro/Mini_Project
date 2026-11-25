import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { ArrowLeft, Download, FlaskConical, GitBranch, RotateCcw } from 'lucide-react';
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
} from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { formatBytes, formatDateTime, formatNumber } from '../lib/format';
import type { DatasetVersionRecord, SynthMedVersionResponse } from '../types';

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};

const cellText = (value: unknown): string => {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

const recordRows = (value: unknown): [string, unknown][] => Object.entries(asRecord(value));

const extensionFromPath = (value: string): string => {
  const match = value.match(/\.(csv|xlsx|json)$/i);
  return match ? match[1].toLowerCase() : 'csv';
};

const sanitize = (value: string) => value.replace(/[^a-z0-9]+/gi, '-').toLowerCase();

interface VersionView {
  id: string;
  label: string;
  number: number;
  kind: string;
  records: number;
  columns: number;
  createdAt: string;
  checksum: string;
  isCurrent: boolean;
  schema: Record<string, unknown>;
  transformHistory: unknown;
  validation: Record<string, unknown>;
  metadata: Record<string, unknown>;
  parentId: string | null;
  restoredFrom: string | null;
  fileName: string;
  storageReference: string;
  sizeLabel: string;
  format: string;
}

const toView = (version: DatasetVersionRecord | SynthMedVersionResponse, isSynth: boolean): VersionView => {
  if (isSynth) {
    const item = version as SynthMedVersionResponse;
    return {
      id: item.id,
      label: item.versionLabel,
      number: item.versionNumber,
      kind: item.datasetKind,
      records: item.recordCount,
      columns: item.columnCount,
      createdAt: item.createdAt,
      checksum: item.checksumSha256,
      isCurrent: item.isActive,
      schema: item.datasetSchema,
      transformHistory: item.transformHistory,
      validation: item.validationSummary,
      metadata: item.metadata,
      parentId: item.parentVersionId,
      restoredFrom: item.restoredFromVersionId,
      fileName: `v${item.versionNumber}-${sanitize(item.versionLabel)}.${item.fileFormat.toLowerCase()}`,
      storageReference: item.storedPath.split(/[\\/]/).filter(Boolean).slice(-1)[0] ?? item.storedPath,
      sizeLabel: formatBytes(item.fileSizeBytes),
      format: item.fileFormat,
    };
  }
  const item = version as DatasetVersionRecord;
  return {
    id: item.id,
    label: item.versionLabel,
    number: item.versionNumber,
    kind: item.kind,
    records: item.recordCount,
    columns: item.columnCount,
    createdAt: item.createdAt,
    checksum: item.checksumSha256,
    isCurrent: item.isCurrent,
    schema: item.datasetSchema ?? {},
    transformHistory: item.transformationHistory,
    validation: item.validationSummary,
    metadata: item.metadata ?? {},
    parentId: item.parentVersionId,
    restoredFrom: null,
    fileName: `v${item.versionNumber}-${sanitize(item.versionLabel)}.${extensionFromPath(item.rawFilePath)}`,
    storageReference: item.rawFilePath.split(/[\\/]/).filter(Boolean).slice(-1)[0] ?? item.rawFilePath,
    sizeLabel: item.fileAvailable ? 'Available' : 'Unavailable',
    format: extensionFromPath(item.rawFilePath).toUpperCase(),
  };
};

export const DatasetVersionDetail = () => {
  const { datasetId = '', versionId = '' } = useParams();
  const location = useLocation();
  const isSynth = location.pathname.startsWith('/synthmed');
  const {
    role,
    getDatasetVersion,
    downloadDatasetVersion,
    restoreDatasetVersion,
    getSynthMedVersion,
    downloadSynthMedVersion,
    restoreSynthMedVersion,
  } = useDemo();

  const [medVersion, setMedVersion] = useState<DatasetVersionRecord | null>(null);
  const [synthVersion, setSynthVersion] = useState<SynthMedVersionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [restoreOpen, setRestoreOpen] = useState(false);
  const [restoring, setRestoring] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      if (isSynth) {
        setSynthVersion(await getSynthMedVersion(datasetId, versionId));
      } else {
        setMedVersion(await getDatasetVersion(datasetId, versionId));
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unexpected API error');
    } finally {
      setLoading(false);
    }
  }, [datasetId, versionId, isSynth, getDatasetVersion, getSynthMedVersion]);

  useEffect(() => {
    void load();
  }, [load]);

  const version = isSynth ? synthVersion : medVersion;
  const view = useMemo(
    () => (version ? toView(version, isSynth) : null),
    [version, isSynth],
  );
  const canRestore = role === 'Administrator' || (role === 'Contributor' && !isSynth);
  const lineagePath = isSynth
    ? `/synthmed/datasets/${datasetId}/lineage`
    : `/datasets/${datasetId}/versions?lineage=${encodeURIComponent(versionId)}`;
  const backPath = isSynth
    ? `/synthmed/datasets/${datasetId}/versions`
    : `/datasets/${datasetId}/versions`;

  const runDownload = async () => {
    if (!view) return;
    if (isSynth) await downloadSynthMedVersion(datasetId, versionId, view.fileName);
    else await downloadDatasetVersion(datasetId, versionId, view.fileName);
  };

  const runRestore = async () => {
    setRestoring(true);
    try {
      if (isSynth) await restoreSynthMedVersion(datasetId, versionId);
      else await restoreDatasetVersion(datasetId, versionId);
      setRestoreOpen(false);
      await load();
    } catch {
      // Store already reports the error.
    } finally {
      setRestoring(false);
    }
  };

  return (
    <>
      <Link to={backPath} className="back-link"><ArrowLeft size={15} /> Back to version history</Link>
      <PageHeader
        eyebrow={`${datasetId} · ${view?.kind ?? 'Version'}`}
        title={view ? `${view.label} · version details` : 'Version details'}
        description="Stored metadata, schema snapshot and provenance returned by the versioning API."
        actions={
          view ? (
            <>
              <Link to={lineagePath}>
                <Button variant="secondary" icon={<GitBranch size={15} />}>View lineage</Button>
              </Link>
              {!isSynth ? (
                <Link to={`/synthmed/generate?datasetId=${encodeURIComponent(datasetId)}&versionId=${encodeURIComponent(versionId)}`}>
                  <Button icon={<FlaskConical size={15} />} data-testid={`version-generate-${versionId}`}>Generate Synthetic Data</Button>
                </Link>
              ) : null}
              <Button variant="secondary" icon={<Download size={15} />} onClick={() => void runDownload()}>Download</Button>
              {canRestore && !view.isCurrent ? (
                <Button variant="danger" icon={<RotateCcw size={15} />} onClick={() => setRestoreOpen(true)}>Restore</Button>
              ) : null}
            </>
          ) : undefined
        }
      />

      {error ? <Alert tone="danger" title="Could not load version">{error}</Alert> : null}
      {loading ? (
        <Card><LoadingState label="Loading version metadata…" /></Card>
      ) : !view ? (
        <Card>
          <EmptyState
            title="Version not found"
            description="The requested version was not returned by the backend for this dataset."
            action={<Link to={backPath}><Button variant="secondary">Back to version history</Button></Link>}
          />
        </Card>
      ) : (
        <>
          <div className="detail-badges">
            <Badge tone={view.isCurrent ? 'success' : 'neutral'}>{view.isCurrent ? 'Current' : 'Superseded'}</Badge>
            <Badge tone="purple">{view.kind}</Badge>
            <Badge>{view.format}</Badge>
          </div>

          <Card>
            <CardHeader title={view.label} subtitle={`Version ${view.number} · ${view.createdAt ? formatDateTime(view.createdAt) : 'unknown creation date'}`} />
            <div className="info-list">
              <InfoRow label="Version ID"><code className="code small">{view.id}</code></InfoRow>
              <InfoRow label="Dataset ID"><code className="code small">{datasetId}</code></InfoRow>
              <InfoRow label="Records">{formatNumber(view.records)}</InfoRow>
              <InfoRow label="Columns">{formatNumber(view.columns)}</InfoRow>
              <InfoRow label="File format">{view.format}</InfoRow>
              <InfoRow label="File size">{view.sizeLabel}</InfoRow>
              <InfoRow label="Parent version">{view.parentId ? <code className="code small">{view.parentId}</code> : 'None'}</InfoRow>
              <InfoRow label="Restored from">{view.restoredFrom ? <code className="code small">{view.restoredFrom}</code> : 'Not a restore'}</InfoRow>
              <InfoRow label="Storage reference">
                <code className="code small" title="Server-side reference only; not a public URL">{view.storageReference}</code>
              </InfoRow>
              <InfoRow label="Checksum (SHA-256)"><code className="code small">{view.checksum || '—'}</code></InfoRow>
            </div>
          </Card>

          <div className="grid-2">
            <Card>
              <CardHeader title="Schema snapshot" subtitle="Column definitions recorded with this version." />
              {recordRows(view.schema).length ? (
                <div className="table-wrap">
                  <table className="table table-compact">
                    <thead><tr><th>Column</th><th>Definition</th></tr></thead>
                    <tbody>
                      {recordRows(view.schema).map(([column, definition]) => (
                        <tr key={column}>
                          <td><code className="code small">{column}</code></td>
                          <td className="cell-wrap"><code className="code small">{cellText(definition)}</code></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="inline-empty">No schema snapshot was recorded for this version.</div>
              )}
            </Card>
            <Card>
              <CardHeader title="Validation summary" subtitle="Server-recorded validation result." />
              {recordRows(view.validation).length ? (
                <div className="info-list">
                  {recordRows(view.validation).map(([key, value]) => (
                    <InfoRow key={key} label={key}>{cellText(value)}</InfoRow>
                  ))}
                </div>
              ) : (
                <div className="inline-empty">No validation summary was recorded.</div>
              )}
            </Card>
          </div>

          <Card>
            <CardHeader title="Transformation history" subtitle="Recorded steps that produced this version." />
            {Array.isArray(view.transformHistory) && view.transformHistory.length ? (
              <div className="version-timeline">
                {view.transformHistory.map((entry, index) => (
                  <div className="version-item" key={index}>
                    <span className="version-dot" />
                    <div className="version-body">
                      <div className="version-head"><strong>Step {index + 1}</strong></div>
                      <p><code className="code small">{cellText(entry)}</code></p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="inline-empty">No transformation steps were recorded for this version.</div>
            )}
          </Card>

          <Card>
            <CardHeader title="Version metadata" subtitle="Additional provenance stored by the backend." />
            {recordRows(view.metadata).length ? (
              <div className="info-list">
                {recordRows(view.metadata).map(([key, value]) => (
                  <InfoRow key={key} label={key}>
                    {key.toLowerCase().includes('path') || key.toLowerCase().includes('stored')
                      ? <code className="code small" title="Server-side reference only">{cellText(value).split(/[\\/]/).filter(Boolean).slice(-1)[0]}</code>
                      : cellText(value)}
                  </InfoRow>
                ))}
              </div>
            ) : (
              <div className="inline-empty">No additional metadata was recorded.</div>
            )}
            <SectionTitle>Integrity</SectionTitle>
            <Alert tone="info" title="Checksum verification">
              Downloads are verified server-side against this SHA-256 checksum before the file is streamed.
            </Alert>
          </Card>
        </>
      )}

      <Modal
        open={restoreOpen}
        title="Restore this version"
        subtitle={view ? `${view.label} · version ${view.number}` : ''}
        onClose={() => setRestoreOpen(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setRestoreOpen(false)}>Cancel</Button>
            <Button variant="danger" disabled={restoring} icon={<RotateCcw size={15} />} onClick={() => void runRestore()}>
              {restoring ? 'Restoring…' : 'Restore version'}
            </Button>
          </>
        }
      >
        <Alert tone="warning" title="Active file will be replaced">
          This is a server-side restore. The selected snapshot remains stored and the action is recorded in the audit log.
        </Alert>
      </Modal>
    </>
  );
};
