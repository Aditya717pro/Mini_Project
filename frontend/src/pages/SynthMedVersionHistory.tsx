import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Download, GitBranch, GitCompare, RefreshCw, RotateCcw, Settings2 } from 'lucide-react';
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
import { ComparisonView } from './DatasetVersionHistory';
import type {
  SynthMedConfigSnapshot,
  SynthMedVersionComparison,
  SynthMedVersionResponse,
} from '../types';

const cellText = (value: unknown): string => {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

const shortChecksum = (value: string): string =>
  value ? (value.length > 22 ? `${value.slice(0, 12)}…${value.slice(-6)}` : value) : '—';

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};

const asStrings = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];

const sanitize = (value: string) => value.replace(/[^a-z0-9]+/gi, '-').toLowerCase();

const versionFilename = (version: SynthMedVersionResponse): string =>
  `v${version.versionNumber}-${sanitize(version.versionLabel)}.${version.fileFormat.toLowerCase()}`;

const ConfigView = ({
  snapshot,
  metadata,
  loading,
}: {
  snapshot: SynthMedConfigSnapshot | null;
  metadata: Record<string, unknown>;
  loading: boolean;
}) => {
  if (loading) return <LoadingState label="Loading configuration snapshot…" />;
  if (!snapshot) {
    const rows = Object.entries(metadata).filter(([key]) =>
      !key.toLowerCase().includes('path') && !key.toLowerCase().includes('stored'),
    );
    if (rows.length === 0) {
      return <EmptyState title="No configuration snapshot" description="No immutable snapshot or configuration metadata was returned for this version." />;
    }
    return (
      <div className="info-list">
        {rows.map(([key, value]) => <InfoRow key={key} label={key}>{cellText(value)}</InfoRow>)}
      </div>
    );
  }
  const warnings = [
    ...asStrings(snapshot.config.reuseWarnings),
    ...asStrings(snapshot.config.warnings),
  ];
  return (
    <div className="stack">
      <div className="info-list">
        <InfoRow label="Snapshot ID"><code className="code small">{snapshot.id}</code></InfoRow>
        <InfoRow label="Model">{snapshot.modelName || '—'}</InfoRow>
        <InfoRow label="Config hash"><code className="code small">{snapshot.configHash || '—'}</code></InfoRow>
        <InfoRow label="Immutable">
          <Badge tone={snapshot.isImmutable ? 'success' : 'warning'}>{snapshot.isImmutable ? 'Yes' : 'No'}</Badge>
        </InfoRow>
        <InfoRow label="Source dataset"><code className="code small">{snapshot.sourceDatasetId ?? '—'}</code></InfoRow>
        <InfoRow label="Generation job"><code className="code small">{snapshot.jobId ?? '—'}</code></InfoRow>
        <InfoRow label="Created">{snapshot.createdAt ? formatDateTime(snapshot.createdAt) : '—'}</InfoRow>
      </div>
      {warnings.length ? (
        <Alert tone="warning" title="Snapshot warnings">
          {warnings.join('; ')}
        </Alert>
      ) : null}
      <SectionTitle>Stored parameters</SectionTitle>
      <div className="table-wrap">
        <table className="table table-compact">
          <thead><tr><th>Parameter</th><th>Value</th></tr></thead>
          <tbody>
            {Object.entries(snapshot.config)
              .filter(([key]) => !key.toLowerCase().includes('path') && !key.toLowerCase().includes('stored'))
              .map(([key, value]) => (
                <tr key={key}>
                  <td><code className="code small">{key}</code></td>
                  <td className="cell-wrap"><code className="code small">{cellText(value)}</code></td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export const SynthMedVersionHistory = () => {
  const { datasetId = '' } = useParams();
  const {
    synthVersions,
    synthExperiments,
    role,
    listSynthMedVersions,
    listSynthMedExperiments,
    getSynthMedExperimentConfigurations,
    compareSynthMedVersions,
    restoreSynthMedVersion,
    downloadSynthMedVersion,
  } = useDemo();

  const versions = useMemo(() => synthVersions[datasetId] ?? [], [synthVersions, datasetId]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [compareOpen, setCompareOpen] = useState(false);
  const [compareA, setCompareA] = useState('');
  const [compareB, setCompareB] = useState('');
  const [comparison, setComparison] = useState<SynthMedVersionComparison | null>(null);
  const [comparing, setComparing] = useState(false);
  const [restoreTarget, setRestoreTarget] = useState<SynthMedVersionResponse | null>(null);
  const [restoring, setRestoring] = useState(false);
  const [configTarget, setConfigTarget] = useState<SynthMedVersionResponse | null>(null);
  const [configSnapshot, setConfigSnapshot] = useState<SynthMedConfigSnapshot | null>(null);
  const [configLoading, setConfigLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      await listSynthMedVersions(datasetId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unexpected API error');
    } finally {
      setLoading(false);
    }
  }, [datasetId, listSynthMedVersions]);

  useEffect(() => {
    void load();
  }, [load]);

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
      setComparison(await compareSynthMedVersions(datasetId, compareA, compareB));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unexpected API error');
    } finally {
      setComparing(false);
    }
  };

  const openConfiguration = async (version: SynthMedVersionResponse) => {
    setConfigTarget(version);
    setConfigSnapshot(null);
    setConfigLoading(true);
    try {
      const experiments = synthExperiments.length ? synthExperiments : await listSynthMedExperiments();
      const metadata = asRecord(version.metadata);
      const jobId = cellText(metadata.jobId);
      const match = experiments.find((experiment) =>
        experiment.sourceVersionId === version.id ||
        experiment.generatedVersionId === version.id ||
        (!!jobId && experiment.generationJobId === jobId),
      );
      if (!match) return;
      const snapshots = await getSynthMedExperimentConfigurations(match.id);
      setConfigSnapshot(
        snapshots.find((snapshot) => snapshot.id === match.configurationSnapshotId) ?? snapshots[0] ?? match.configurationSnapshot,
      );
    } catch {
      // Store already reports the error.
    } finally {
      setConfigLoading(false);
    }
  };

  const runRestore = async () => {
    if (!restoreTarget) return;
    setRestoring(true);
    try {
      await restoreSynthMedVersion(datasetId, restoreTarget.id);
      setRestoreTarget(null);
      await load();
    } catch {
      // Store already reports the error.
    } finally {
      setRestoring(false);
    }
  };

  const canManage = role === 'Administrator' || role === 'Contributor';

  return (
    <>
      <Link to="/synthmed/generated" className="back-link"><ArrowLeft size={15} /> Back to generated datasets</Link>
      <PageHeader
        eyebrow={`SynthMed · ${datasetId}`}
        title={versions[0]?.datasetName ?? 'SynthMed version history'}
        description="Immutable dataset snapshots, lineage links and server-side configuration provenance."
        actions={
          <>
            <Link to={`/synthmed/datasets/${datasetId}/lineage`}>
              <Button variant="secondary" icon={<GitBranch size={15} />}>Lineage</Button>
            </Link>
            <Button variant="secondary" icon={<RefreshCw size={15} />} onClick={() => void load()}>Refresh</Button>
          </>
        }
      />

      {error ? <Alert tone="danger" title="Version request failed">{error}</Alert> : null}
      {loading ? (
        <Card><LoadingState label="Loading SynthMed versions…" /></Card>
      ) : versions.length === 0 ? (
        <Card>
          <EmptyState
            title="No SynthMed versions recorded"
            description="Versions are created when source uploads and generated datasets are snapshotted by the backend."
            action={<Button variant="secondary" icon={<RefreshCw size={15} />} onClick={() => void load()}>Try again</Button>}
          />
        </Card>
      ) : (
        <Card>
          <CardHeader
            title="Stored versions"
            subtitle={`${formatNumber(versions.length)} versions returned for this dataset`}
            action={<Badge tone="purple">{versions[0]?.datasetKind ?? 'dataset'}</Badge>}
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
                      <Link to={`/synthmed/datasets/${datasetId}/versions/${version.id}`} className="inline-link">
                        {version.versionLabel}
                      </Link>
                      <div className="stat-hint">
                        {version.versionNumber} · <code className="code small">{shortChecksum(version.checksumSha256)}</code>
                      </div>
                    </td>
                    <td>
                      <div>{version.datasetKind}</div>
                      <Badge tone={version.isActive ? 'success' : 'neutral'}>{version.isActive ? 'Active' : 'Historical'}</Badge>
                    </td>
                    <td className="num">{formatNumber(version.recordCount)}</td>
                    <td>{version.createdAt ? formatDateTime(version.createdAt) : '—'}</td>
                    <td>
                      <div className="inline-actions">
                        <Link to={`/synthmed/datasets/${datasetId}/versions/${version.id}`}>
                          <Button size="sm" variant="secondary">View</Button>
                        </Link>
                        <Button size="sm" variant="ghost" icon={<GitCompare size={14} />} onClick={() => openCompare(version.id)}>Compare</Button>
                        <Link to={`/synthmed/datasets/${datasetId}/lineage`}>
                          <Button size="sm" variant="ghost" icon={<GitBranch size={14} />}>Lineage</Button>
                        </Link>
                        <Button size="sm" variant="ghost" icon={<Settings2 size={14} />} onClick={() => void openConfiguration(version)}>Configuration</Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          icon={<Download size={14} />}
                          disabled={!version.fileSizeBytes}
                          onClick={() => void downloadSynthMedVersion(datasetId, version.id, versionFilename(version))}
                        >
                          Download
                        </Button>
                        {canManage && !version.isActive ? (
                          <Button size="sm" variant="secondary" icon={<RotateCcw size={14} />} onClick={() => setRestoreTarget(version)}>Restore</Button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="field-hint">File sizes: {versions.map((version) => `${version.versionLabel} ${formatBytes(version.fileSizeBytes)}`).join(' · ')}</p>
        </Card>
      )}

      <Modal
        open={compareOpen}
        title="Compare SynthMed versions"
        subtitle="Schema, missingness, distribution and linked report differences from the backend."
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
            <label className="field-label" htmlFor="synth-compare-a">Version A</label>
            <select id="synth-compare-a" className="input" value={compareA} onChange={(event) => setCompareA(event.target.value)}>
              <option value="">Select a version</option>
              {versions.map((version) => <option key={version.id} value={version.id}>{version.versionLabel}</option>)}
            </select>
          </div>
          <div>
            <label className="field-label" htmlFor="synth-compare-b">Version B</label>
            <select id="synth-compare-b" className="input" value={compareB} onChange={(event) => setCompareB(event.target.value)}>
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
        open={configTarget !== null}
        title="Configuration snapshot"
        subtitle={configTarget ? `${configTarget.versionLabel} · ${configTarget.datasetKind}` : ''}
        onClose={() => setConfigTarget(null)}
      >
        <ConfigView
          snapshot={configSnapshot}
          metadata={asRecord(configTarget?.metadata)}
          loading={configLoading}
        />
      </Modal>

      <Modal
        open={restoreTarget !== null}
        title="Restore SynthMed version"
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
        <Alert tone="warning" title="Active dataset file will be replaced">
          The backend verifies the stored checksum before restoring. The historical snapshot and its lineage are preserved.
        </Alert>
      </Modal>
    </>
  );
};
