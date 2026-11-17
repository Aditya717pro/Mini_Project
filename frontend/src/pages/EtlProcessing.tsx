import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  CircleDashed,
  Database,
  Download,
  FileText,
  Layers,
  Loader2,
  PlayCircle,
  RefreshCw,
  ShieldCheck,
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
  EmptyState,
  PageHeader,
  ProgressBar,
  StatCard,
  Tabs,
  type Tone,
} from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { formatDateTime, formatNumber } from '../lib/format';
import type {
  EtlProfileIssue,
  JobStatus,
  MappingDecisionInput,
  MappingDecisionType,
  StageState,
} from '../types';

type MappingDraft = {
  decision: MappingDecisionType | 'Pending';
  target: string;
  note: string;
};

const activeStatuses: JobStatus[] = [
  'Queued',
  'Profiling',
  'Review required',
  'Approved',
  'Processing',
  'Running',
];
const failedStatuses: JobStatus[] = ['Failed', 'Cancelled', 'Rejected'];

const statusTone = (status: JobStatus): Tone => {
  if (status === 'Completed') return 'success';
  if (status === 'Processing' || status === 'Running' || status === 'Profiling' || status === 'Approved') return 'info';
  if (status === 'Review required') return 'warning';
  if (status === 'Failed' || status === 'Rejected') return 'danger';
  if (status === 'Cancelled') return 'neutral';
  return 'neutral';
};

const progressTone = (status: JobStatus): Tone => {
  if (status === 'Completed') return 'success';
  if (status === 'Failed' || status === 'Rejected') return 'danger';
  if (status === 'Review required') return 'warning';
  return 'info';
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

const count = (value: number | null | undefined) => (value == null ? '—' : formatNumber(value));

const issueField = (issue: EtlProfileIssue) => issue.field || issue.detail || 'dataset';

export const EtlProcessing = () => {
  const {
    datasets,
    jobs,
    role,
    refresh,
    profileJob,
    recordMappingDecisions,
    approveMappings,
    publishJob,
    cancelJob,
    rejectJob,
    downloadDataset,
  } = useDemo();
  const [tab, setTab] = useState('all');
  const [selectedId, setSelectedId] = useState<string | null>(
    jobs.find((job) => job.status === 'Review required')?.id ?? jobs[0]?.id ?? null,
  );
  const [drafts, setDrafts] = useState<Record<string, MappingDraft>>({});
  const [approvalNote, setApprovalNote] = useState('');
  const [rejectReason, setRejectReason] = useState('');
  const [busy, setBusy] = useState<string | null>(null);

  const selected = jobs.find((job) => job.id === selectedId) ?? jobs[0] ?? null;
  const selectedDataset = datasets.find((dataset) => dataset.id === selected?.datasetId);

  useEffect(() => {
    if (!selected) {
      setDrafts({});
      return;
    }
    const next: Record<string, MappingDraft> = {};
    for (const mapping of selected.mappings) {
      next[mapping.source] = {
        decision: mapping.decision ?? 'Pending',
        target: mapping.decision === 'Approved' ? mapping.target : mapping.proposedTarget ?? mapping.target ?? '',
        note: '',
      };
    }
    setDrafts(next);
    setApprovalNote('');
    setRejectReason('');
  }, [selected?.id, selected?.mappings]);

  const tabs = [
    { id: 'all', label: 'All jobs', count: jobs.length },
    { id: 'active', label: 'Active', count: jobs.filter((job) => activeStatuses.includes(job.status)).length },
    { id: 'review', label: 'Review required', count: jobs.filter((job) => job.status === 'Review required').length },
    { id: 'completed', label: 'Completed', count: jobs.filter((job) => job.status === 'Completed').length },
    { id: 'closed', label: 'Closed', count: jobs.filter((job) => failedStatuses.includes(job.status)).length },
  ];

  const filtered = useMemo(
    () =>
      jobs.filter((job) => {
        if (tab === 'active') return activeStatuses.includes(job.status);
        if (tab === 'review') return job.status === 'Review required';
        if (tab === 'completed') return job.status === 'Completed';
        if (tab === 'closed') return failedStatuses.includes(job.status);
        return true;
      }),
    [jobs, tab],
  );

  const unreviewed = selected?.mappings.filter((mapping) => !drafts[mapping.source] || drafts[mapping.source].decision === 'Pending') ?? [];
  const allDecided = Boolean(selected?.mappings.length) && unreviewed.length === 0;
  const draftDecisions: MappingDecisionInput[] = selected
    ? selected.mappings
        .filter((mapping) => {
          const decision = drafts[mapping.source]?.decision;
          return decision && decision !== 'Pending';
        })
        .map((mapping) => {
          const draft = drafts[mapping.source];
          const decision = draft.decision as MappingDecisionType;
          return {
            source: mapping.source,
            decision,
            target: decision === 'Approved' ? draft.target.trim() || null : null,
            note: draft.note.trim(),
          };
        })
    : [];

  const profile = selected?.profile;
  const profileIssues = profile?.issues ?? [];
  const summary = selected?.transformationSummary ?? {};
  const rowIssues = summary.rowIssues ?? [];
  const errors = Object.entries(summary.errors ?? {});
  const warnings = Object.entries(summary.warnings ?? {});

  const setDraft = (source: string, patch: Partial<MappingDraft>) => {
    setDrafts((prev) => {
      const current = prev[source] ?? { decision: 'Pending' as const, target: '', note: '' };
      return { ...prev, [source]: { ...current, ...patch } };
    });
  };

  const runAction = async (key: string, action: () => Promise<void> | void) => {
    setBusy(key);
    try {
      await action();
    } finally {
      setBusy(null);
    }
  };

  const acceptSuggestions = () => {
    if (!selected) return;
    const next: Record<string, MappingDraft> = {};
    for (const mapping of selected.mappings) {
      const target = mapping.proposedTarget || mapping.target;
      next[mapping.source] = {
        decision: target && mapping.status !== 'Unmapped' ? 'Approved' : 'Unmapped',
        target: target && mapping.status !== 'Unmapped' ? target : '',
        note: 'Accepted from profiling suggestions',
      };
    }
    setDrafts(next);
  };

  return (
    <>
      <PageHeader
        eyebrow="Pipeline"
        title="ETL processing"
        description="Profile uploads, review every proposed mapping, approve the set, then run an atomic load that preserves original files and values."
        actions={
          <>
            <Button
              variant="secondary"
              icon={<RefreshCw size={16} />}
              onClick={() => void runAction('refresh', refresh)}
              disabled={busy === 'refresh'}
            >
              Refresh
            </Button>
            <Link to="/upload">
              <Button icon={<UploadCloud size={16} />}>New upload</Button>
            </Link>
          </>
        }
      />

      <div className="stats-grid">
        <StatCard
          label="In progress"
          value={jobs.filter((job) => job.status === 'Profiling' || job.status === 'Processing' || job.status === 'Running').length}
          hint="Backend-owned job state"
          icon={<Loader2 size={20} />}
          tone="info"
        />
        <StatCard
          label="Awaiting mapping review"
          value={jobs.filter((job) => job.status === 'Review required').length}
          hint="All decisions must be recorded"
          icon={<AlertTriangle size={20} />}
          tone="warning"
        />
        <StatCard
          label="Completed jobs"
          value={jobs.filter((job) => job.status === 'Completed').length}
          hint="Processed outputs staged"
          icon={<CheckCircle2 size={20} />}
          tone="success"
        />
        <StatCard
          label="Closed jobs"
          value={jobs.filter((job) => failedStatuses.includes(job.status)).length}
          hint="Failed, cancelled or rejected"
          icon={<XCircle size={20} />}
          tone="danger"
        />
      </div>

      <div className="etl-layout">
        <Card className="etl-list-card">
          <CardHeader title="Pipeline jobs" subtitle="Select a job to inspect its state" />
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
                  <span className="job-list-sub">
                    {job.id} · {job.currentStage || job.stages[0]?.detail || ''}
                  </span>
                  <ProgressBar value={job.progress} height={5} tone={progressTone(job.status)} />
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
                  subtitle={`${selected.id} · stage ${selected.currentStage || '—'} · started ${formatDateTime(selected.startedAt)}`}
                  action={<Badge tone={statusTone(selected.status)}>{selected.status}</Badge>}
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
                  <ProgressBar value={selected.progress} tone={progressTone(selected.status)} height={10} />
                  <span>{selected.progress}%</span>
                </div>
                <div className="job-facts">
                  <div><span>Rows in</span><strong>{count(selected.rowsIn)}</strong></div>
                  <div><span>Rows out</span><strong>{count(selected.rowsOut)}</strong></div>
                  <div><span>Duplicate records</span><strong>{count(summary.duplicates)}</strong></div>
                  <div>
                    <span>Dataset</span>
                    <Link to={`/datasets/${selected.datasetId}`} className="inline-link">{selected.datasetId}</Link>
                  </div>
                </div>

                {selected.errorMessage ? (
                  <Alert tone="danger" title="Pipeline failed">
                    {selected.errorMessage} Original files and source values were preserved.
                  </Alert>
                ) : null}
                {selected.rejectionReason ? (
                  <Alert tone="danger" title="Job rejected">{selected.rejectionReason}</Alert>
                ) : null}
                {selected.status === 'Review required' ? (
                  <Alert tone="warning" title="Load blocked pending mapping review">
                    {unreviewed.length > 0
                      ? `${unreviewed.length} column${unreviewed.length === 1 ? '' : 's'} still need an explicit decision. Name similarity is not sufficient evidence of equivalence.`
                      : 'All decisions are recorded. Approve the mapping set to make the job runnable.'}
                  </Alert>
                ) : null}
                {selected.status === 'Approved' ? (
                  <Alert tone="success" title="Mappings approved">
                    Approved by {selected.approvedBy || 'a reviewer'} at {formatDateTime(selected.approvedAt || selected.startedAt)}.
                    Only the approved mapping can reach the transform step.
                  </Alert>
                ) : null}

                <div className="form-actions">
                  {selected.status === 'Queued' ? (
                    <Button
                      icon={<PlayCircle size={16} />}
                      onClick={() => void runAction('profile', () => profileJob(selected.id))}
                      disabled={busy === 'profile'}
                    >
                      Start profiling
                    </Button>
                  ) : null}
                  {selected.status === 'Review required' ? (
                    <>
                      <Button
                        variant="success"
                        icon={<ShieldCheck size={16} />}
                        disabled={!allDecided || busy === 'approve'}
                        onClick={() => void runAction('approve', () => approveMappings(selected.id, approvalNote))}
                      >
                        Approve mapping set
                      </Button>
                      <Button
                        variant="secondary"
                        icon={<CheckCircle2 size={16} />}
                        onClick={acceptSuggestions}
                      >
                        Accept suggestions
                      </Button>
                    </>
                  ) : null}
                  {selected.status === 'Approved' ? (
                    <Button
                      icon={<Layers size={16} />}
                      onClick={() => void runAction('run', () => publishJob(selected.id))}
                      disabled={busy === 'run'}
                    >
                      Run approved ETL
                    </Button>
                  ) : null}
                  {selected.status === 'Completed' && selectedDataset ? (
                    <Button
                      variant="secondary"
                      icon={<Download size={16} />}
                      onClick={() => void runAction('download', () => downloadDataset(selectedDataset))}
                      disabled={busy === 'download'}
                    >
                      Download processed output
                    </Button>
                  ) : null}
                  {['Queued', 'Profiling', 'Review required', 'Approved', 'Failed'].includes(selected.status) ? (
                    <Button
                      variant="ghost"
                      onClick={() => void runAction('cancel', () => cancelJob(selected.id))}
                      disabled={busy === 'cancel'}
                    >
                      Cancel job
                    </Button>
                  ) : null}
                </div>
                {selected.status === 'Review required' ? (
                  <div className="form-grid">
                    <label className="field">
                      <span>Approval note</span>
                      <input
                        className="input"
                        value={approvalNote}
                        maxLength={500}
                        placeholder="Why is this mapping set acceptable?"
                        onChange={(event) => setApprovalNote(event.target.value)}
                      />
                    </label>
                  </div>
                ) : null}
                {role === 'Administrator' && !['Running', 'Processing', 'Completed'].includes(selected.status) ? (
                  <div className="form-actions">
                    <input
                      className="input"
                      value={rejectReason}
                      maxLength={1000}
                      placeholder="Rejection reason"
                      onChange={(event) => setRejectReason(event.target.value)}
                    />
                    <Button
                      variant="danger"
                      onClick={() => void runAction('reject', () => rejectJob(selected.id, rejectReason))}
                      disabled={busy === 'reject' || !rejectReason.trim()}
                    >
                      Reject job
                    </Button>
                  </div>
                ) : null}
              </Card>

              <Card>
                <CardHeader
                  title="Extract profile"
                  subtitle="Profiling findings are recorded before any mapping decision"
                  action={<Badge tone={profileIssues.length ? 'warning' : 'success'}>{profileIssues.length} findings</Badge>}
                />
                <div className="job-facts">
                  <div><span>Rows</span><strong>{count(profile?.row_count)}</strong></div>
                  <div><span>Columns</span><strong>{count(profile?.column_count)}</strong></div>
                  <div><span>Missing cells</span><strong>{count(profile?.missing_cells)}</strong></div>
                  <div><span>Duplicate rows</span><strong>{count(profile?.duplicate_rows)}</strong></div>
                </div>
                {profileIssues.length ? (
                  <div className="table-wrap">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Field</th>
                          <th>Finding</th>
                          <th>Severity</th>
                          <th className="num">Affected</th>
                        </tr>
                      </thead>
                      <tbody>
                        {profileIssues.map((issue, index) => (
                          <tr key={`${issueField(issue)}-${issue.code}-${index}`}>
                            <td><code className="code">{issueField(issue)}</code></td>
                            <td>{issue.message}</td>
                            <td>
                              <Badge tone={issue.severity === 'error' ? 'danger' : issue.severity === 'review' ? 'warning' : 'neutral'}>
                                {issue.severity ?? 'info'}
                              </Badge>
                            </td>
                            <td className="num">{count(issue.affected)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="field-hint">No profiling findings are available yet. Start profiling for queued jobs.</p>
                )}
              </Card>

              <Card>
                <CardHeader
                  title="Column mapping review"
                  subtitle="Approve, reject or leave each field unmapped. A reviewer decision is required for every column."
                  action={<Badge tone="neutral">{selected.mappings.length} fields</Badge>}
                />
                {selected.mappings.length ? (
                  <div className="table-wrap">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Source column</th>
                          <th>Inferred type</th>
                          <th>Proposed target</th>
                          <th className="num">Confidence</th>
                          <th>Decision</th>
                          <th>Reviewer</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selected.mappings.map((mapping) => {
                          const draft = drafts[mapping.source] ?? { decision: 'Pending', target: '', note: '' };
                          const editable = selected.status === 'Review required';
                          return (
                            <tr key={mapping.source}>
                              <td>
                                <code className="code">{mapping.source}</code>
                                <span className="table-sub">{mapping.note}</span>
                              </td>
                              <td>{mapping.inferredType || '—'}</td>
                              <td>
                                <code className="code">{mapping.proposedTarget || mapping.target || '—'}</code>
                                {editable && draft.decision === 'Approved' ? (
                                  <input
                                    className="input input-sm"
                                    aria-label={`Target for ${mapping.source}`}
                                    value={draft.target}
                                    onChange={(event) => setDraft(mapping.source, { target: event.target.value })}
                                  />
                                ) : null}
                                {editable ? (
                                  <input
                                    className="input input-sm"
                                    aria-label={`Note for ${mapping.source}`}
                                    placeholder="Decision note"
                                    value={draft.note}
                                    onChange={(event) => setDraft(mapping.source, { note: event.target.value })}
                                  />
                                ) : null}
                              </td>
                              <td className="num">
                                <span className={`confidence ${mapping.confidence >= 0.9 ? 'high' : mapping.confidence >= 0.7 ? 'mid' : 'low'}`}>
                                  {Math.round(mapping.confidence * 100)}%
                                </span>
                              </td>
                              <td>
                                {editable ? (
                                  <select
                                    className="input input-sm"
                                    aria-label={`Decision for ${mapping.source}`}
                                    value={draft.decision}
                                    onChange={(event) =>
                                      setDraft(mapping.source, { decision: event.target.value as MappingDraft['decision'] })
                                    }
                                  >
                                    <option value="Pending">Pending</option>
                                    <option value="Approved">Approve</option>
                                    <option value="Rejected">Reject</option>
                                    <option value="Unmapped">Leave unmapped</option>
                                  </select>
                                ) : (
                                  <Badge
                                    tone={
                                      mapping.decision === 'Approved'
                                        ? 'success'
                                        : mapping.decision
                                          ? 'warning'
                                          : 'neutral'
                                    }
                                  >
                                    {mapping.decision ?? mapping.status}
                                  </Badge>
                                )}
                              </td>
                              <td>
                                {mapping.decidedBy ? (
                                  <>
                                    <span>{mapping.decidedBy}</span>
                                    <span className="table-sub">{formatDateTime(mapping.decidedAt || selected.startedAt)}</span>
                                  </>
                                ) : (
                                  <span className="muted small">—</span>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="field-hint">No mapping suggestions yet. Start profiling to generate proposals.</p>
                )}
                {selected.status === 'Review required' && selected.mappings.length ? (
                  <div className="form-actions">
                    <Button
                      variant="secondary"
                      icon={<ShieldCheck size={16} />}
                      disabled={!allDecided || busy === 'decisions'}
                      onClick={() => void runAction('decisions', () => recordMappingDecisions(selected.id, draftDecisions))}
                    >
                      Save reviewer decisions
                    </Button>
                    <span className="field-hint">
                      {allDecided
                        ? 'All columns have a decision. Save them, then approve the set.'
                        : `${unreviewed.length} column${unreviewed.length === 1 ? '' : 's'} still pending.`}
                    </span>
                  </div>
                ) : null}
              </Card>

              {(errors.length > 0 || warnings.length > 0 || rowIssues.length > 0) ? (
                <Card>
                  <CardHeader
                    title="Transformation report"
                    subtitle="Invalid values are flagged and retained; source values are never silently changed"
                    action={<Badge tone={errors.length ? 'danger' : 'warning'}>{rowIssues.length} row findings</Badge>}
                  />
                  <div className="job-facts">
                    <div><span>Error flags</span><strong>{errors.reduce((sum, [, value]) => sum + value, 0)}</strong></div>
                    <div><span>Review flags</span><strong>{warnings.reduce((sum, [, value]) => sum + value, 0)}</strong></div>
                    <div><span>Duplicate records</span><strong>{count(summary.duplicates)}</strong></div>
                    <div><span>Originals preserved</span><strong>Yes</strong></div>
                  </div>
                  {(errors.length > 0 || warnings.length > 0) ? (
                    <div className="table-wrap">
                      <table className="table">
                        <thead><tr><th>Target</th><th>Severity</th><th className="num">Count</th></tr></thead>
                        <tbody>
                          {errors.map(([target, value]) => (
                            <tr key={`error-${target}`}>
                              <td><code className="code">{target}</code></td>
                              <td><Badge tone="danger">error</Badge></td>
                              <td className="num">{value}</td>
                            </tr>
                          ))}
                          {warnings.map(([target, value]) => (
                            <tr key={`warning-${target}`}>
                              <td><code className="code">{target}</code></td>
                              <td><Badge tone="warning">review</Badge></td>
                              <td className="num">{value}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : null}
                  {rowIssues.length ? (
                    <div className="table-wrap">
                      <table className="table">
                        <thead><tr><th className="num">Row</th><th>Field</th><th>Code</th><th>Value</th><th>Severity</th></tr></thead>
                        <tbody>
                          {rowIssues.slice(0, 50).map((issue, index) => (
                            <tr key={`${issue.row}-${issue.target}-${index}`}>
                              <td className="num">{issue.row ?? '—'}</td>
                              <td><code className="code">{issue.target ?? issue.source ?? '—'}</code></td>
                              <td>{issue.code ?? issue.message ?? '—'}</td>
                              <td>{issue.value == null ? '—' : String(issue.value)}</td>
                              <td>
                                <Badge tone={issue.severity === 'error' ? 'danger' : 'warning'}>
                                  {issue.severity ?? 'review'}
                                </Badge>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : null}
                </Card>
              ) : null}

              <Card>
                <CardHeader
                  title="Job log"
                  subtitle="Every state transition and decision is recorded"
                  action={<Badge tone="neutral">{selected.logs.length} entries</Badge>}
                />
                <div className="log-view">
                  {selected.logs.map((log, index) => (
                    <div key={`${log.time}-${index}`} className="log-row">
                      <span className="log-time">{new Date(log.time).toLocaleTimeString('en-GB')}</span>
                      <Badge tone={log.level === 'ERROR' ? 'danger' : log.level === 'WARN' ? 'warning' : 'neutral'}>
                        {log.level}
                      </Badge>
                      <span className="log-stage">{log.stage}</span>
                      <span className="log-message">
                        {log.message}
                        {Object.keys(log.details ?? {}).length
                          ? ` ${JSON.stringify(log.details)}`
                          : ''}
                      </span>
                    </div>
                  ))}
                </div>
              </Card>

              <Card>
                <div className="callout-icon"><FileText size={18} /></div>
                <p>
                  Raw files are immutable. Processed outputs are staged atomically after approved mappings, with
                  validation and rollback. Rows are flagged, not deleted; missing values are never imputed; ambiguous
                  dates are never guessed.
                </p>
              </Card>
            </>
          ) : (
            <Card>
              <EmptyState
                title="No pipeline jobs"
                description="Upload a dataset to create a queued ETL job."
                action={<Link to="/upload"><Button>Upload dataset</Button></Link>}
              />
            </Card>
          )}
        </div>
      </div>
    </>
  );
};
