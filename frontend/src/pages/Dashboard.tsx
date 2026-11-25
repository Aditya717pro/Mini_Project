import { useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  Area,
  AreaChart,
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
  ArrowRight,
  BadgeCheck,
  CheckCircle2,
  Database,
  TrendingUp,
  UploadCloud,
  Wand2,
  Workflow,
} from 'lucide-react';
import { Button, Card, CardHeader, ProgressBar, StatCard } from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { domains } from '../data/mockData';
import { formatDate, formatNumber } from '../lib/format';

const PRIMARY_OPTIONS = [
  {
    testId: 'home-synthetic-card',
    to: '/synthmed',
    icon: Wand2,
    title: 'SYNTHETIC',
    description: 'Generate synthetic medical datasets from new datasets or existing repository datasets.',
    foot: 'Open SynthMed workspace',
  },
  {
    testId: 'home-upload-card',
    to: '/upload',
    icon: UploadCloud,
    title: 'UPLOAD TO REPOSITORY',
    description: 'Upload, extract, transform, validate and store datasets in My Repository.',
    foot: 'Start governed ingestion',
  },
] as const;

const tooltipStyle = {
  borderRadius: 10,
  border: '1px solid var(--border)',
  background: 'var(--surface-2)',
  color: 'var(--text)',
  fontSize: 12,
  boxShadow: 'var(--shadow)',
};

const CHART_BLUE_PALETTE = ['#0b2545', '#123a6b', '#33547d', '#5f82ad', '#9db8d8'];

export const Dashboard = () => {
  const { datasets, jobs } = useDemo();
  const [searchParams] = useSearchParams();
  const showUploadAcknowledgement = searchParams.get('uploaded') === '1';
  const uploadedDatasetId = searchParams.get('datasetId') || '';
  const uploadedJobId = searchParams.get('jobId') || '';
  const uploadedDataset = datasets.find((dataset) => dataset.id === uploadedDatasetId);

  const available = datasets.filter((dataset) => dataset.status === 'Available');
  const totalRecords = datasets.reduce((sum, dataset) => sum + dataset.records, 0);
  const pending = datasets.filter(
    (dataset) => dataset.status === 'Pending review' || dataset.status === 'Changes requested',
  );
  const activeJobs = jobs.filter((job) =>
    ['Queued', 'Profiling', 'Review required', 'Approved', 'Processing', 'Running'].includes(job.status),
  );

  const monthlyData = useMemo(() => {
    return Array.from({ length: 12 }, (_, index) => {
      const point = new Date();
      point.setDate(1);
      point.setMonth(point.getMonth() - (11 - index));
      const key = `${point.getFullYear()}-${String(point.getMonth() + 1).padStart(2, '0')}`;
      return {
        month: point.toLocaleDateString('en-GB', { month: 'short' }),
        uploads: datasets.filter((dataset) => dataset.createdAt?.slice(0, 7) === key).length,
        published: datasets.filter(
          (dataset) => dataset.status === 'Available' && dataset.updatedAt?.slice(0, 7) === key,
        ).length,
      };
    });
  }, [datasets]);

  const domainData = useMemo(() => {
    return domains.map((domain) => ({
      name: domain,
      count: datasets.filter((dataset) => dataset.domain === domain).length,
    }));
  }, [datasets]);

  const qualityBuckets = useMemo(() => [
    { name: 'Excellent', count: datasets.filter((d) => d.qualityScore != null && d.qualityScore >= 90).length },
    { name: 'Good', count: datasets.filter((d) => d.qualityScore != null && d.qualityScore >= 80 && d.qualityScore < 90).length },
    { name: 'Fair', count: datasets.filter((d) => d.qualityScore != null && d.qualityScore < 80).length },
    { name: 'Not assessed', count: datasets.filter((d) => d.qualityScore == null).length },
  ], [datasets]);

  const recentDatasets = useMemo(() => {
    return [...datasets]
      .sort((a, b) => (b.updatedAt || b.createdAt || '').localeCompare(a.updatedAt || a.createdAt || ''))
      .slice(0, 4);
  }, [datasets]);

  return (
    <div className="dashboard-page" style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 24 }}>
      <section className="hero-section" data-testid="home-hero" style={{ width: '100%' }}>
        <div className="hero-eyebrow">MedDataHub · SynthMed</div>
        <h1 className="hero-title">What would you like to do?</h1>
        <p className="hero-subtitle">
          Generate governed synthetic cohorts, or upload and process datasets for My Repository.
        </p>
        <div className="hero-actions" data-testid="home-primary-options" style={{ gridTemplateColumns: 'repeat(2, minmax(0, 1fr))' }}>
          {PRIMARY_OPTIONS.map((option) => {
            const Icon = option.icon;
            return (
              <Link key={option.testId} to={option.to} className="action-card" data-testid={option.testId}>
                <span className="action-icon"><Icon size={20} /></span>
                <h3>{option.title}</h3>
                <p>{option.description}</p>
                <span className="action-card-foot">{option.foot} <ArrowRight size={14} /></span>
              </Link>
            );
          })}
        </div>
      </section>

      {showUploadAcknowledgement ? (
        <Card className="success-panel" data-testid="home-upload-acknowledgement">
          <div className="success-icon"><CheckCircle2 size={26} /></div>
          <div>
            <h2>Dataset uploaded successfully</h2>
            <p>
              {uploadedDataset?.title || 'Your dataset'} completed the real ETL pipeline and is now in My Repository,
              awaiting governance review. Dataset <strong>{uploadedDatasetId}</strong> · ETL job{' '}
              <strong>{uploadedJobId}</strong>.
            </p>
            <div className="success-actions">
              <Link to={`/datasets/${uploadedDatasetId}`}>
                <Button icon={<ArrowRight size={16} />}>View uploaded dataset</Button>
              </Link>
              <Link to="/etl">
                <Button variant="secondary">Open ETL processing</Button>
              </Link>
            </div>
          </div>
        </Card>
      ) : null}

      <div className="stats-grid" style={{ width: '100%' }}>
        <StatCard
          label="Available Datasets"
          value={available.length}
          hint="Ready for research use"
          icon={<Database size={20} />}
          tone="info"
        />
        <StatCard
          label="Records Managed"
          value={formatNumber(totalRecords)}
          hint="Across all cohorts"
          icon={<TrendingUp size={20} />}
          tone="neutral"
        />
        <StatCard
          label="Pending Review"
          value={pending.length}
          hint="Governance intake queue"
          icon={<BadgeCheck size={20} />}
          tone="warning"
        />
        <StatCard
          label="Active ETL Pipelines"
          value={activeJobs.length}
          hint="Running & review-stage jobs"
          icon={<Workflow size={20} />}
          tone="success"
        />
      </div>

      {/* Graphs & Plots row 1: Domain distribution + Monthly trend */}
      <div className="grid-2" style={{ width: '100%' }}>
        <Card>
          <CardHeader
            title="Disease & clinical category coverage"
            subtitle="Distribution of datasets by clinical domain"
            action={<Link to="/repository" className="inline-link">All datasets <ArrowRight size={13} /></Link>}
          />
          <div className="chart-box" style={{ height: 260, width: '100%' }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={domainData} margin={{ top: 12, right: 16, left: -16, bottom: 28 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 11, fill: 'var(--text-2)' }}
                  angle={-15}
                  textAnchor="end"
                  interval={0}
                  axisLine={{ stroke: 'var(--border)' }}
                  tickLine={false}
                />
                <YAxis
                  allowDecimals={false}
                  tick={{ fontSize: 11, fill: 'var(--text-2)' }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar dataKey="count" name="Datasets" radius={[6, 6, 0, 0]}>
                  {domainData.map((entry, index) => (
                    <Cell key={entry.name} fill={CHART_BLUE_PALETTE[index % CHART_BLUE_PALETTE.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Repository ingestion & activity"
            subtitle="Dataset intake and publication velocity over 12 months"
          />
          <div className="chart-box" style={{ height: 260, width: '100%' }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={monthlyData} margin={{ top: 12, right: 16, left: -16, bottom: 8 }}>
                <defs>
                  <linearGradient id="areaGlowUploads" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#0b2545" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#0b2545" stopOpacity={0.0} />
                  </linearGradient>
                  <linearGradient id="areaGlowPublished" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#123a6b" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#123a6b" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="month" tick={{ fontSize: 11, fill: 'var(--text-2)' }} axisLine={{ stroke: 'var(--border)' }} tickLine={false} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: 'var(--text-2)' }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={tooltipStyle} />
                <Area type="monotone" dataKey="uploads" name="Uploads" stroke="#0b2545" strokeWidth={2.5} fill="url(#areaGlowUploads)" />
                <Area type="monotone" dataKey="published" name="Published" stroke="#123a6b" strokeWidth={2} fill="url(#areaGlowPublished)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      {/* Graphs & Plots row 2: Pipeline activity + Quality snapshot & recent datasets */}
      <div className="grid-2" style={{ width: '100%' }}>
        <Card>
          <CardHeader
            title="Pipeline activity"
            subtitle="Active and review-stage jobs from the ETL pipeline"
            action={<Link to="/etl" className="inline-link">ETL workspace <ArrowRight size={13} /></Link>}
          />
          <div className="job-mini-list">
            {activeJobs.length === 0 ? (
              <div style={{ padding: '24px 0', textAlign: 'center', color: 'var(--text-3)' }}>
                <CheckCircle2 size={28} style={{ color: 'var(--accent)', margin: '0 auto 8px', opacity: 0.8 }} />
                <p style={{ margin: 0, fontSize: 13, color: 'var(--text-2)' }}>No active pipeline jobs.</p>
                <span style={{ fontSize: 12 }}>All extract, transform, and profiling jobs are complete.</span>
              </div>
            ) : (
              activeJobs.map((job) => (
                <div key={job.id} className="job-mini">
                  <div className="job-mini-head">
                    <div>
                      <strong>{job.datasetTitle}</strong>
                      <span className="muted small">{job.id} · {job.status}</span>
                    </div>
                    <span className="muted small">{job.progress}%</span>
                  </div>
                  <ProgressBar
                    value={job.progress}
                    tone={job.status === 'Failed' ? 'danger' : job.status === 'Review required' ? 'warning' : 'info'}
                  />
                </div>
              ))
            )}
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Quality assessment snapshot"
            subtitle="Latest quality validation per dataset"
            action={<Link to="/quality" className="inline-link">Quality dashboard <ArrowRight size={13} /></Link>}
          />
          <div className="chart-box compact" style={{ height: 140, width: '100%' }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={qualityBuckets} layout="vertical" margin={{ top: 4, right: 16, left: 4, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="name" width={90} tick={{ fontSize: 11, fill: 'var(--text-2)' }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar dataKey="count" radius={[0, 6, 6, 0]} barSize={16} name="Datasets">
                  {qualityBuckets.map((entry, index) => (
                    <Cell key={entry.name} fill={['#0b2545', '#123a6b', '#33547d', '#64748b'][index]}
 />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <span style={{ fontSize: 12, fontWeight: 650, color: 'var(--text)' }}>Recent Repository Datasets</span>
              <Link to="/repository" className="inline-link" style={{ fontSize: 11 }}>View all</Link>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {recentDatasets.map((d) => (
                <Link
                  key={d.id}
                  to={`/datasets/${d.id}`}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '6px 10px',
                    borderRadius: 8,
                    background: 'var(--surface-2)',
                    textDecoration: 'none',
                    color: 'var(--text)',
                    fontSize: 12,
                  }}
                >
                  <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '70%' }}>
                    <strong>{d.title}</strong>
                  </div>
                  <span className="muted small">{formatDate(d.createdAt || d.updatedAt)}</span>
                </Link>
              ))}
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};
