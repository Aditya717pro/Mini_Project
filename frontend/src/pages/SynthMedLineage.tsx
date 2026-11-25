import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, GitBranch, RefreshCw } from 'lucide-react';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  InfoRow,
  LoadingState,
  PageHeader,
} from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { formatDateTime, formatNumber } from '../lib/format';
import type { SynthMedLineageEvent } from '../types';

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};

const cellText = (value: unknown): string => {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

const versionTarget = (event: SynthMedLineageEvent): string | null => {
  const metadata = asRecord(event.metadata);
  const candidate = metadata.versionId ?? metadata.syntheticVersionId ?? metadata.sourceVersionId;
  if (typeof candidate === 'string' && candidate) return candidate;
  if (event.childResourceType.toLowerCase().includes('version')) return event.childResourceId;
  return null;
};

export const SynthMedLineage = () => {
  const { datasetId = '' } = useParams();
  const { synthLineage, getSynthMedDatasetLineage } = useDemo();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      await getSynthMedDatasetLineage(datasetId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unexpected API error');
    } finally {
      setLoading(false);
    }
  }, [datasetId, getSynthMedDatasetLineage]);

  useEffect(() => {
    void load();
  }, [load]);

  const lineage = synthLineage[datasetId];
  const events = lineage?.lineage ?? [];
  const versions = lineage?.versions ?? [];

  return (
    <>
      <Link to={`/synthmed/datasets/${datasetId}/versions`} className="back-link"><ArrowLeft size={15} /> Back to version history</Link>
      <PageHeader
        eyebrow={`SynthMed · ${datasetId}`}
        title="Dataset lineage"
        description="Chronological lineage events recorded with the stored dataset versions and linked reports."
        actions={
          <Button variant="secondary" icon={<RefreshCw size={15} />} onClick={() => void load()}>Refresh</Button>
        }
      />

      {error ? <Alert tone="danger" title="Could not load lineage">{error}</Alert> : null}
      {loading ? (
        <Card><LoadingState label="Loading lineage events…" /></Card>
      ) : !lineage ? (
        <Card>
          <EmptyState title="No lineage returned" description="The lineage endpoint did not return a payload for this dataset." />
        </Card>
      ) : (
        <>
          <Card>
            <CardHeader
              title="Lineage summary"
              subtitle="Counts reflect the current server response"
              action={<Badge tone="purple">{formatNumber(events.length)} events</Badge>}
            />
            <div className="info-list">
              <InfoRow label="Dataset ID"><code className="code small">{lineage.datasetId}</code></InfoRow>
              <InfoRow label="Versions">{formatNumber(versions.length)}</InfoRow>
              <InfoRow label="Lineage events">{formatNumber(events.length)}</InfoRow>
              <InfoRow label="First event">{events.length ? formatDateTime(events[0].createdAt) : '—'}</InfoRow>
              <InfoRow label="Latest event">{events.length ? formatDateTime(events[events.length - 1].createdAt) : '—'}</InfoRow>
            </div>
          </Card>

          <Card>
            <CardHeader title="Event timeline" subtitle="Each item is a real lineage event stored by the backend." />
            {events.length === 0 ? (
              <EmptyState title="No lineage events" description="No relationships have been recorded for this dataset yet." />
            ) : (
              <div className="version-timeline">
                {events.map((event) => {
                  const target = versionTarget(event);
                  return (
                    <div className="version-item" key={event.id}>
                      <span className="version-dot current" />
                      <div className="version-body">
                        <div className="version-head">
                          <strong>{event.eventType}</strong>
                          <Badge tone="neutral">{event.parentResourceType} → {event.childResourceType}</Badge>
                          <span className="muted small">{event.createdAt ? formatDateTime(event.createdAt) : '—'}</span>
                        </div>
                        <p>
                          <code className="code small">{event.parentResourceId}</code>
                          {' → '}
                          {target ? (
                            <Link to={`/synthmed/datasets/${datasetId}/versions/${target}`} className="inline-link">
                              <code className="code small">{event.childResourceId}</code>
                            </Link>
                          ) : (
                            <code className="code small">{event.childResourceId}</code>
                          )}
                        </p>
                        <div className="version-meta">
                          {event.sourceDatasetId ? <span>source: <code className="code small">{event.sourceDatasetId}</code></span> : null}
                          {event.generatedDatasetId ? <span>generated: <code className="code small">{event.generatedDatasetId}</code></span> : null}
                          {Object.entries(asRecord(event.metadata)).map(([key, value]) => (
                            <span key={key}>{key}: {cellText(value)}</span>
                          ))}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>

          {versions.length ? (
            <Card>
              <CardHeader title="Versions in this lineage" subtitle="Snapshots returned alongside the lineage events." />
              <div className="table-wrap">
                <table className="table table-compact">
                  <thead><tr><th>Version</th><th>Kind</th><th className="num">Records</th><th>Created</th><th /></tr></thead>
                  <tbody>
                    {versions.map((version) => (
                      <tr key={version.id}>
                        <td>{version.versionLabel}</td>
                        <td>{version.datasetKind}</td>
                        <td className="num">{formatNumber(version.recordCount)}</td>
                        <td>{version.createdAt ? formatDateTime(version.createdAt) : '—'}</td>
                        <td>
                          <Link to={`/synthmed/datasets/${datasetId}/versions/${version.id}`} className="inline-link">
                            <Button size="sm" variant="ghost" icon={<GitBranch size={14} />}>View</Button>
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          ) : null}
        </>
      )}
    </>
  );
};
