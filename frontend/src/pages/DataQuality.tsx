import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  CalendarDays,
  FilterX,
  RefreshCw,
  ScanSearch,
  Search,
  ShieldCheck,
  Users,
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
import { formatDateTime, formatNumber, scoreTone } from '../lib/format';
import type { QualityDimensionKey } from '../types';

const dimensionLabels: Record<QualityDimensionKey, string> = {
  completeness: 'Completeness',
  validity: 'Validity',
  consistency: 'Consistency',
  uniqueness: 'Uniqueness',
  typeCorrectness: 'Type correctness',
};

const severityTone: Record<string, Tone> = { High: 'danger', Medium: 'warning', Low: 'neutral' };

const tooltipStyle = {
  borderRadius: 10,
  border: '1px solid #e2e8e8',
  fontSize: 12,
  boxShadow: '0 8px 24px rgba(15, 43, 42, 0.08)',
};

export const DataQuality = () => {
  const { datasets, qualityReports, notify } = useDemo();
  const scored = datasets.filter((dataset) => qualityReports[dataset.id]);

  const [datasetId, setDatasetId] = useState(scored[0]?.id ?? '');
  const [severity, setSeverity] = useState('all');
  const [dimension, setDimension] = useState('all');
  const [search, setSearch] = useState('');

  const dataset = datasets.find((item) => item.id === datasetId);
  const report = dataset ? qualityReports[dataset.id] : undefined;

  const radarData = report
    ? (Object.keys(report.dimensions) as QualityDimensionKey[]).map((key) => ({
        dimension: dimensionLabels[key],
        score: report.dimensions[key],
        fullMark: 100,
      }))
    : [];

  const filteredIssues = useMemo(() => {
    if (!report) return [];
    const query = search.trim().toLowerCase();
    return report.issues.filter((issue) => {
      if (severity !== 'all' && issue.severity !== severity) return false;
      if (dimension !== 'all' && issue.dimension !== dimension) return false;
      if (!query) return true;
      return `${issue.field} ${issue.description} ${issue.recommendation}`.toLowerCase().includes(query);
    });
  }, [dimension, report, search, severity]);

  const portfolio = scored
    .map((item) => ({
      name: item.id,
      title: item.title,
      score: qualityReports[item.id]?.overall ?? 0,
    }))
    .sort((a, b) => b.score - a.score);

  const highIssues = report?.issues.filter((issue) => issue.severity === 'High').length ?? 0;
  const worstKey = report
    ? (Object.entries(report.dimensions).sort((a, b) => a[1] - b[1])[0][0] as QualityDimensionKey)
    : null;

  return (
    <>
      <PageHeader
        eyebrow="Assessment"
        title="Data quality"
        description="Inspect completeness, validity, consistency, uniqueness and type correctness. Unusual values are flagged, not silently treated as errors."
        actions={
          <Button
            variant="secondary"
            icon={<RefreshCw size={16} />}
            onClick={() =>
              notify(
                'info',
                'Assessment re-run requires the backend',
                'Quality rules will run in the Python ETL service. This demo report is static synthetic output.',
              )
            }
          >
            Re-run assessment
          </Button>
        }
      />

      <DemoNotice text="Quality reports are demo outputs generated from synthetic statistics. Missing values and duplicates are flagged; no records are removed or imputed." />

      <Card className="selector-card">
        <div className="selector-row">
          <div>
            <label className="field-label" htmlFor="quality-dataset">Dataset</label>
            <select
              id="quality-dataset"
              className="input"
              value={datasetId}
              onChange={(event) => setDatasetId(event.target.value)}
            >
              {scored.map((item) => (
                <option key={item.id} value={item.id}>{item.id} · {item.title}</option>
              ))}
            </select>
          </div>
          {dataset ? (
            <div className="selector-meta">
              <Badge tone="neutral">{dataset.domain}</Badge>
              <Badge tone={dataset.access === 'Open' ? 'success' : dataset.access === 'Controlled' ? 'info' : 'danger'}>{dataset.access}</Badge>
              <Link to={`/datasets/${dataset.id}`} className="inline-link">Open dataset <ArrowRight size={13} /></Link>
            </div>
          ) : null}
        </div>
      </Card>

      {!report || !dataset ? (
        <Card>
          <EmptyState
            title="No quality report available"
            description="Datasets are assessed after a successful ETL transform. Select a dataset with a completed assessment."
            action={<Link to="/etl"><Button variant="secondary">Open ETL workspace</Button></Link>}
          />
        </Card>
      ) : (
        <>
          <div className="stats-grid">
            <StatCard label="Overall quality" value={report.overall} hint={`${report.grade} · curated demo score`} icon={<BadgeCheck size={20} />} tone={scoreTone(report.overall) as Tone} />
            <StatCard label="High-severity issues" value={highIssues} hint="Require review before modelling" icon={<AlertTriangle size={20} />} tone={highIssues > 0 ? 'warning' : 'success'} />
            <StatCard label="Records assessed" value={formatNumber(report.sampleSize)} hint="Synthetic records" icon={<Users size={20} />} tone="info" />
            <StatCard label="Weakest dimension" value={worstKey ? dimensionLabels[worstKey] : '—'} hint={worstKey ? `${report.dimensions[worstKey]}% · ${report.grade}` : ''} icon={<ScanSearch size={20} />} tone="purple" />
          </div>

          <div className="grid-2">
            <Card>
              <CardHeader title="Quality dimensions" subtitle="Independent dimension scores" action={<DemoBadge label="Demo report" />} />
              <div className="report-head compact">
                <ScoreRing value={report.overall} size={118} label="overall" />
                <div className="report-meta">
                  <div className="report-meta-row"><CalendarDays size={14} /><span>Assessed {formatDateTime(report.assessedAt)}</span></div>
                  <div className="report-meta-row"><ShieldCheck size={14} /><span>{report.rulesVersion}</span></div>
                  <p>{report.method}</p>
                </div>
              </div>
              <div className="metric-list">
                {(Object.keys(report.dimensions) as QualityDimensionKey[]).map((key) => (
                  <div key={key} className="metric-row">
                    <div className="metric-head">
                      <span>{dimensionLabels[key]}</span>
                      <strong>{report.dimensions[key]}%</strong>
                    </div>
                    <ProgressBar value={report.dimensions[key]} tone={scoreTone(report.dimensions[key]) as Tone} />
                  </div>
                ))}
              </div>
            </Card>

            <Card>
              <CardHeader title="Dimension profile" subtitle="Relative strengths and gaps" />
              <div className="chart-box">
                <ResponsiveContainer width="100%" height={330}>
                  <RadarChart data={radarData} outerRadius="72%">
                    <PolarGrid stroke="#e2e8e8" />
                    <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 11, fill: '#4b5b5a' }} />
                    <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fontSize: 9, fill: '#93a3a2' }} />
                    <Radar name="Score" dataKey="score" stroke="#0f766e" fill="#0f766e" fillOpacity={0.22} strokeWidth={2} />
                    <Tooltip contentStyle={tooltipStyle} />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>

          <Card>
            <CardHeader
              title="Findings"
              subtitle={`${filteredIssues.length} of ${report.issues.length} issues shown`}
              action={<Badge tone={highIssues > 0 ? 'danger' : 'success'}>{highIssues} high severity</Badge>}
            />
            <div className="table-toolbar table-toolbar-wrap">
              <div className="search-input">
                <Search size={16} />
                <input
                  type="search"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search findings or fields…"
                  aria-label="Search quality findings"
                />
              </div>
              <div className="toolbar-filters">
                <select className="input input-sm" value={severity} onChange={(event) => setSeverity(event.target.value)} aria-label="Filter by severity">
                  <option value="all">All severities</option>
                  {['High', 'Medium', 'Low'].map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
                <select className="input input-sm" value={dimension} onChange={(event) => setDimension(event.target.value)} aria-label="Filter by dimension">
                  <option value="all">All dimensions</option>
                  {(Object.keys(dimensionLabels) as QualityDimensionKey[]).map((key) => (
                    <option key={key} value={key}>{dimensionLabels[key]}</option>
                  ))}
                </select>
                {(severity !== 'all' || dimension !== 'all' || search) ? (
                  <button
                    className="icon-btn"
                    onClick={() => { setSeverity('all'); setDimension('all'); setSearch(''); }}
                    title="Clear filters"
                    aria-label="Clear filters"
                  >
                    <FilterX size={16} />
                  </button>
                ) : null}
              </div>
            </div>
            {filteredIssues.length === 0 ? (
              <EmptyState title="No findings match these filters" description="Clear the filters to view all quality findings for this dataset." />
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Severity</th>
                      <th>Dimension</th>
                      <th>Field</th>
                      <th>Finding</th>
                      <th className="num">Records</th>
                      <th>Recommended action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredIssues.map((issue) => (
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
            )}
          </Card>

          <div className="grid-2">
            <Card>
              <CardHeader title="Portfolio quality" subtitle="Overall scores for assessed datasets" />
              <div className="chart-box">
                <ResponsiveContainer width="100%" height={Math.max(220, portfolio.length * 38)}>
                  <BarChart data={portfolio} layout="vertical" margin={{ top: 0, right: 24, left: 8, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#eef2f2" horizontal={false} />
                    <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 10, fill: '#6b7c7b' }} axisLine={false} tickLine={false} />
                    <YAxis type="category" dataKey="name" width={96} tick={{ fontSize: 10, fill: '#4b5b5a' }} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Bar dataKey="score" name="Quality score" radius={[0, 5, 5, 0]} barSize={14}>
                      {portfolio.map((entry) => (
                        <Cell key={entry.name} fill={entry.score >= 85 ? '#0f766e' : entry.score >= 70 ? '#f59e0b' : '#dc2626'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>

            <Card>
              <CardHeader title="Scoring method" subtitle="Planned backend formula — documented, not hidden" />
              <Alert tone="warning" title="Demo scores are curated">
                The displayed overall score comes from synthetic demo metadata. Dimension scores illustrate the report
                structure. The backend engine will compute and version the score below.
              </Alert>
              <div className="formula">
                <code>overall = 0.30·completeness + 0.25·validity + 0.20·consistency + 0.15·uniqueness + 0.10·type_correctness</code>
              </div>
              <ul className="bullet-list">
                <li>Completeness is computed from missing cells per field, not imputed values.</li>
                <li>Validity requires explicit validation rules per field; unusual values alone are not errors.</li>
                <li>Consistency compares category vocabularies and cross-field constraints.</li>
                <li>Uniqueness checks duplicate rows and identifier collisions; neither is auto-deleted.</li>
                <li>Type correctness checks parsed types against the declared schema.</li>
              </ul>
              <Link to="/readiness" className="inline-link">Quality is not the same as AI readiness <ArrowRight size={13} /></Link>
            </Card>
          </div>

          <Card className="callout">
            <div className="callout-icon"><ShieldCheck size={18} /></div>
            <div>
              <strong>What this report does not do</strong>
              <p>
                It does not remove duplicates, impute missing values, correct dates, convert units or exclude outliers.
                Those actions require approved transform rules and are logged as new dataset versions. Statistical
                outliers are surfaced for clinician review, not classified as errors.
              </p>
            </div>
          </Card>
        </>
      )}
    </>
  );
};
