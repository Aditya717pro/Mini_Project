import { useEffect, useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Download, FileText, FlaskConical, KeyRound, Lock, ShieldCheck } from 'lucide-react';
import { AccessBadge, Alert, Badge, Button, Card, CardHeader, EmptyState, InfoRow, LoadingState, PageHeader, StatusBadge, Tabs } from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { formatDate, formatDateTime, formatNumber } from '../lib/format';
import type { Dataset, SynthMedGeneratedEvaluationSummary, SynthMedVersionResponse } from '../types';

const getType = (d: Dataset) => (d.origin === 'Synthetic' ? 'Synthetic' : (d.versions?.length ?? 0) > 1 ? 'Processed' : 'Original');

export const DatasetDetail = () => {
  const { datasetId = '' } = useParams();
  const [searchParams] = useSearchParams();
  const justRegistered = searchParams.get('registered') === '1';
  const { datasets, requests, role, user, downloadDataset, getDatasetLineage, listSynthMedVersions, getSynthMedGeneratedEvaluation, getSynthMedQualityReport, getSynthMedPrivacyReport, getSynthMedClinicalReport, refresh } = useDemo();
  const dataset = datasets.find((d) => d.id === datasetId);
  const [tab, setTab] = useState(() => searchParams.get('tab') || 'overview');
  const [lineage, setLineage] = useState<Record<string, unknown> | null>(null);
  const [synthVersions, setSynthVersions] = useState<SynthMedVersionResponse[]>([]);
  const [evaluation, setEvaluation] = useState<SynthMedGeneratedEvaluationSummary | null>(null);
  const [quality, setQuality] = useState<Record<string, unknown> | null>(null);
  const [privacy, setPrivacy] = useState<Record<string, unknown> | null>(null);
  const [clinical, setClinical] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);

  const isOwner = dataset?.owner === user.name;
  const isPublic = dataset?.access === 'Open';
  const approvedRequest = useMemo(() => requests.some((r) => r.datasetId === dataset?.id && r.direction === 'Outgoing' && r.status === 'Approved'), [requests, dataset?.id]);
  const hasAccess = isPublic || role === 'Administrator' || isOwner || approvedRequest;
  const canDownload = !!dataset && dataset.status === 'Available' && hasAccess;
  const isSynthetic = dataset?.origin === 'Synthetic';
  const sourceDataset = datasets.find((d) => d.id === dataset?.sourceRepositoryDatasetId);
  const relatedReports = requests.filter((r) => r.datasetId === dataset?.id);

  useEffect(() => { void refresh().catch(() => undefined); }, [refresh]);
  useEffect(() => {
    const next = searchParams.get('tab');
    if (next) setTab(next);
  }, [searchParams]);
  useEffect(() => {
    if (!dataset) return;
    let active = true;
    setLoading(true);
    const tasks: Promise<void>[] = [
      getDatasetLineage(dataset.id).then((r) => { if (active) setLineage(r as unknown as Record<string, unknown>); }).catch(() => { if (active) setLineage(null); }),
    ];
    if (isSynthetic && dataset.sourceGeneratedDatasetId) {
      tasks.push(listSynthMedVersions(dataset.sourceGeneratedDatasetId).then((v) => { if (active) setSynthVersions(v); }).catch(() => { if (active) setSynthVersions([]); }));
      tasks.push(getSynthMedGeneratedEvaluation(dataset.sourceGeneratedDatasetId).then((v) => { if (active) setEvaluation(v); }).catch(() => { if (active) setEvaluation(null); }));
      tasks.push(getSynthMedQualityReport(dataset.sourceGeneratedDatasetId).then((v) => { if (active) setQuality(v.report as Record<string, unknown>); }).catch(() => { if (active) setQuality(null); }));
      tasks.push(getSynthMedPrivacyReport(dataset.sourceGeneratedDatasetId).then((v) => { if (active) setPrivacy(v.report as Record<string, unknown>); }).catch(() => { if (active) setPrivacy(null); }));
      tasks.push(getSynthMedClinicalReport(dataset.sourceGeneratedDatasetId).then((v) => { if (active) setClinical(v.report as Record<string, unknown>); }).catch(() => { if (active) setClinical(null); }));
    } else {
      setSynthVersions([]); setEvaluation(null); setQuality(null); setPrivacy(null); setClinical(null);
    }
    Promise.all(tasks).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [dataset, isSynthetic, getDatasetLineage, listSynthMedVersions, getSynthMedGeneratedEvaluation, getSynthMedQualityReport, getSynthMedPrivacyReport, getSynthMedClinicalReport]);

  if (!dataset) {
    return <Card><EmptyState title="Dataset not found" description="The requested dataset is unavailable." action={<Link to="/repository"><Button variant="secondary">Back to repository</Button></Link>} /></Card>;
  }

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'schema', label: 'Schema' },
    { id: 'preview', label: 'Data Preview' },
    { id: 'versions', label: 'Versions' },
    { id: 'lineage', label: 'Lineage' },
    { id: 'quality', label: 'Quality and Validation' },
    { id: 'synthetic', label: 'Synthetic Evaluations' },
    { id: 'reports', label: 'Reports' },
  ];

  return (
    <>
      <PageHeader
        eyebrow="Dataset detail"
        title={dataset.title}
        description={dataset.description}
        actions={<><Link to="/repository"><Button variant="secondary" icon={<ArrowLeft size={16} />}>Repository</Button></Link><Link to={`/synthmed/generate?datasetId=${encodeURIComponent(dataset.id)}`}><Button icon={<FlaskConical size={16} />} data-testid={`dataset-generate-${dataset.id}`}>Generate Synthetic Data</Button></Link>{canDownload ? <Button icon={<Download size={16} />} onClick={() => void downloadDataset(dataset)}>Download</Button> : null}</>}
      />
      {isSynthetic && dataset?.sourceGeneratedDatasetId ? (
        <Alert
          tone="success"
          title={justRegistered ? 'Dataset added to repository' : 'Registered synthetic dataset'}
          data-testid="dataset-registration-banner"
        >
          This synthetic dataset was registered from the stored generation output with provenance preserved.
        </Alert>
      ) : null}
      <div className="detail-badges">
        <Badge tone={isSynthetic ? 'purple' : 'neutral'}>{getType(dataset)}</Badge>
        <StatusBadge status={dataset.status} />
        <AccessBadge access={dataset.access} />
        <Badge tone="neutral">{dataset.format}</Badge>
        {dataset.domain ? <Badge tone="purple">{dataset.domain}</Badge> : null}
      </div>

      {!isPublic ? (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 16px',
          borderRadius: '12px',
          background: hasAccess ? 'rgba(11, 37, 69, 0.06)' : 'rgba(11, 37, 69, 0.1)',
          border: `1px solid ${hasAccess ? 'var(--primary)' : 'var(--amber)'}`,
          margin: '12px 0 16px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Lock size={18} style={{ color: hasAccess ? 'var(--primary)' : 'var(--amber)' }} />
            <div>
              <strong style={{ fontSize: 13 }}>Private Repository</strong>
              <p style={{ margin: 0, fontSize: 12, color: 'var(--text-2)' }}>
                {isOwner
                  ? 'Owned by you. Accessible only by you and collaborators you approve via access requests.'
                  : hasAccess
                  ? 'Access permitted. You have approved access to view and download this repository.'
                  : `Accessible only by the repository owner (${dataset.owner}) and approved users.`}
              </p>
            </div>
          </div>
          {!hasAccess ? (
            <Link to="/access-requests">
              <Button size="sm" icon={<KeyRound size={14} />}>Request Access</Button>
            </Link>
          ) : null}
        </div>
      ) : null}

      <Tabs tabs={tabs} active={tab} onChange={setTab} />

      {tab === 'overview' ? (
        <div className="grid-2">
          <Card>
            <CardHeader title="Overview" subtitle="Dataset metadata and status" />
            <div className="info-list">
              <InfoRow label="Dataset name">{dataset.title}</InfoRow>
              <InfoRow label="Type">{getType(dataset)}</InfoRow>
              <InfoRow label="Disease/category">{dataset.domain}</InfoRow>
              <InfoRow label="Records">{formatNumber(dataset.records)}</InfoRow>
              <InfoRow label="Columns">{formatNumber(dataset.columns)}</InfoRow>
              <InfoRow label="Format">{dataset.format}</InfoRow>
              <InfoRow label="Date added">{formatDate(dataset.createdAt || dataset.updatedAt)}</InfoRow>
              <InfoRow label="Owner">{dataset.owner}</InfoRow>
              <InfoRow label="Visibility">{isPublic ? 'Public (Open to everyone)' : 'Private (Owner & approved users only)'}</InfoRow>
              <InfoRow label="Status">{dataset.status}</InfoRow>
              <InfoRow label="Description">{dataset.description || '—'}</InfoRow>
            </div>
          </Card>
          <Card>
            <CardHeader title={isSynthetic ? 'Provenance' : 'Dataset context'} subtitle={isSynthetic ? 'Synthetic dataset origin and generation trace' : 'Repository metadata'} />
            <div className="info-list">
              {isSynthetic ? (
                <>
                  <InfoRow label="Source dataset">{sourceDataset ? <Link to={`/datasets/${sourceDataset.id}`} className="inline-link">{sourceDataset.title}</Link> : dataset.sourceRepositoryDatasetId || '—'}</InfoRow>
                  <InfoRow label="Generation job ID"><code className="code small">{dataset.generationJobId || '—'}</code></InfoRow>
                  <InfoRow label="Model">{dataset.generationModel || '—'}</InfoRow>
                  <InfoRow label="Timestamp">{formatDateTime(dataset.createdAt)}</InfoRow>
                  <InfoRow label="Generated dataset ID"><code className="code small">{dataset.sourceGeneratedDatasetId || '—'}</code></InfoRow>
                </>
              ) : (
                <>
                  <InfoRow label="Version">{dataset.version}</InfoRow>
                  <InfoRow label="Study design">{dataset.studyDesign || '—'}</InfoRow>
                  <InfoRow label="Geography">{dataset.geography?.join(', ') || '—'}</InfoRow>
                  <InfoRow label="License">{dataset.license || '—'}</InfoRow>
                </>
              )}
            </div>
          </Card>
        </div>
      ) : null}

      {tab === 'schema' ? (
        <Card>
          <CardHeader title="Schema" subtitle="Schema metadata available from repository records" />
          {loading ? <LoadingState label="Loading schema..." /> : (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Field</th><th>Value</th></tr></thead>
                <tbody>
                  <tr><td>Columns</td><td>{formatNumber(dataset.columns)}</td></tr>
                  <tr><td>Label column</td><td>{dataset.labelColumn || '—'}</td></tr>
                  <tr><td>Format</td><td>{dataset.format}</td></tr>
                  <tr><td>Data dictionary</td><td>{dataset.dataDictionaryAvailable ? 'Available' : 'Not supplied'}</td></tr>
                  <tr><td>Intended tasks</td><td>{dataset.intendedTasks?.join(', ') || '—'}</td></tr>
                </tbody>
              </table>
            </div>
          )}
          {!dataset.dataDictionaryAvailable ? <p className="muted small" style={{ marginTop: 12 }}>Column-level schema is not exposed by the current repository API for this dataset.</p> : null}
        </Card>
      ) : null}

      {tab === 'preview' ? (
        <Card>
          <CardHeader title="Data Preview" subtitle="Read-only preview" />
          <EmptyState title="Preview unavailable in repository detail" description={isSynthetic && dataset.sourceGeneratedDatasetId ? 'Open the generated dataset detail to preview synthetic rows.' : 'Row preview is not exposed by the current repository dataset API.'} action={isSynthetic && dataset.sourceGeneratedDatasetId ? <Link to={`/synthmed/generated/${dataset.sourceGeneratedDatasetId}`}><Button variant="secondary">Open generated preview</Button></Link> : undefined} />
        </Card>
      ) : null}

      {tab === 'versions' ? (
        <Card>
          <CardHeader title="Versions" subtitle="Version history and provenance" />
          {isSynthetic ? (
            synthVersions.length === 0 ? <EmptyState title="No synthetic versions" description="No version records were returned for this generated dataset." /> : (
              <div className="table-wrap"><table className="table"><thead><tr><th>Version</th><th>Created</th><th>Records</th><th>Columns</th><th>Note</th></tr></thead><tbody>{synthVersions.map((v) => <tr key={v.id}><td>{v.versionLabel || v.id.slice(0, 8)}</td><td className="muted small">{formatDateTime(v.createdAt)}</td><td className="num">{formatNumber(v.recordCount)}</td><td className="num">{formatNumber(v.columnCount)}</td><td className="muted">{typeof v.metadata?.note === 'string' ? v.metadata.note : '—'}</td></tr>)}</tbody></table></div>
            )
          ) : dataset.versions?.length ? (
            <div className="table-wrap"><table className="table"><thead><tr><th>Version</th><th>Date</th><th>Records</th><th>Status</th><th>Note</th></tr></thead><tbody>{dataset.versions.map((v) => <tr key={v.version}><td>{v.version}</td><td className="muted small">{formatDate(v.date)}</td><td className="num">{formatNumber(v.records)}</td><td><Badge tone={v.status === 'Current' ? 'success' : 'neutral'}>{v.status}</Badge></td><td className="muted">{v.note}</td></tr>)}</tbody></table></div>
          ) : <EmptyState title="No versions" description="No version history is available for this dataset." />}
        </Card>
      ) : null}

      {tab === 'lineage' ? (
        <Card>
          <CardHeader title="Lineage" subtitle="Available provenance and lineage data" />
          {loading ? <LoadingState label="Loading lineage..." /> : lineage ? (
            <pre className="code-block">{JSON.stringify(lineage, null, 2)}</pre>
          ) : (
            <EmptyState title="No lineage data" description={isSynthetic ? 'Synthetic provenance is shown in Overview. Detailed lineage was not returned by the API.' : 'Lineage data is not available for this dataset.'} />
          )}
        </Card>
      ) : null}

      {tab === 'quality' ? (
        <Card>
          <CardHeader title="Quality and Validation" subtitle="Available validation and quality metadata" />
          <div className="info-list">
            <InfoRow label="Quality score">{dataset.qualityScore ?? '—'}</InfoRow>
            <InfoRow label="Readiness score">{dataset.readinessScore ?? '—'}</InfoRow>
            <InfoRow label="Representativeness score">{dataset.representativenessScore ?? '—'}</InfoRow>
            <InfoRow label="Missing rate">{dataset.missingRate != null ? `${dataset.missingRate}%` : '—'}</InfoRow>
            <InfoRow label="Duplicate rate">{dataset.duplicateRate != null ? `${dataset.duplicateRate}%` : '—'}</InfoRow>
          </div>
          {isSynthetic && dataset.sourceGeneratedDatasetId ? <Alert tone="info" title="Synthetic validation">Detailed synthetic quality, privacy, and clinical reports are available in the Synthetic Evaluations tab.</Alert> : null}
        </Card>
      ) : null}

      {tab === 'synthetic' ? (
        isSynthetic ? (
          <div className="stack">
            <Card>
              <CardHeader title="Synthetic Evaluations" subtitle="Real evaluation reports when available" action={dataset.sourceGeneratedDatasetId ? <Link to={`/synthmed/generated/${dataset.sourceGeneratedDatasetId}`} className="inline-link">Open generated detail</Link> : undefined} />
              <div className="info-list">
                <InfoRow label="Source dataset">{sourceDataset?.title || dataset.sourceRepositoryDatasetId || '—'}</InfoRow>
                <InfoRow label="Generation job">{dataset.generationJobId || '—'}</InfoRow>
                <InfoRow label="Model">{dataset.generationModel || '—'}</InfoRow>
                <InfoRow label="Generated dataset ID">{dataset.sourceGeneratedDatasetId || '—'}</InfoRow>
              </div>
            </Card>
            <Card><CardHeader title="Quality evaluation" /><pre className="code-block">{JSON.stringify(quality ?? evaluation?.quality ?? { message: 'No quality evaluation available.' }, null, 2)}</pre></Card>
            <Card><CardHeader title="Privacy evaluation" /><pre className="code-block">{JSON.stringify(privacy ?? evaluation?.privacy ?? { message: 'No privacy evaluation available.' }, null, 2)}</pre></Card>
            <Card><CardHeader title="Clinical validation" /><pre className="code-block">{JSON.stringify(clinical ?? { message: 'No clinical validation report available.' }, null, 2)}</pre></Card>
          </div>
        ) : (
          <Card>
            <CardHeader title="Synthetic Evaluations" subtitle="Synthetic reports for this dataset" />
            <EmptyState title="No synthetic evaluations" description="This repository dataset is not synthetic. Synthetic quality, privacy and clinical reports appear here for synthetic datasets." />
          </Card>
        )
      ) : null}

      {tab === 'reports' ? (
        <Card>
          <CardHeader title="Reports" subtitle="Available reports and access context" />
          {isSynthetic && dataset.sourceGeneratedDatasetId ? (
            <div className="button-row">
              <Link to={`/synthmed/generated/${dataset.sourceGeneratedDatasetId}`}><Button variant="secondary" icon={<FlaskConical size={16} />}>Generated dataset reports</Button></Link>
              <Link to={`/synthmed/evaluation?dataset=${encodeURIComponent(dataset.sourceGeneratedDatasetId)}`}><Button variant="secondary" icon={<ShieldCheck size={16} />}>Evaluation page</Button></Link>
            </div>
          ) : (
            <EmptyState title="No report shortcuts" description="No synthetic report endpoints are associated with this original dataset. Use ETL/quality/readiness workspaces for processing outputs." action={<Link to="/reports"><Button variant="secondary" icon={<FileText size={16} />}>Reports workspace</Button></Link>} />
          )}
          {relatedReports.length > 0 ? <Alert tone="info" title="Access requests">{relatedReports.length} access request(s) reference this dataset.</Alert> : null}
        </Card>
      ) : null}
    </>
  );
};
