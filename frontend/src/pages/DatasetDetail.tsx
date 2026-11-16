import { useMemo, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  AlertTriangle,
  ArrowLeft,
  BadgeCheck,
  BrainCircuit,
  CalendarDays,
  Download,
  FileKey2,
  Globe2,
  Lock,
  MapPin,
  ShieldCheck,
  Users,
  Workflow,
} from 'lucide-react';
import {
  AccessBadge,
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  DemoBadge,
  EmptyState,
  Field,
  InfoRow,
  Modal,
  PageHeader,
  ProgressBar,
  ScoreRing,
  SectionTitle,
  StatusBadge,
  Tabs,
  type Tone,
} from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { formatDate, formatDateTime, formatNumber, scoreTone } from '../lib/format';
import type { QualityDimensionKey, ReadinessReport } from '../types';

const dimensionLabels: Record<QualityDimensionKey, string> = {
  completeness: 'Completeness',
  validity: 'Validity',
  consistency: 'Consistency',
  uniqueness: 'Uniqueness',
  typeCorrectness: 'Type correctness',
};

const severityTone: Record<string, Tone> = { High: 'danger', Medium: 'warning', Low: 'neutral' };

const chartTooltip = {
  borderRadius: 10,
  border: '1px solid #e2e8e8',
  fontSize: 12,
  boxShadow: '0 8px 24px rgba(15, 43, 42, 0.08)',
};

const verdictTone = (verdict: ReadinessReport['verdict']): Tone =>
  verdict === 'Ready' ? 'success' : verdict === 'Ready with caveats' ? 'warning' : 'danger';

export const DatasetDetail = () => {
  const { datasetId } = useParams();
  const {
    datasets,
    qualityReports,
    readinessReports,
    representativenessReports,
    requests,
    requestAccess,
    role,
  } = useDemo();

  const dataset = datasets.find((item) => item.id === datasetId);
  const quality = dataset ? qualityReports[dataset.id] : undefined;
  const readiness = dataset ? readinessReports[dataset.id] : undefined;
  const representativeness = dataset ? representativenessReports[dataset.id] : undefined;

  const [tab, setTab] = useState('overview');
  const [requestOpen, setRequestOpen] = useState(false);
  const [projectTitle, setProjectTitle] = useState('');
  const [purpose, setPurpose] = useState('');
  const [agreement, setAgreement] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const pendingRequest = useMemo(
    () =>
      dataset
        ? requests.find(
            (request) =>
              request.datasetId === dataset.id &&
              request.direction === 'Outgoing' &&
              request.status === 'Pending',
          )
        : undefined,
    [dataset, requests],
  );

  if (!dataset) {
    return (
      <>
        <PageHeader
          title="Dataset not found"
          description="The dataset ID does not exist in this demo workspace."
          actions={
            <Link to="/repository">
              <Button variant="secondary" icon={<ArrowLeft size={16} />}>Back to repository</Button>
            </Link>
          }
        />
        <Card>
          <EmptyState
            title={`No dataset with ID “${datasetId ?? ''}”`}
            description="Check the identifier or browse the repository for available synthetic datasets."
            action={<Link to="/repository"><Button>Browse repository</Button></Link>}
          />
        </Card>
      </>
    );
  }

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'metadata', label: 'Metadata' },
    { id: 'quality', label: 'Quality' },
    { id: 'readiness', label: 'AI readiness' },
    { id: 'representativeness', label: 'Representativeness' },
    { id: 'versions', label: 'Versions', count: dataset.versions.length },
  ];

  const canRequest = dataset.access !== 'Open' && dataset.status === 'Available';
  const submitRequest = (event: FormEvent) => {
    event.preventDefault();
    const next: Record<string, string> = {};
    if (projectTitle.trim().length < 5) next.projectTitle = 'Enter a project title.';
    if (purpose.trim().length < 40) next.purpose = 'Describe the purpose in at least 40 characters.';
    if (!agreement) next.agreement = 'Accept the data-use terms to continue.';
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    const ok = requestAccess(dataset.id, { projectTitle, purpose });
    if (ok) {
      setRequestOpen(false);
      setProjectTitle('');
      setPurpose('');
      setAgreement(false);
      setErrors({});
    }
  };

  return (
    <>
      <Link to="/repository" className="back-link"><ArrowLeft size={15} /> Back to repository</Link>
      <PageHeader
        eyebrow={`${dataset.id} · ${dataset.domain}`}
        title={dataset.title}
        description={dataset.description}
        actions={
          <>
            <Link to="/etl">
              <Button variant="secondary" icon={<Workflow size={16} />}>ETL status</Button>
            </Link>
            <Button
              variant="secondary"
              disabled
              title="Secure signed downloads are implemented with the backend."
              icon={<Download size={16} />}
            >
              Download
            </Button>
            {canRequest ? (
              pendingRequest ? (
                <Button disabled icon={<Lock size={16} />}>Request pending</Button>
              ) : (
                <Button icon={<FileKey2 size={16} />} onClick={() => setRequestOpen(true)}>Request access</Button>
              )
            ) : (
              <Button disabled icon={<Lock size={16} />}>
                {dataset.access === 'Open' ? 'Open metadata only (demo)' : 'Not available for access'}
              </Button>
            )}
          </>
        }
      />

      <div className="detail-badges">
        <StatusBadge status={dataset.status} />
        <AccessBadge access={dataset.access} />
        <Badge tone="neutral">{dataset.format}</Badge>
        <Badge tone="neutral">{dataset.version}</Badge>
        <Badge tone="purple">{dataset.domain}</Badge>
        {dataset.isLocalPreview ? <DemoBadge label="Local preview" /> : <DemoBadge />}
      </div>

      {dataset.status === 'Pending review' ? (
        <Alert tone="warning" title="Governance review required">
          This dataset is not published. Metadata is visible to authorised users, but file access and downloads are
          disabled until a reviewer approves the dataset and its access classification.
        </Alert>
      ) : null}
      {dataset.status === 'Failed' ? (
        <Alert tone="danger" title="ETL failed — original file preserved">
          The transform stage stopped on a validation error. No records were deleted or modified. Review the ETL log
          and correct the source file or mapping before retrying.
        </Alert>
      ) : null}
      {dataset.isLocalPreview ? (
        <Alert tone="info" title="Client-side preview">
          This record was created in the browser demo. File profiling is real; quality, readiness and representativeness
          scores are generated by demo rules and are not persisted to a backend.
        </Alert>
      ) : null}

      <div className="detail-layout">
        <div className="detail-main">
          <Tabs tabs={tabs} active={tab} onChange={setTab} />

          {tab === 'overview' ? (
            <>
              <div className="grid-3">
                <Card className="score-card">
                  <ScoreRing value={dataset.qualityScore} label="quality" />
                  <div>
                    <strong>Data quality</strong>
                    <p>Completeness, validity, consistency, uniqueness and type correctness.</p>
                    <Link to="/quality" className="inline-link">Open quality workspace</Link>
                  </div>
                </Card>
                <Card className="score-card">
                  <ScoreRing value={dataset.readinessScore} label="readiness" />
                  <div>
                    <strong>AI readiness</strong>
                    <p>Task-specific assessment, scored independently from data quality.</p>
                    <Link to="/readiness" className="inline-link">Open readiness workspace</Link>
                  </div>
                </Card>
                <Card className="score-card">
                  <ScoreRing value={dataset.representativenessScore} label="coverage" />
                  <div>
                    <strong>Representativeness</strong>
                    <p>Demographic coverage based only on recorded attributes.</p>
                    <Link to="/representativeness" className="inline-link">Open coverage analysis</Link>
                  </div>
                </Card>
              </div>

              <Card>
                <CardHeader title="Dataset summary" subtitle="Curated metadata for discovery and research triage" />
                <div className="info-grid">
                  <InfoRow label="Owner">{dataset.owner}</InfoRow>
                  <InfoRow label="Organisation">{dataset.ownerOrganisation}</InfoRow>
                  <InfoRow label="Records">{formatNumber(dataset.records)}</InfoRow>
                  <InfoRow label="Columns">{dataset.columns}</InfoRow>
                  <InfoRow label="Age range">{dataset.ageRange}</InfoRow>
                  <InfoRow label="Geography">{dataset.geography.join(', ')}</InfoRow>
                  <InfoRow label="Study design">{dataset.studyDesign}</InfoRow>
                  <InfoRow label="Collection period">{dataset.collectionPeriod}</InfoRow>
                  <InfoRow label="Licence">{dataset.license}</InfoRow>
                  <InfoRow label="Data dictionary">{dataset.dataDictionaryAvailable ? 'Available' : 'Not supplied'}</InfoRow>
                  <InfoRow label="Ethics approval">{dataset.ethicsApproved ? 'Recorded' : 'Not evidenced'}</InfoRow>
                  <InfoRow label="Label column">{dataset.labelColumn ?? 'None'}</InfoRow>
                  <InfoRow label="Checksum"><code className="code small">{dataset.checksum}</code></InfoRow>
                  <InfoRow label="Last updated">{formatDateTime(dataset.updatedAt)}</InfoRow>
                </div>
                <div className="tag-row">
                  {dataset.tags.map((tagValue) => <span key={tagValue} className="tag">#{tagValue}</span>)}
                </div>
              </Card>

              <Card>
                <CardHeader title="Intended research use" subtitle="Tasks declared by the contributor" />
                <ul className="checklist">
                  {dataset.intendedTasks.map((task) => (
                    <li key={task}><BadgeCheck size={16} /><span>{task}</span></li>
                  ))}
                </ul>
                <Alert tone="info">
                  AI readiness is assessed against the declared task. A high quality score does not imply that the
                  dataset is suitable for every AI use case.
                </Alert>
              </Card>
            </>
          ) : null}

          {tab === 'metadata' ? (
            <Card>
              <CardHeader title="Metadata record" subtitle="Public metadata is separated from controlled file content" />
              <div className="info-grid">
                <InfoRow label="Dataset ID">{dataset.id}</InfoRow>
                <InfoRow label="Version">{dataset.version}</InfoRow>
                <InfoRow label="Created">{formatDateTime(dataset.createdAt)}</InfoRow>
                <InfoRow label="Updated">{formatDateTime(dataset.updatedAt)}</InfoRow>
                <InfoRow label="File format">{dataset.format}</InfoRow>
                <InfoRow label="File size">{dataset.sizeMb} MB</InfoRow>
                <InfoRow label="Rows">{formatNumber(dataset.records)}</InfoRow>
                <InfoRow label="Columns">{dataset.columns}</InfoRow>
                <InfoRow label="Missing cells">{dataset.missingRate}%</InfoRow>
                <InfoRow label="Duplicate rows">{dataset.duplicateRate}%</InfoRow>
                <InfoRow label="Access class">{dataset.access}</InfoRow>
                <InfoRow label="Consent scope">{dataset.consentScope}</InfoRow>
                <InfoRow label="Owner">{dataset.owner}</InfoRow>
                <InfoRow label="Organisation">{dataset.ownerOrganisation}</InfoRow>
              </div>
              <SectionTitle>Governance notes</SectionTitle>
              <p className="muted">
                File contents are never exposed by metadata endpoints. Access to record-level data follows the
                {` ${dataset.access.toLowerCase()}`} access policy and requires an approved request for controlled or
                restricted datasets. In this demo, no file storage or signed URL service is connected.
              </p>
            </Card>
          ) : null}

          {tab === 'quality' ? (
            quality ? (
              <div className="stack">
                <Card>
                  <CardHeader
                    title="Quality assessment"
                    subtitle={`${quality.grade} · rules ${quality.rulesVersion}`}
                    action={<DemoBadge label="Demo report" />}
                  />
                  <div className="report-head">
                    <ScoreRing value={quality.overall} size={132} label="overall" />
                    <div className="report-meta">
                      <div className="report-meta-row"><CalendarDays size={14} /><span>Assessed {formatDateTime(quality.assessedAt)}</span></div>
                      <div className="report-meta-row"><Users size={14} /><span>{formatNumber(quality.sampleSize)} records assessed</span></div>
                      <p>{quality.method}</p>
                    </div>
                  </div>
                  <div className="metric-list">
                    {(Object.keys(quality.dimensions) as QualityDimensionKey[]).map((key) => {
                      const value = quality.dimensions[key];
                      return (
                        <div key={key} className="metric-row">
                          <div className="metric-head">
                            <span>{dimensionLabels[key]}</span>
                            <strong>{value}%</strong>
                          </div>
                          <ProgressBar value={value} tone={scoreTone(value) as Tone} />
                        </div>
                      );
                    })}
                  </div>
                </Card>
                <Card>
                  <CardHeader title="Issues requiring review" subtitle="Flags are not automatic errors unless a validation rule applies" />
                  <div className="table-wrap">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Severity</th>
                          <th>Dimension</th>
                          <th>Field</th>
                          <th>Finding</th>
                          <th className="num">Records</th>
                          <th>Recommendation</th>
                        </tr>
                      </thead>
                      <tbody>
                        {quality.issues.map((issue) => (
                          <tr key={issue.id}>
                            <td><Badge tone={severityTone[issue.severity]}>{issue.severity}</Badge></td>
                            <td className="muted">{dimensionLabels[issue.dimension]}</td>
                            <td><code className="code">{issue.field}</code></td>
                            <td className="cell-wrap">{issue.description}</td>
                            <td className="num">{formatNumber(issue.affectedRecords)}</td>
                            <td className="cell-wrap muted">{issue.recommendation}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              </div>
            ) : (
              <Card>
                <EmptyState
                  title="Quality assessment not available"
                  description="This dataset has not completed the ETL quality stage. Quality reports are generated after processing."
                  action={<Link to="/etl"><Button variant="secondary">Open ETL workspace</Button></Link>}
                />
              </Card>
            )
          ) : null}

          {tab === 'readiness' ? (
            readiness ? (
              <div className="stack">
                <Card>
                  <CardHeader
                    title="AI-readiness assessment"
                    subtitle={`Task: ${readiness.task}`}
                    action={<Badge tone={verdictTone(readiness.verdict)}>{readiness.verdict}</Badge>}
                  />
                  <div className="report-head">
                    <ScoreRing value={readiness.overall} size={132} label="overall" />
                    <div className="report-meta">
                      <div className="report-meta-row"><CalendarDays size={14} /><span>Assessed {formatDateTime(readiness.assessedAt)}</span></div>
                      <div className="report-meta-row"><BrainCircuit size={14} /><span>{readiness.method}</span></div>
                      <p>
                        Data quality and AI readiness are separate measures. This score is relative to the declared
                        research task and is not a guarantee of model performance.
                      </p>
                    </div>
                  </div>
                  <div className="metric-list">
                    {readiness.categories.map((category) => (
                      <div key={category.key} className="metric-row">
                        <div className="metric-head">
                          <span>{category.label} <small className="muted">· weight {category.weight}%</small></span>
                          <strong>{category.score}</strong>
                        </div>
                        <ProgressBar value={category.score} tone={scoreTone(category.score) as Tone} />
                        <p className="metric-note">{category.note}</p>
                      </div>
                    ))}
                  </div>
                </Card>
                <div className="grid-2">
                  <Card>
                    <CardHeader title="Limitations" subtitle="Identified by the rule-based assessment" />
                    <ul className="bullet-list">
                      {readiness.limitations.map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  </Card>
                  <Card>
                    <CardHeader title="Recommendations" subtitle="Actions before research use" />
                    <ul className="bullet-list bullet-check">
                      {readiness.recommendations.map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  </Card>
                </div>
              </div>
            ) : (
              <Card>
                <EmptyState
                  title="AI-readiness report not available"
                  description="Readiness is assessed after the quality stage completes. A labelled or clearly defined task is required."
                  action={<Link to="/readiness"><Button variant="secondary">Open readiness workspace</Button></Link>}
                />
              </Card>
            )
          ) : null}

          {tab === 'representativeness' ? (
            representativeness ? (
              <div className="stack">
                <Alert tone="info" title="Recorded attributes only">
                  Missing demographic attributes are reported explicitly and are never inferred. Charts describe the
                  synthetic source file, not a target population.
                </Alert>
                <div className="grid-2">
                  <Card>
                    <CardHeader title="Age distribution" subtitle={dataset.ageRange} />
                    <div className="chart-box">
                      <ResponsiveContainer width="100%" height={230}>
                        <BarChart data={representativeness.ageBands} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#eef2f2" vertical={false} />
                          <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#6b7c7b' }} axisLine={false} tickLine={false} interval={0} angle={-18} textAnchor="end" height={48} />
                          <YAxis tick={{ fontSize: 10, fill: '#6b7c7b' }} axisLine={false} tickLine={false} />
                          <Tooltip contentStyle={chartTooltip} />
                          <Bar dataKey="value" name="Records" radius={[5, 5, 0, 0]}>
                            {representativeness.ageBands.map((entry) => <Cell key={entry.label} fill="#0f766e" />)}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </Card>
                  <Card>
                    <CardHeader title="Geographic representation" subtitle={dataset.geography.join(', ')} />
                    <div className="chart-box">
                      <ResponsiveContainer width="100%" height={230}>
                        <BarChart data={representativeness.geography} layout="vertical" margin={{ top: 8, right: 16, left: 12, bottom: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#eef2f2" horizontal={false} />
                          <XAxis type="number" tick={{ fontSize: 10, fill: '#6b7c7b' }} axisLine={false} tickLine={false} />
                          <YAxis type="category" dataKey="label" width={96} tick={{ fontSize: 10, fill: '#4b5b5a' }} axisLine={false} tickLine={false} />
                          <Tooltip contentStyle={chartTooltip} />
                          <Bar dataKey="value" name="Records" radius={[0, 5, 5, 0]} fill="#0ea5e9" />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </Card>
                </div>
                <div className="grid-2">
                  <Card>
                    <CardHeader title="Pregnancy-stage coverage" subtitle="Only shown where recorded at source" />
                    {representativeness.pregnancyStages.length > 0 ? (
                      <div className="chart-box">
                        <ResponsiveContainer width="100%" height={220}>
                          <BarChart data={representativeness.pregnancyStages} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#eef2f2" vertical={false} />
                            <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#6b7c7b' }} axisLine={false} tickLine={false} interval={0} />
                            <YAxis tick={{ fontSize: 10, fill: '#6b7c7b' }} axisLine={false} tickLine={false} />
                            <Tooltip contentStyle={chartTooltip} />
                            <Bar dataKey="value" name="Records" radius={[5, 5, 0, 0]} fill="#8b5cf6" />
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    ) : (
                      <div className="inline-empty">Pregnancy stage is not applicable or not recorded for this dataset.</div>
                    )}
                  </Card>
                  <Card>
                    <CardHeader title="Paediatric age groups" subtitle="Only shown where applicable" />
                    {representativeness.paediatricGroups.length > 0 ? (
                      <div className="chart-box">
                        <ResponsiveContainer width="100%" height={220}>
                          <BarChart data={representativeness.paediatricGroups} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#eef2f2" vertical={false} />
                            <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#6b7c7b' }} axisLine={false} tickLine={false} interval={0} />
                            <YAxis tick={{ fontSize: 10, fill: '#6b7c7b' }} axisLine={false} tickLine={false} />
                            <Tooltip contentStyle={chartTooltip} />
                            <Bar dataKey="value" name="Records" radius={[5, 5, 0, 0]} fill="#f59e0b" />
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    ) : (
                      <div className="inline-empty">Paediatric groups are not applicable to this dataset.</div>
                    )}
                  </Card>
                </div>
                <Card>
                  <CardHeader title="Unavailable demographic attributes" subtitle="Reported explicitly; no values inferred" />
                  <div className="table-wrap">
                    <table className="table">
                      <thead>
                        <tr><th>Attribute</th><th>Status</th><th>Action</th></tr>
                      </thead>
                      <tbody>
                        {representativeness.missingAttributes.map((item) => (
                          <tr key={item.attribute}>
                            <td><strong>{item.attribute}</strong></td>
                            <td className="muted">{item.detail}</td>
                            <td className="muted">{item.action}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              </div>
            ) : (
              <Card>
                <EmptyState
                  title="Representativeness analysis not available"
                  description="The analysis is generated after processing. Demographic attributes must be present in the source file; they are never inferred."
                  action={<Link to="/representativeness"><Button variant="secondary">Open coverage workspace</Button></Link>}
                />
              </Card>
            )
          ) : null}

          {tab === 'versions' ? (
            <Card>
              <CardHeader title="Dataset versions" subtitle="Original uploads are never overwritten" />
              <div className="version-timeline">
                {dataset.versions.map((item) => (
                  <div key={item.version} className="version-item">
                    <span className={`version-dot ${item.status === 'Current' ? 'current' : ''}`} />
                    <div className="version-body">
                      <div className="version-head">
                        <strong>{item.version}</strong>
                        <Badge tone={item.status === 'Current' ? 'success' : 'neutral'}>{item.status}</Badge>
                        <span className="muted small">{formatDate(item.date)}</span>
                      </div>
                      <p>{item.note}</p>
                      <div className="version-meta">
                        <span>{formatNumber(item.records)} records</span>
                        <code className="code small">{item.checksum.slice(0, 24)}…</code>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          ) : null}
        </div>

        <aside className="detail-side">
          <Card>
            <CardHeader title="Access & governance" />
            <div className="side-badges">
              <AccessBadge access={dataset.access} />
              <StatusBadge status={dataset.status} />
            </div>
            <div className="side-list">
              <div><Globe2 size={15} /><span>{dataset.geography.join(', ')}</span></div>
              <div><ShieldCheck size={15} /><span>{dataset.ethicsApproved ? 'Ethics evidence recorded' : 'Ethics evidence missing'}</span></div>
              <div><MapPin size={15} /><span>{dataset.ownerOrganisation}</span></div>
              <div><Lock size={15} /><span>{dataset.license}</span></div>
            </div>
            {canRequest ? (
              <Button className="full-width" onClick={() => setRequestOpen(true)} icon={<FileKey2 size={16} />}>
                Request access
              </Button>
            ) : dataset.access === 'Open' ? (
              <Button className="full-width" variant="secondary" disabled>Open access · download not connected</Button>
            ) : (
              <Button className="full-width" variant="secondary" disabled>Access unavailable while {dataset.status.toLowerCase()}</Button>
            )}
            <p className="side-note">
              Signed file downloads are not implemented in this demo. Metadata views do not grant record-level access.
            </p>
          </Card>

          <Card>
            <CardHeader title="Report provenance" />
            <ul className="provenance-list">
              <li><span>Quality</span><strong>{quality ? quality.rulesVersion : 'Not assessed'}</strong></li>
              <li><span>Readiness</span><strong>{readiness ? 'Rule-based v0.1' : 'Not assessed'}</strong></li>
              <li><span>Coverage</span><strong>{representativeness ? 'Recorded attributes only' : 'Not assessed'}</strong></li>
              <li><span>Assessment mode</span><strong>Demo</strong></li>
            </ul>
            <Alert tone="warning">
              No regulatory compliance is claimed. Reports are demonstration outputs for synthetic data.
            </Alert>
          </Card>

          {role !== 'Researcher' ? (
            <Card>
              <CardHeader title="Role note" subtitle={`Current demo role: ${role}`} />
              <p className="muted small">
                {role === 'Contributor'
                  ? 'Contributors can manage their own datasets. Access requests are reviewed by data owners and administrators.'
                  : 'Administrators can review governance queues. This demo shows role-aware controls but does not implement authentication.'}
              </p>
            </Card>
          ) : null}
        </aside>
      </div>

      <Modal
        open={requestOpen}
        title="Request dataset access"
        subtitle={`${dataset.title} · ${dataset.access}`}
        onClose={() => setRequestOpen(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setRequestOpen(false)}>Cancel</Button>
            <Button type="submit" form="access-request-form" icon={<FileKey2 size={16} />}>Submit request</Button>
          </>
        }
      >
        <form id="access-request-form" onSubmit={submitRequest} className="stack-sm">
          <Alert tone="warning">
            {dataset.access === 'Restricted'
              ? 'Restricted data requires sponsor approval, an ethics reference and a secure analysis environment. You can submit the request now, but approval is not guaranteed.'
              : 'Controlled data requires an approved data-use agreement. The dataset owner or an administrator will review this request.'}
          </Alert>
          <Field label="Project title" required error={errors.projectTitle} htmlFor="projectTitle">
            <input
              id="projectTitle"
              className="input"
              value={projectTitle}
              onChange={(event) => setProjectTitle(event.target.value)}
              placeholder="Short descriptive study title"
            />
          </Field>
          <Field
            label="Purpose and analysis plan"
            required
            error={errors.purpose}
            hint="Describe the research question, methods, and how record-level data will be secured."
            htmlFor="purpose"
          >
            <textarea
              id="purpose"
              className="input textarea"
              rows={5}
              value={purpose}
              onChange={(event) => setPurpose(event.target.value)}
            />
          </Field>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={agreement}
              onChange={(event) => setAgreement(event.target.checked)}
            />
            <span>
              I agree to the data-use terms, will not attempt re-identification, and understand that access may be
              revoked. <em>Demo request only.</em>
            </span>
          </label>
          {errors.agreement ? <div className="field-error">{errors.agreement}</div> : null}
          <div className="modal-note">
            <AlertTriangle size={15} />
            <span>This request is stored in the browser demo only. It does not create a backend record.</span>
          </div>
        </form>
      </Modal>
    </>
  );
};
