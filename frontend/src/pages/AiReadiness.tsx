import { useState } from 'react';
import { Link } from 'react-router-dom';
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
  ArrowRight,
  Award,
  BrainCircuit,
  CalendarDays,
  CheckCircle2,
  Flag,
  Gauge,
  Sparkles,
  Target,
  TriangleAlert,
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
  ScoreRing,
  StatCard,
  type Tone,
} from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { formatDateTime, scoreTone } from '../lib/format';

const tooltipStyle = {
  borderRadius: 10,
  border: '1px solid #e2e8e8',
  fontSize: 12,
  boxShadow: '0 8px 24px rgba(15, 43, 42, 0.08)',
};

const verdictTone = (verdict: string): Tone =>
  verdict === 'Ready' ? 'success' : verdict === 'Ready with caveats' ? 'warning' : 'danger';

export const AiReadiness = () => {
  const { datasets, readinessReports } = useDemo();
  const assessed = datasets.filter((dataset) => readinessReports[dataset.id]);
  const [datasetId, setDatasetId] = useState(assessed[0]?.id ?? '');

  const dataset = datasets.find((item) => item.id === datasetId);
  const report = dataset ? readinessReports[dataset.id] : undefined;

  const weakest = report
    ? [...report.categories].sort((a, b) => a.score - b.score)[0]
    : null;

  const chartData = report
    ? report.categories.map((category) => ({
        name: category.label,
        score: category.score,
      }))
    : [];

  const comparison = assessed.slice(0, 8).map((item) => ({
    name: item.id,
    quality: item.qualityScore ?? 0,
    readiness: item.readinessScore ?? 0,
  }));

  return (
    <>
      <PageHeader
        eyebrow="Assessment"
        title="AI readiness"
        description="Evaluate whether a dataset is fit for a declared research task. Readiness is scored independently from data quality."
        actions={
          <Button
            variant="secondary"
            icon={<Sparkles size={16} />}
            onClick={() => {
              const element = document.getElementById('readiness-method');
              element?.scrollIntoView({ behavior: 'smooth' });
            }}
          >
            How scoring works
          </Button>
        }
      />

      <DemoNotice text="Readiness reports use rule-based demo logic (v0.1) tuned to declared tasks. They are not model-performance predictions and claim no regulatory validation." />

      <Card className="selector-card">
        <div className="selector-row">
          <div>
            <label className="field-label" htmlFor="readiness-dataset">Dataset</label>
            <select
              id="readiness-dataset"
              className="input"
              value={datasetId}
              onChange={(event) => setDatasetId(event.target.value)}
            >
              {assessed.map((item) => (
                <option key={item.id} value={item.id}>{item.id} · {item.title}</option>
              ))}
            </select>
          </div>
          {dataset ? (
            <div className="selector-meta">
              <Badge tone="neutral">{dataset.domain}</Badge>
              {report ? <Badge tone={verdictTone(report.verdict)}>{report.verdict}</Badge> : null}
              <Link to={`/datasets/${dataset.id}`} className="inline-link">Open dataset <ArrowRight size={13} /></Link>
            </div>
          ) : null}
        </div>
      </Card>

      {!report || !dataset ? (
        <Card>
          <EmptyState
            title="No readiness report available"
            description="Readiness is assessed after the ETL and quality stages, against a declared research task."
            action={<Link to="/quality"><Button variant="secondary">Open quality workspace</Button></Link>}
          />
        </Card>
      ) : (
        <>
          <div className="stats-grid">
            <StatCard label="Overall readiness" value={report.overall} hint={report.verdict} icon={<BrainCircuit size={20} />} tone={verdictTone(report.verdict)} />
            <StatCard label="Declared task" value={<span className="stat-value-small">{report.task}</span>} hint="Assessment is relative to this task" icon={<Target size={20} />} tone="info" />
            <StatCard label="Weakest category" value={weakest ? weakest.label : '—'} hint={weakest ? `${weakest.score}/100 · weight ${weakest.weight}%` : ''} icon={<Gauge size={20} />} tone="warning" />
            <StatCard label="Quality score" value={dataset.qualityScore ?? '—'} hint="Scored separately from readiness" icon={<Award size={20} />} tone="success" />
          </div>

          <div className="grid-2">
            <Card>
              <CardHeader
                title="Readiness profile"
                subtitle={report.task}
                action={<Badge tone={verdictTone(report.verdict)}>{report.verdict}</Badge>}
              />
              <div className="report-head">
                <ScoreRing value={report.overall} size={132} label="overall" />
                <div className="report-meta">
                  <div className="report-meta-row"><CalendarDays size={14} /><span>Assessed {formatDateTime(report.assessedAt)}</span></div>
                  <div className="report-meta-row"><BrainCircuit size={14} /><span>{report.method}</span></div>
                  <p>
                    The assessment combines data quality with label availability, feature coverage, documentation,
                    missingness, representativeness and task suitability.
                  </p>
                </div>
              </div>
              <div className="metric-list">
                {report.categories.map((category) => (
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

            <div className="stack">
              <Card>
                <CardHeader title="Category comparison" subtitle="Scores out of 100" action={<DemoBadge label="Rule-based" />} />
                <div className="chart-box">
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={chartData} layout="vertical" margin={{ top: 0, right: 24, left: 16, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#eef2f2" horizontal={false} />
                      <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 10, fill: '#6b7c7b' }} axisLine={false} tickLine={false} />
                      <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 10, fill: '#4b5b5a' }} axisLine={false} tickLine={false} />
                      <Tooltip contentStyle={tooltipStyle} />
                      <Bar dataKey="score" name="Readiness" radius={[0, 5, 5, 0]} barSize={13}>
                        {chartData.map((entry) => (
                          <Cell key={entry.name} fill={entry.score >= 85 ? '#0f766e' : entry.score >= 70 ? '#f59e0b' : '#dc2626'} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Card>

              <Card>
                <CardHeader title="Quality vs readiness" subtitle="Two independent assessments" />
                <Alert tone="info">
                  A dataset can have excellent quality and still be unsuitable for a task because labels are missing,
                  documentation is incomplete or coverage is unrepresentative. The reverse can also be true.
                </Alert>
                <div className="compare-row">
                  <div>
                    <span>Data quality</span>
                    <strong>{dataset.qualityScore ?? '—'}</strong>
                  </div>
                  <div className="compare-arrow">≠</div>
                  <div>
                    <span>AI readiness</span>
                    <strong>{report.overall}</strong>
                  </div>
                </div>
              </Card>
            </div>
          </div>

          <div className="grid-2">
            <Card>
              <CardHeader title="Identified limitations" subtitle="Must be addressed or documented before research use" action={<TriangleAlert size={18} className="muted-icon" />} />
              <ul className="bullet-list">
                {report.limitations.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </Card>
            <Card>
              <CardHeader title="Recommendations" subtitle="Suggested next actions" action={<Flag size={18} className="muted-icon" />} />
              <ul className="bullet-list bullet-check">
                {report.recommendations.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </Card>
          </div>

          <Card id="readiness-method">
            <CardHeader title="Readiness method" subtitle="Documented rule-based assessment v0.1" action={<DemoBadge label="Demo method" />} />
            <div className="method-grid">
              <div>
                <h4>Inputs</h4>
                <ul className="bullet-list">
                  <li>Latest quality report and missingness statistics.</li>
                  <li>Feature and label availability from the common schema.</li>
                  <li>Metadata completeness: data dictionary, ethics evidence, consent, collection period.</li>
                  <li>Representativeness analysis using recorded demographics only.</li>
                  <li>The contributor's declared research task.</li>
                </ul>
              </div>
              <div>
                <h4>Rules</h4>
                <ul className="bullet-list">
                  <li>Category scores are weighted (20% data quality and label availability, smaller weights for supporting dimensions).</li>
                  <li>Verdict: ≥80 Ready · 65–79 Ready with caveats · &lt;65 Not ready.</li>
                  <li>No ML model is used. Scores are deterministic and explainable.</li>
                  <li>The architecture is prepared for future validated ML-based evaluation.</li>
                </ul>
              </div>
            </div>
            <Alert tone="warning" title="Not a compliance certificate">
              These scores do not certify clinical safety, regulatory compliance or model performance. They support
              research triage and must be reviewed by a domain expert.
            </Alert>
          </Card>

          <Card>
            <CardHeader title="Portfolio comparison" subtitle="Quality and readiness diverge across datasets" />
            <div className="chart-box">
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={comparison} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eef2f2" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#6b7c7b' }} axisLine={false} tickLine={false} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: '#6b7c7b' }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Bar dataKey="quality" name="Quality" fill="#93c5c0" radius={[4, 4, 0, 0]} barSize={16} />
                  <Bar dataKey="readiness" name="AI readiness" fill="#0f766e" radius={[4, 4, 0, 0]} barSize={16} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card className="callout">
            <div className="callout-icon"><CheckCircle2 size={18} /></div>
            <div>
              <strong>Next step</strong>
              <p>
                Review the limitations with the data owner, agree a label definition and missing-data strategy, and
                record those decisions in the dataset card. A new version triggers a fresh readiness assessment.
              </p>
              <Link to={`/datasets/${dataset.id}`} className="inline-link">Open dataset record <ArrowRight size={13} /></Link>
            </div>
          </Card>
        </>
      )}
    </>
  );
};
