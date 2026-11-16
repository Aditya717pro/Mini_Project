import { Link } from 'react-router-dom';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  ArrowRight,
  BadgeCheck,
  BrainCircuit,
  Database,
  FileText,
  KeyRound,
  ShieldAlert,
  TrendingUp,
  UploadCloud,
  Workflow,
} from 'lucide-react';
import {
  Alert,
  AccessBadge,
  Button,
  Card,
  CardHeader,
  DemoBadge,
  DemoNotice,
  PageHeader,
  ProgressBar,
  StatCard,
  StatusBadge,
} from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { activityFeed, domains, uploadsByMonth } from '../data/mockData';
import { formatDate, formatNumber, relativeTime } from '../lib/format';

const CHART_COLORS = ['#0f766e', '#0ea5e9', '#8b5cf6', '#f59e0b', '#ec4899', '#14b8a6'];

const tooltipStyle = {
  borderRadius: 10,
  border: '1px solid #e2e8e8',
  fontSize: 12,
  boxShadow: '0 8px 24px rgba(15, 43, 42, 0.08)',
};

const activityIcon = {
  processing: <Workflow size={15} />,
  upload: <UploadCloud size={15} />,
  request: <KeyRound size={15} />,
  publish: <Database size={15} />,
  quality: <BadgeCheck size={15} />,
};

export const Dashboard = () => {
  const { datasets, jobs, requests } = useDemo();

  const available = datasets.filter((dataset) => dataset.status === 'Available');
  const totalRecords = datasets.reduce((sum, dataset) => sum + dataset.records, 0);
  const pending = datasets.filter(
    (dataset) => dataset.status === 'Pending review' || dataset.status === 'Changes requested',
  );
  const activeJobs = jobs.filter((job) => job.status === 'Running' || job.status === 'Queued');
  const pendingRequests = requests.filter(
    (request) => request.direction === 'Incoming' && request.status === 'Pending',
  );

  const domainData = domains.map((domain) => ({
    name: domain,
    value: datasets.filter((dataset) => dataset.domain === domain).length,
  }));

  const qualityBuckets = [
    { name: 'Excellent', value: datasets.filter((d) => d.qualityScore != null && d.qualityScore >= 90).length },
    { name: 'Good', value: datasets.filter((d) => d.qualityScore != null && d.qualityScore >= 80 && d.qualityScore < 90).length },
    { name: 'Fair', value: datasets.filter((d) => d.qualityScore != null && d.qualityScore < 80).length },
    { name: 'Not assessed', value: datasets.filter((d) => d.qualityScore == null).length },
  ];

  const recent = [...datasets].sort((a, b) => b.createdAt.localeCompare(a.createdAt)).slice(0, 5);
  const activeJobList = jobs
    .filter((job) => job.status !== 'Completed')
    .slice(0, 3);

  return (
    <>
      <PageHeader
        eyebrow="Research overview"
        title="Good morning, Dr. Rahman"
        description="Monitor repository health, review pipeline activity and keep women's and paediatric datasets ready for reuse."
        actions={
          <>
            <Link to="/repository">
              <Button variant="secondary">Browse repository</Button>
            </Link>
            <Link to="/upload">
              <Button icon={<UploadCloud size={16} />}>Upload dataset</Button>
            </Link>
          </>
        }
      />

      <DemoNotice />

      <div className="stats-grid">
        <StatCard
          label="Published datasets"
          value={formatNumber(available.length)}
          hint={`${formatNumber(datasets.length)} total in workspace`}
          icon={<Database size={20} />}
          tone="success"
          trend="+3 this month"
        />
        <StatCard
          label="Records under management"
          value={formatNumber(totalRecords)}
          hint="Synthetic records across all versions"
          icon={<FileText size={20} />}
          tone="info"
          trend="+18.2% QoQ"
        />
        <StatCard
          label="Governance queue"
          value={pending.length}
          hint="Datasets awaiting review"
          icon={<ShieldAlert size={20} />}
          tone={pending.length > 0 ? 'warning' : 'success'}
        />
        <StatCard
          label="Active ETL jobs"
          value={activeJobs.length}
          hint={`${jobs.filter((job) => job.status === 'Review required').length} awaiting mapping review`}
          icon={<Workflow size={20} />}
          tone="purple"
        />
      </div>

      {pendingRequests.length > 0 ? (
        <Alert tone="warning" title={`${pendingRequests.length} access request${pendingRequests.length === 1 ? '' : 's'} need a decision`}>
          <span>
            Review controlled-data applications for {pendingRequests.map((request) => request.datasetId).join(', ')}.{' '}
            <Link to="/access-requests" className="inline-link">
              Open access requests
            </Link>
          </span>
        </Alert>
      ) : null}

      <div className="grid-2">
        <Card>
          <CardHeader
            title="Uploads and publications"
            subtitle="Rolling 12 months · demo activity"
            action={<DemoBadge label="Mock activity" />}
          />
          <div className="chart-box">
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={uploadsByMonth} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                <defs>
                  <linearGradient id="uploadsFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#0f766e" stopOpacity={0.25} />
                    <stop offset="100%" stopColor="#0f766e" stopOpacity={0.02} />
                  </linearGradient>
                  <linearGradient id="publishedFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#0ea5e9" stopOpacity={0.18} />
                    <stop offset="100%" stopColor="#0ea5e9" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#eef2f2" vertical={false} />
                <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#6b7c7b' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: '#6b7c7b' }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={tooltipStyle} />
                <Area type="monotone" dataKey="uploads" stroke="#0f766e" strokeWidth={2} fill="url(#uploadsFill)" name="Uploaded" />
                <Area type="monotone" dataKey="published" stroke="#0ea5e9" strokeWidth={2} fill="url(#publishedFill)" name="Published" />
                <Legend iconType="circle" iconSize={7} wrapperStyle={{ fontSize: 12 }} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <CardHeader title="Datasets by domain" subtitle="Coverage across research areas" />
          <div className="chart-box donut-box">
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie
                  data={domainData}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={58}
                  outerRadius={92}
                  paddingAngle={3}
                  stroke="#fff"
                  strokeWidth={2}
                >
                  {domainData.map((entry, index) => (
                    <Cell key={entry.name} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={tooltipStyle} />
                <Legend layout="vertical" align="right" verticalAlign="middle" iconType="circle" iconSize={7} wrapperStyle={{ fontSize: 11, lineHeight: '20px' }} />
              </PieChart>
            </ResponsiveContainer>
            <div className="donut-center">
              <strong>{datasets.length}</strong>
              <span>datasets</span>
            </div>
          </div>
        </Card>
      </div>

      <div className="grid-2 grid-2-wide">
        <Card>
          <CardHeader
            title="Recent uploads"
            subtitle="Latest synthetic datasets added to the workspace"
            action={<Link to="/datasets" className="inline-link">View all <ArrowRight size={13} /></Link>}
          />
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Dataset</th>
                  <th>Domain</th>
                  <th className="num">Records</th>
                  <th>Access</th>
                  <th>Quality</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((dataset) => (
                  <tr key={dataset.id}>
                    <td>
                      <Link to={`/datasets/${dataset.id}`} className="table-title">
                        {dataset.title}
                      </Link>
                      <span className="table-sub">{dataset.id} · {formatDate(dataset.createdAt)}</span>
                    </td>
                    <td className="muted">{dataset.domain}</td>
                    <td className="num">{formatNumber(dataset.records)}</td>
                    <td><AccessBadge access={dataset.access} /></td>
                    <td>
                      {dataset.qualityScore == null ? (
                        <span className="muted">—</span>
                      ) : (
                        <span className={`score-pill ${dataset.qualityScore >= 85 ? 'score-good' : dataset.qualityScore >= 70 ? 'score-mid' : 'score-low'}`}>
                          {dataset.qualityScore}
                        </span>
                      )}
                    </td>
                    <td><StatusBadge status={dataset.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <div className="stack">
          <Card>
            <CardHeader title="Quality snapshot" subtitle="Latest assessment per dataset" action={<BadgeCheck size={18} className="muted-icon" />} />
            <div className="chart-box compact">
              <ResponsiveContainer width="100%" height={150}>
                <BarChart data={qualityBuckets} layout="vertical" margin={{ top: 0, right: 16, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eef2f2" horizontal={false} />
                  <XAxis type="number" hide />
                  <YAxis type="category" dataKey="name" width={84} tick={{ fontSize: 11, fill: '#4b5b5a' }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Bar dataKey="value" radius={[0, 6, 6, 0]} barSize={16} name="Datasets">
                    {qualityBuckets.map((entry, index) => (
                      <Cell key={entry.name} fill={['#0f766e', '#14b8a6', '#f59e0b', '#cbd5d5'][index]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="mini-footer">
              <Link to="/quality" className="inline-link">Open quality assessment <ArrowRight size={13} /></Link>
            </div>
          </Card>

          <Card>
            <CardHeader title="Activity" subtitle="Workspace audit trail (mock)" />
            <ul className="activity-list">
              {activityFeed.map((item) => (
                <li key={item.id}>
                  <span className={`activity-icon activity-${item.type}`}>{activityIcon[item.type]}</span>
                  <div>
                    <strong>{item.title}</strong>
                    <span>{item.detail}</span>
                    <time>{relativeTime(item.time)}</time>
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>

      <div className="grid-2">
        <Card>
          <CardHeader
            title="Pipeline activity"
            subtitle="Live demo jobs · progress simulated in the browser"
            action={<Link to="/etl" className="inline-link">ETL workspace <ArrowRight size={13} /></Link>}
          />
          <div className="job-mini-list">
            {activeJobList.length === 0 ? (
              <p className="muted">No active jobs. All pipelines have completed.</p>
            ) : (
              activeJobList.map((job) => (
                <div key={job.id} className="job-mini">
                  <div className="job-mini-head">
                    <div>
                      <strong>{job.datasetTitle}</strong>
                      <span>{job.id} · {job.status}</span>
                    </div>
                    <span className="muted">{job.progress}%</span>
                  </div>
                  <ProgressBar value={job.progress} tone={job.status === 'Failed' ? 'danger' : job.status === 'Review required' ? 'warning' : 'info'} />
                </div>
              ))
            )}
          </div>
        </Card>

        <Card>
          <CardHeader title="Quick actions" subtitle="Common research data tasks" />
          <div className="quick-actions">
            <Link to="/upload" className="quick-action">
              <span className="quick-icon tone-success"><UploadCloud size={18} /></span>
              <div>
                <strong>Upload a dataset</strong>
                <span>CSV, XLSX or JSON with validation</span>
              </div>
              <ArrowRight size={15} />
            </Link>
            <Link to="/readiness" className="quick-action">
              <span className="quick-icon tone-purple"><BrainCircuit size={18} /></span>
              <div>
                <strong>Assess AI readiness</strong>
                <span>Task-specific, rule-based review</span>
              </div>
              <ArrowRight size={15} />
            </Link>
            <Link to="/access-requests" className="quick-action">
              <span className="quick-icon tone-warning"><KeyRound size={18} /></span>
              <div>
                <strong>Review access requests</strong>
                <span>{pendingRequests.length} pending decision(s)</span>
              </div>
              <ArrowRight size={15} />
            </Link>
            <Link to="/representativeness" className="quick-action">
              <span className="quick-icon tone-info"><TrendingUp size={18} /></span>
              <div>
                <strong>Check representativeness</strong>
                <span>Women's and paediatric coverage</span>
              </div>
              <ArrowRight size={15} />
            </Link>
          </div>
        </Card>
      </div>
    </>
  );
};
