import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft,
  Download,
  GitCompare,
  History,
  Plus,
  RefreshCw,
  RotateCcw,
} from 'lucide-react';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  Field,
  InfoRow,
  LoadingState,
  Modal,
  PageHeader,
  SectionTitle,
} from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { formatDateTime, formatNumber } from '../lib/format';
import type {
  DatasetLineageEvent,
  DatasetVersionComparison,
  DatasetVersionRecord,
  SynthMedVersionComparison,
} from '../types';

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};

const cellText = (value: unknown): string => {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

const numericText = (value: unknown): string =>
  typeof value === 'number' && Number.isFinite(value) ? formatNumber(value) : cellText(value);

const shortChecksum = (value: string): string =>
  value ? (value.length > 22 ? `${value.slice(0, 12)}…${value.slice(-6)}` : value) : '—';

const extensionFromPath = (value: string): string => {
  const match = value.match(/\.(csv|xlsx|json)$/i);
  return match ? match[1].toLowerCase() : 'csv';
};

const versionFilename = (version: DatasetVersionRecord): string =>
  `dataset-v${version.versionNumber}-${version.versionLabel.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}.${extensionFromPath(version.rawFilePath)}`;

const statusTone = (version: DatasetVersionRecord): 'success' | 'neutral' =>
  version.isCurrent ? 'success' : 'neutral';

export const ComparisonView = ({
  comparison,
}: {
  comparison: DatasetVersionComparison | SynthMedVersionComparison;
}) => {
  const metadata = asRecord(comparison.metadata);
  const missingDeltas = comparison.missing?.deltas ?? {};
  const distributions = comparison.distributions ?? {};
  const dtypeChanges = comparison.schema?.dtypeChanges ?? [];

  return (
    <div className="stack">
      <div className="request-summary">
        <div>
          <span>Version A</span>
          <strong>{comparison.versionA.versionLabel}</strong>
          <small>{shortChecksum(comparison.versionA.checksumSha256)}</small>
        </div>
        <div>
          <span>Version B</span>
          <strong>{comparison.versionB.versionLabel}</strong>
          <small>{shortChecksum(comparison.versionB.checksumSha256)}</small>
        </div>
      </div>
      <div className="info-list">
        <InfoRow label="Record delta">{numericText(metadata.recordCountDelta)}</InfoRow>
        <InfoRow label="Column delta">{numericText(metadata.columnCountDelta)}</InfoRow>
        <InfoRow label="Checksum changed">
          <Badge tone={metadata.checksumChanged === true ? 'warning' : 'success'}>
            {metadata.checksumChanged === true ? 'Yes' : 'No'}
          </Badge>
        </InfoRow>
        <InfoRow label="Common columns">{formatNumber(comparison.schema?.common?.length ?? 0)}</InfoRow>
      </div>

      <div>
        <SectionTitle>Schema changes</SectionTitle>
        <InfoRow label="Added columns">
          {comparison.schema?.added?.length ? comparison.schema.added.join(', ') : 'None'}
        </InfoRow>
        <InfoRow label="Removed columns">
          {comparison.schema?.removed?.length ? comparison.schema.removed.join(', ') : 'None'}
        </InfoRow>
        {dtypeChanges.length ? (
          <div className="table-wrap">
            <table className="table table-compact">
              <thead>
                <tr><th>Column</th><th>Type A</th><th>Type B</th></tr>
              </thead>
              <tbody>
                {dtypeChanges.map((change, index) => (
                  <tr key={`${cellText(change.column)}-${index}`}>
                    <td>{cellText(change.column)}</td>
                    <td>{cellText(change.dtypeA)}</td>
                    <td>{cellText(change.dtypeB)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted small">No column type changes were recorded.</p>
        )}
      </div>

      <div>
        <SectionTitle>Missingness deltas</SectionTitle>
        {Object.keys(missingDeltas).length ? (
          <div className="table-wrap">
            <table className="table table-compact">
              <thead>
                <tr><th>Column</th><th className="num">A</th><th className="num">B</th><th className="num">Delta</th></tr>
              </thead>
              <tbody>
                {Object.entries(missingDeltas).map(([column, delta]) => {
                  const row = asRecord(delta);
                  return (
                    <tr key={column}>
                      <td>{column}</td>
                      <td className="num">{numericText(row.missingA)}</td>
                      <td className="num">{numericText(row.missingB)}</td>
                      <td className="num">{numericText(row.delta)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="inline-empty">No shared columns had missingness values to compare.</div>
        )}
      </div>

      <div>
        <SectionTitle>Distribution changes</SectionTitle>
        {Object.keys(distributions).length ? (
          <div className="table-wrap">
            <table className="table table-compact">
              <thead>
                <tr><th>Column</th><th>Kind</th><th>A</th><th>B</th><th>Delta</th></tr>
              </thead>
              <tbody>
                {Object.entries(distributions).map(([column, value]) => {
                  const row = asRecord(value);
                  return (
                    <tr key={column}>
                      <td>{column}</td>
                      <td>{cellText(row.kind)}</td>
                      <td className="cell-wrap"><code className="code small">{cellText(row.a ?? row.topA)}</code></td>
                      <td className="cell-wrap"><code className="code small">{cellText(row.b ?? row.topB)}</code></td>
                      <td className="cell-wrap"><code className="code small">{cellText(row.delta ?? row.shareDelta)}</code></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="inline-empty">No comparable distributions were returned.</div>
        )}
      </div>

      <div className="grid-2">
        <Card>
          <CardHeader title="Transform history A" />
          <p className="muted small">{cellText(comparison.transformHistory?.a)}</p>
        </Card>
        <Card>
          <CardHeader title="Transform history B" />
          <p className="muted small">{cellText(comparison.transformHistory?.b)}</p>
        </Card>
      </div>
      <div className="grid-2">
        <Card>
          <CardHeader title="Validation A" />
          <p className="muted small">{cellText(comparison.validation?.a)}</p>
        </Card>
        <Card>
          <CardHeader title="Validation B" />
          <p className="muted small">{cellText(comparison.validation?.b)}</p>
        </Card>
      </div>
      {comparison.privacy || comparison.utility ? (
        <Card>
          <CardHeader title="Privacy and utility" subtitle="Attached analysis snapshots for these versions." />
          {comparison.privacy ? <InfoRow label="Privacy"><code className="code small">{cellText(comparison.privacy)}</code></InfoRow> : null}
          {comparison.utility ? <InfoRow label="Utility"><code className="code small">{cellText(comparison.utility)}</code></InfoRow> : null}
        </Card>
      ) : null}
    </div>
  );
};

const LineageView = ({ events }: { events: DatasetLineageEvent[] }) => {
  if (events.length === 0) {
    return <EmptyState title="No lineage events" description="The backend returned no lineage events for this dataset." />;
  }
  return (
    <div className="version-timeline">
      {events.map((event) => (
        <div className="version-item" key={event.id}>
          <span className="version-dot current" />
          <div className="version-body">
            <div className="version-head">
              <strong>{event.eventType}</strong>
              <span className="muted small">{formatDateTime(event.createdAt)}</span>
            </div>
            <p>
              {event.parentResourceType} <code className="code small">{event.parentResourceId}</code>
              {' → '}
              {event.childResourceType} <code className="code small">{event.childResourceId}</code>
            </p>
            <div className="version-meta">
              {Object.entries(event.metadata).map(([key, value]) => (
                <span key={key}>{key}: {cellText(value)}</span>
              ))}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};

export const DatasetVersionHistory = () => {
  const { datasetId = '' } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const lineageParam = searchParams.get('lineage');
  const {
    datasetVersions,
    role,
    listDatasetVersions,
    getDatasetLineage,
    compareDatasetVersions,
    restoreDatasetVersion,
    downloadDatasetVersion,
    createDatasetVersion,
  } = useDemo();

  const summary = datasetVersions[datasetId];
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [compareOpen, setCompareOpen] = useState(false);
  const [compareA, setCompareA] = useState('');
  const [compareB, setCompareB] = useState('');
  const [comparison, setComparison] = useState<DatasetVersionComparison | null>(null);
  const [comparing, setComparing] = useState(false);
  const [restoreTarget, setRestoreTarget] = useState<DatasetVersionRecord | null>(null);
  const [restoring, setRestoring] = useState(false);
  const [lineageOpen, setLineageOpen] = useState(false);
  const [lineageEvents, setLineageEvents] = useState<DatasetLineageEvent[]>([]);
  const [lineageLoading, setLineageLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createNote, setCreateNote] = useState('');
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      await listDatasetVersions(datasetId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unexpected API error');
    } finally {
      setLoading(false);
    }
  }, [datasetId, listDatasetVersions]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!lineageParam) return;
    let active = true;
    setLineageOpen(true);
    setLineageLoading(true);
    void getDatasetLineage(datasetId)
      .then((result) => {
        if (active) setLineageEvents(result.events);
      })
      .catch(() => undefined)
      .finally(() => {
        if (active) setLineageLoading(false);
      });
    return () => {
      active = false;
    };
  }, [datasetId, lineageParam, getDatasetLineage]);

  const versions = useMemo(() => summary?.versions ?? [], [summary]);
  const canManage = role === 'Administrator' || role === 'Contributor';

  const openCompare = (versionId: string) => {
    setCompareA(versionId);
    setCompareB(versions.find((item) => item.id !== versionId)?.id ?? '');
    setComparison(null);
    setCompareOpen(true);
  };

  const runCompare = async () => {
    if (!compareA || !compareB || compareA === compareB) {
      setError('Select two different versions to compare.');
      return;
    }
    setComparing(true);
    setError('');
    try {
      setComparison(await compareDatasetVersions(datasetId, compareA, compareB));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unexpected API error');
    } finally {
      setComparing(false);
    }
  };

  const openLineage = async () => {
    setLineageOpen(true);
    setLineageLoading(true);
    try {
      const result = await getDatasetLineage(datasetId);
      setLineageEvents(result.events);
    } catch {
      // Store already reports the error.
    } finally {
      setLineageLoading(false);
    }
  };

  const runRestore = async () => {
    if (!restoreTarget) return;
    setRestoring(true);
    try {
      await restoreDatasetVersion(datasetId, restoreTarget.id);
      setRestoreTarget(null);
      await load();
    } catch {
      // Store already reports the error.
    } finally {
      setRestoring(false);
    }
  };

  const runCreate = async () => {
    setCreating(true);
    try {
      await createDatasetVersion(datasetId, createNote);
      setCreateOpen(false);
      setCreateNote('');
      await load();
    } catch {
      // Store already reports the error.
    } finally {
      setCreating(false);
    }
  };

  return (
    <>
      <Link to={`/datasets/${datasetId}`} className="back-link"><ArrowLeft size={15} /> Back to dataset</Link>
      <PageHeader
        eyebrow={`${datasetId} · ${summary?.datasetType ?? 'Dataset'}`}
        title={summary?.datasetName ?? 'Dataset version history'}
        description="Every stored version, its provenance and the server-calculated differences between versions."
        actions={
          <>
            <Button variant="secondary" icon={<RefreshCw size={15} />} onClick={() => void load()}>Refresh</Button>
            {canManage ? (
              <Button icon={<Plus size={15} />} onClick={() => setCreateOpen(true)}>Create version</Button>
            ) : null}
          </>
        }
      />

      {error ? <Alert tone="danger" title="Version request failed">{error}</Alert> : null}
      {loading ? (
        <Card><LoadingState label="Loading dataset versions…" /></Card>
      ) : !summary || versions.length === 0 ? (
        <Card>
          <EmptyState
            title="No versions recorded"
            description="The backend has not stored any versions for this dataset yet."
            action={<Button variant="secondary" icon={<RefreshCw size={15} />} onClick={() => void load()}>Try again</Button>}
          />
        </Card>
      ) : (
        <>
          <Card>
            <CardHeader
              title="Version summary"
              subtitle="Reported by the dataset versioning API"
              action={<Badge tone="purple">{formatNumber(summary.totalVersions)} versions</Badge>}
            />
            <div className="info-list">
              <InfoRow label="Dataset ID"><code className="code small">{summary.datasetId}</code></InfoRow>
              <InfoRow label="Dataset type">{summary.datasetType || '—'}</InfoRow>
              <InfoRow label="Owner"><code className="code small">{summary.ownerId}</code></InfoRow>
              <InfoRow label="Current version">{summary.currentVersion || '—'}</InfoRow>
              <InfoRow label="Total versions">{formatNumber(summary.totalVersions)}</InfoRow>
              <InfoRow label="Last updated">{summary.lastUpdatedAt ? formatDateTime(summary.lastUpdatedAt) : '—'}</InfoRow>
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Stored versions"
              subtitle="Original uploads and derived versions are never overwritten in place."
              action={<Button variant="ghost" size="sm" icon={<History size={14} />} onClick={() => void openLineage()}>Dataset lineage</Button>}
            />
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Version</th><th>Type</th><th className="num">Records</th><th>Created</th><th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {versions.map((version) => (
                    <tr key={version.id}>
                      <td>
                        <Link to={`/datasets/${datasetId}/versions/${version.id}`} className="inline-link">
                          {version.versionLabel}
                        </Link>
                        <div className="stat-hint">{version.versionNumber} · <code className="code small">{shortChecksum(version.checksumSha256)}</code></div>
                      </td>
                      <td>
                        <div>{version.kind}</div>
                        <Badge tone={statusTone(version)}>{version.isCurrent ? 'Current' : 'Superseded'}</Badge>
                      </td>
                      <td className="num">{formatNumber(version.recordCount)}</td>
                      <td>{version.createdAt ? formatDateTime(version.createdAt) : '—'}</td>
                      <td>
                        <div className="inline-actions">
                          <Link to={`/datasets/${datasetId}/versions/${version.id}`}>
                            <Button size="sm" variant="secondary">View</Button>
                          </Link>
                          <Button size="sm" variant="ghost" icon={<GitCompare size={14} />} onClick={() => openCompare(version.id)}>Compare</Button>
                          <Button size="sm" variant="ghost" onClick={() => {
                            setLineageEvents([]);
                            setLineageOpen(true);
                            void getDatasetLineage(datasetId)
                              .then((result) => setLineageEvents(result.events))
                              .catch(() => undefined);
                          }}>Lineage</Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            icon={<Download size={14} />}
                            disabled={!version.fileAvailable}
                            title={version.fileAvailable ? 'Download this stored version' : 'No file is available for this version'}
                            onClick={() => void downloadDatasetVersion(datasetId, version.id, versionFilename(version))}
                          >
                            Download
                          </Button>
                          {canManage && !version.isCurrent ? (
                            <Button size="sm" variant="secondary" icon={<RotateCcw size={14} />} onClick={() => setRestoreTarget(version)}>Restore</Button>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}

      <Modal
        open={compareOpen}
        title="Compare stored versions"
        subtitle="Differences are calculated from the stored files by the backend."
        onClose={() => setCompareOpen(false)}
        wide
        footer={
          <>
            <Button variant="ghost" onClick={() => setCompareOpen(false)}>Close</Button>
            <Button icon={<GitCompare size={15} />} disabled={comparing} onClick={() => void runCompare()}>
              {comparing ? 'Comparing…' : 'Compare versions'}
            </Button>
          </>
        }
      >
        <div className="selector-row">
          <div>
            <label className="field-label" htmlFor="compare-a">Version A</label>
            <select id="compare-a" className="input" value={compareA} onChange={(event) => setCompareA(event.target.value)}>
              <option value="">Select a version</option>
              {versions.map((version) => <option key={version.id} value={version.id}>{version.versionLabel}</option>)}
            </select>
          </div>
          <div>
            <label className="field-label" htmlFor="compare-b">Version B</label>
            <select id="compare-b" className="input" value={compareB} onChange={(event) => setCompareB(event.target.value)}>
              <option value="">Select a version</option>
              {versions.map((version) => <option key={version.id} value={version.id}>{version.versionLabel}</option>)}
            </select>
          </div>
        </div>
        {comparison ? <ComparisonView comparison={comparison} /> : (
          <div className="inline-empty">Select two versions and run the comparison to see the real diff.</div>
        )}
      </Modal>

      <Modal
        open={lineageOpen}
        title="Dataset lineage"
        subtitle={`Lineage events for ${datasetId}`}
        onClose={() => {
          setLineageOpen(false);
          if (lineageParam) setSearchParams({}, { replace: true });
        }}
      >
        {lineageLoading ? <LoadingState label="Loading lineage…" /> : <LineageView events={lineageEvents} />}
      </Modal>

      <Modal
        open={restoreTarget !== null}
        title="Restore version"
        subtitle={restoreTarget ? `${restoreTarget.versionLabel} · ${formatNumber(restoreTarget.recordCount)} records` : ''}
        onClose={() => setRestoreTarget(null)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setRestoreTarget(null)}>Cancel</Button>
            <Button variant="danger" disabled={restoring} icon={<RotateCcw size={15} />} onClick={() => void runRestore()}>
              {restoring ? 'Restoring…' : 'Restore version'}
            </Button>
          </>
        }
      >
        <Alert tone="warning" title="Current dataset file will be replaced">
          The backend will copy the selected snapshot over the active dataset file and record the restore in the audit log.
          The historical version itself is not deleted.
        </Alert>
      </Modal>

      <Modal
        open={createOpen}
        title="Create dataset version"
        subtitle="Store a new snapshot of the current dataset file."
        onClose={() => setCreateOpen(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button disabled={creating} icon={<Plus size={15} />} onClick={() => void runCreate()}>
              {creating ? 'Creating…' : 'Create version'}
            </Button>
          </>
        }
      >
        <Field label="Version note" hint="Optional provenance note stored with the new snapshot." htmlFor="version-note">
          <textarea id="version-note" className="input textarea" rows={4} value={createNote} onChange={(event) => setCreateNote(event.target.value)} />
        </Field>
      </Modal>
    </>
  );
};
