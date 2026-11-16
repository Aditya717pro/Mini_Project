import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  CircleDashed,
  Database,
  FileText,
  Layers,
  Loader2,
  PlayCircle,
  RefreshCw,
  SlidersHorizontal,
  UploadCloud,
  XCircle,
} from 'lucide-react';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  DemoBadge,
  DemoNotice,
  EmptyState,
  PageHeader,
  ProgressBar,
  StatCard,
  Tabs,
  type Tone,
} from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { formatDateTime, formatNumber } from '../lib/format';
import type { EtlJob, StageState } from '../types';

const statusTone = (status: EtlJob['status']): Tone => {
  if (status === 'Completed') return 'success';
  if (status === 'Running') return 'info';
  if (status === 'Review required') return 'warning';
  if (status === 'Failed') return 'danger';
  return 'neutral';
};

const stageIcon = (state: StageState) => {
  if (state === 'Completed') return <CheckCircle2 size={18} />;
  if (state === 'Running') return <Loader2 size={18} className="spin" />;
  if (state === 'Failed') return <XCircle size={18} />;
  if (state === 'Awaiting review') return <AlertTriangle size={18} />;
  return <CircleDashed size={18} />;
};

const stageClass = (state: StageState) => {
  if (state === 'Completed') return 'stage-completed';
  if (state === 'Running') return 'stage-running';
  if (state === 'Failed') return 'stage-failed';
  if (state === 'Awaiting review') return 'stage-review';
  return 'stage-queued';
};

const stageIcons = [<UploadCloud size={18} />, <SlidersHorizontal size={18} />, <Database size={18} />];

export const EtlProcessing = () => {
  const { jobs, resolveMapping, publishJob } = useDemo();
  const [tab, setTab] = useState('all');
  const [selectedId, setSelectedId] = useState<string | null>(
    jobs.find((job) => job.status === 'Review required')?.id ?? jobs[0]?.id ?? null,
  );

  const tabs = [
    { id: 'all', label: 'All jobs', count: jobs.length },
    { id: 'active', label: 'Active', count: jobs.filter((job) => job.status === 'Running' || job.status === 'Queued').length },
    { id: 'review', label: 'Review required', count: jobs.filter((job) => job.status === 'Review required').length },
    { id: 'completed', label: 'Completed', count: jobs.filter((job) => job.status === 'Completed').length },
    { id: 'failed', label: 'Failed', count: jobs.filter((job) => job.status === 'Failed').length },
  ];

  const filtered = useMemo(
    () =>
      jobs.filter((job) => {
        if (tab === 'active') return job.status === 'Running' || job.status === 'Queued';
        if (tab === 'review') return job.status === 'Review required';
        if (tab === 'completed') return job.status === 'Completed';
        if (tab === 'failed') return job.status === 'Failed';
        return true;
      }),
    [jobs, tab],
  );

  const selected = jobs.find((job) => job.id === selectedId) ?? filtered[0] ?? jobs[0] ?? null;
  const suggestedMappings = selected?.mappings.filter((mapping) => mapping.status === 'Suggested') ?? [];
  const canPublish = selected?.status === 'Review required' && suggestedMappings.length === 0;

  return (
    <>
      <PageHeader
        eyebrow="Pipeline"
        title="ETL processing"
        description="Track extract, transform and load jobs. Mapping proposals require explicit contributor approval; nothing is auto-equated by name."
        actions={
          <>
            <Button variant="secondary" icon={<RefreshCw size={16} />} disabled title="Job refresh will be wired to the FastAPI backend.">
              Refresh
            </Button>
            <Link to="/upload">
              <Button icon={<UploadCloud size={16} />}>New upload</Button>
            </Link>
          </>
        }
      />

      <DemoNotice text="Pipeline progress, logs and mapping suggestions are demonstration data. The Python ETL engine (PHASE 6) will replace this simulation without changing the UI contract." />

      <div className="stats-grid">
        <StatCard label="Running jobs" value={jobs.filter((job) => job.status === 'Running').length} hint="Browser-simulated progress" icon={<PlayCircle size={20} />} tone="info" />
        <StatCard label="Awaiting mapping review" value={jobs.filter((job) => job.status === 'Review required').length} hint="Uncertain mappings block load" icon={<AlertTriangle size={20} />} tone="warning" />
        <StatCard label="Completed jobs" value={jobs.filter((job) => job.status === 'Completed').length} hint="Processed versions staged" icon={<CheckCircle2 size={20} />} tone="success" />
        <StatCard label="Failed jobs" value={jobs.filter((job) => job.status === 'Failed').length} hint="Original files preserved" icon={<XCircle size={20} />} tone="danger" />
      </div>

      <div className="etl-layout">
        <Card className="etl-list-card">
          <CardHeader title="Pipeline jobs" subtitle="Select a job to inspect its stages" />
          <Tabs tabs={tabs} active={tab} onChange={setTab} />
          <div className="job-list">
            {filtered.length === 0 ? (
              <EmptyState title="No jobs in this state" description="Choose another filter to see other pipeline jobs." />
            ) : (
              filtered.map((job) => (
                <button
                  key={job.id}
                  className={`job-list-item ${selected?.id === job.id ? 'selected' : ''}`}
                  onClick={() => setSelectedId(job.id)}
                >
                  <div className="job-list-top">
                    <strong>{job.datasetTitle}</strong>
                    <Badge tone={statusTone(job.status)}>{job.status}</Badge>
                  </div>
                  <span className="job-list-sub">{job.id} · {job.stages[0]?.detail ?? ''}</span>
                  <ProgressBar
                    value={job.progress}
                    height={5}
                    tone={job.status === 'Failed' ? 'danger' : job.status === 'Review required' ? 'warning' : job.status === 'Completed' ? 'success' : 'info'}
                  />
                  <div className="job-list-meta">
                    <span>{formatDateTime(job.startedAt)}</span>
                    <span>{job.progress}%</span>
                  </div>
                </button>
              ))
            )}
          </div>
        </Card>

        <div className="etl-detail">
          {selected ? (
            <>
              <Card>
                <CardHeader
                  title={selected.datasetTitle}
                  subtitle={`${selected.id} · started ${formatDateTime(selected.startedAt)}`}
                  action={
                    <div className="card-action-row">
                      <Badge tone={statusTone(selected.status)}>{selected.status}</Badge>
                      <DemoBadge label="Simulated job" />
                    </div>
                  }
                />
                <div className="pipeline">
                  {selected.stages.map((stage, index) => (
                    <div key={stage.key} className={`pipeline-stage ${stageClass(stage.state)}`}>
                      <div className="stage-head">
                        <span className="stage-icon">{stageIcons[index]}</span>
                        <span className="stage-state-icon">{stageIcon(stage.state)}</span>
                      </div>
                      <strong>{stage.label}</strong>
                      <span className="stage-state">{stage.state}</span>
                      <p>{stage.detail}</p>
                      {index < selected.stages.length - 1 ? <ArrowRight className="stage-arrow" size={16} /> : null}
                    </div>
                  ))}
                </div>
                <div className="job-progress-row">
                  <ProgressBar
                    value={selected.progress}
                    tone={selected.status === 'Failed' ? 'danger' : selected.status === 'Review required' ? 'warning' : selected.status === 'Completed' ? 'success' : 'info'}
                    height={10}
                  />
                  <span>{selected.progress}%</span>
                </div>
                <div className="job-facts">
                  <div><span>Rows in</span><strong>{formatNumber(selected.rowsIn)}</strong></div>
                  <div><span>Rows out</span><strong>{formatNumber(selected.rowsOut)}</strong></div>
                  <div><span>Records removed</span><strong>0</strong></div>
                  <div><span>Dataset</span><Link to={`/datasets/${selected.datasetId}`} className="inline-link">{selected.datasetId}</Link></div>
                </div>
                {selected.status === 'Failed' ? (
                  <Alert tone="danger" title="Transform failed">
                    The pipeline stopped without modifying records. Correct the source file or mapping configuration, then
                    re-run the job. A new attempt must create a new job record.
                  </Alert>
                ) : null}
                {selected.status === 'Review required' ? (
                  <Alert tone="warning" title="Load blocked pending mapping review">
                    {suggestedMappings.length > 0
                      ? `${suggestedMappings.length} suggested mapping(s) require an explicit decision. Name similarity is not sufficient evidence of equivalence.`
                      : 'All suggested mappings have been resolved. The processed artefact can be staged, but governance review is still required before access is granted.'}
                  </Alert>
                ) : null}
              </Card>

              <Card>
                <CardHeader
                  title="Column mapping review"
                  subtitle="Approve, correct or leave fields unmapped. Original values are preserved."
                  action={<Badge tone="neutral">{selected.mappings.length} fields</Badge>}
                />
                <div className="table-wrap">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Source column</th>
                        <th>Proposed target</th>
                        <th className="num">Confidence</th>
                        <th>Status</th>
                        <th>Decision</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selected.mappings.map((mapping) => (
                        <tr key={mapping.source}>
                          <td><code className="code">{mapping.source}</code></td>
                          <td>
                            <code className="code">{mapping.target}</code>
                            <span className="table-sub">{mapping.note}</span>
                          </td>
                          <td className="num">
                            <span className={`confidence ${mapping.confidence >= 0.9 ? 'high' : mapping.confidence >= 0.7 ? 'mid' : 'low'}`}>
                              {Math.round(mapping.confidence * 100)}%
                            </span>
                          </td>
                          <td>
                            <Badge tone={mapping.status === 'Approved' ? 'success' : mapping.status === 'Suggested' ? 'warning' : 'neutral'}>
                              {mapping.status}
                            </Badge>
                          </td>
                          <td>
                            {mapping.status === 'Suggested' && selected.status === 'Review required' ? (
                              <div className="row-actions">
                                <Button
                                  size="sm"
                                  variant="success"
                                  onClick={() => resolveMapping(selected.id, mapping.source, 'Approved')}
                                >
                                  Approve
                                </Button>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => resolveMapping(selected.id, mapping.source, 'Unmapped')}
                                >
                                  Leave unmapped
                                </Button>
                              </div>
                            ) : (
                              <span className="muted small">—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {selected.status === 'Review required' ? (
                  <div className="form-actions">
                    <Button
                      disabled={!canPublish}
                      onClick={() => publishJob(selected.id)}
                      icon={<Layers size={16} />}
                    >
                      Stage processed output
                    </Button>
                    <span className="field-hint">
                      {canPublish
                        ? 'Staging does not publish the dataset. Governance approval is still required.'
                        : 'Resolve all suggested mappings to enable staging.'}
                    </span>
                  </div>
                ) : null}
              </Card>

              <Card>
                <CardHeader title="Job log" subtitle="Every transformation is recorded; source values are never silently changed" action={<Badge tone="neutral">{selected.logs.length} entries</Badge>} />
                <div className="log-view">
                  {selected.logs.map((log, index) => (
                    <div key={`${log.time}-${index}`} className="log-row">
                      <span className="log-time">{new Date(log.time).toLocaleTimeString('en-GB')}</span>
                      <Badge tone={log.level === 'ERROR' ? 'danger' : log.level === 'WARN' ? 'warning' : 'neutral'}>{log.level}</Badge>
                      <span className="log-stage">{log.stage}</span>
                      <span className="log-message">{log.message}</span>
                    </div>
                  ))}
                </div>
              </Card>
            </>
          ) : (
            <Card>
              <EmptyState title="No pipeline jobs" description="Upload a dataset to create the first ETL job." action={<Link to="/upload"><Button>Upload dataset</Button></Link>} />
            </Card>
          )}
        </div>
      </div>

      <Card className="callout">
        <div className="callout-icon"><FileText size={18} /></div>
        <div>
          <strong>ETL design contract</strong>
          <p>
            Extract profiles the file; transform proposes mappings and standardisation rules; load writes a new
            version, logs and quality report. The engine will be implemented in Python, independent of API routes, and
            will never delete records or overwrite source files.
          </p>
        </div>
      </Card>
    </>
  );
};
