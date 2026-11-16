import { useMemo, useState } from 'react';
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
  AlertTriangle,
  ArrowRight,
  Baby,
  FilterX,
  HeartPulse,
  MapPin,
  Search,
  Users,
} from 'lucide-react';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  DemoNotice,
  EmptyState,
  PageHeader,
  StatCard,
} from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { formatDate, formatNumber } from '../lib/format';

const tooltipStyle = {
  borderRadius: 10,
  border: '1px solid #e2e8e8',
  fontSize: 12,
  boxShadow: '0 8px 24px rgba(15, 43, 42, 0.08)',
};

const AGE_COLORS = ['#0f766e', '#14919b', '#0ea5e9', '#8b5cf6', '#f59e0b', '#ec4899', '#14b8a6'];

export const Representativeness = () => {
  const { datasets, representativenessReports } = useDemo();
  const analysed = datasets.filter((dataset) => representativenessReports[dataset.id]);
  const [datasetId, setDatasetId] = useState(analysed[0]?.id ?? '');
  const [domainFilter, setDomainFilter] = useState('all');
  const [search, setSearch] = useState('');

  const options = analysed.filter(
    (dataset) => domainFilter === 'all' || dataset.domain === domainFilter,
  );
  const dataset = datasets.find((item) => item.id === datasetId);
  const report = dataset ? representativenessReports[dataset.id] : undefined;

  const missing = useMemo(() => {
    if (!report) return [];
    const query = search.trim().toLowerCase();
    if (!query) return report.missingAttributes;
    return report.missingAttributes.filter((item) =>
      `${item.attribute} ${item.detail} ${item.action}`.toLowerCase().includes(query),
    );
  }, [report, search]);

  const paediatricApplicable = (report?.paediatricGroups.length ?? 0) > 0;
  const geographyCount = report?.geography.length ?? 0;

  const handleDomainChange = (value: string) => {
    setDomainFilter(value);
    const nextOptions = analysed.filter((item) => value === 'all' || item.domain === value);
    if (nextOptions.length > 0) setDatasetId(nextOptions[0].id);
  };

  return (
    <>
      <PageHeader
        eyebrow="Assessment"
        title="Representativeness"
        description="Describe who is in the data using recorded attributes only. Missing demographic characteristics are reported, never inferred."
        actions={
          <Link to="/repository">
            <Button variant="secondary">Browse repository</Button>
          </Link>
        }
      />

      <DemoNotice text="Coverage charts are generated from synthetic demo records. The analysis does not infer ethnicity, geography, pregnancy status or any missing attribute." />

      <Card className="selector-card">
        <div className="selector-row selector-wrap">
          <div>
            <label className="field-label" htmlFor="coverage-domain">Filter by domain</label>
            <select
              id="coverage-domain"
              className="input"
              value={domainFilter}
              onChange={(event) => handleDomainChange(event.target.value)}
            >
              <option value="all">All domains</option>
              {[...new Set(analysed.map((item) => item.domain))].map((domain) => (
                <option key={domain} value={domain}>{domain}</option>
              ))}
            </select>
          </div>
          <div className="grow">
            <label className="field-label" htmlFor="coverage-dataset">Dataset</label>
            <select
              id="coverage-dataset"
              className="input"
              value={datasetId}
              onChange={(event) => setDatasetId(event.target.value)}
            >
              {options.map((item) => (
                <option key={item.id} value={item.id}>{item.id} · {item.title}</option>
              ))}
            </select>
          </div>
          {dataset ? (
            <div className="selector-meta">
              <Badge tone="neutral">{dataset.ageRange}</Badge>
              <Link to={`/datasets/${dataset.id}`} className="inline-link">Open dataset <ArrowRight size={13} /></Link>
            </div>
          ) : null}
        </div>
      </Card>

      {!report || !dataset ? (
        <Card>
          <EmptyState
            title="No representativeness report"
            description="Coverage analysis is generated after processing. Try another domain filter or dataset."
            action={<Button variant="secondary" onClick={() => { setDomainFilter('all'); setDatasetId(analysed[0]?.id ?? ''); }}>Show all datasets</Button>}
          />
        </Card>
      ) : (
        <>
          <div className="stats-grid">
            <StatCard label="Age coverage" value={dataset.ageRange} hint="Declared age range" icon={<Users size={20} />} tone="info" />
            <StatCard label="Recorded locations" value={geographyCount} hint={dataset.geography.join(', ')} icon={<MapPin size={20} />} tone="success" />
            <StatCard label="Paediatric analysis" value={paediatricApplicable ? 'Applicable' : 'Not applicable'} hint={paediatricApplicable ? 'Paediatric bands available' : 'No paediatric groups recorded'} icon={<Baby size={20} />} tone={paediatricApplicable ? 'purple' : 'neutral'} />
            <StatCard label="Unavailable attributes" value={report.missingAttributes.length} hint="Explicitly reported, not inferred" icon={<AlertTriangle size={20} />} tone={report.missingAttributes.length > 0 ? 'warning' : 'success'} />
          </div>

          <Alert tone="info" title="Recorded attributes only">
            These charts describe the synthetic source records. They do not estimate the target population, and missing
            demographic values are not imputed or modelled. Match the dataset to the research question before drawing
            equity conclusions.
          </Alert>

          <div className="grid-2">
            <Card>
              <CardHeader title="Age distribution" subtitle={`${formatNumber(dataset.records)} records · ${dataset.ageRange}`} />
              <div className="chart-box">
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={report.ageBands} margin={{ top: 8, right: 8, left: -14, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#eef2f2" vertical={false} />
                    <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#6b7c7b' }} axisLine={false} tickLine={false} interval={0} angle={-18} textAnchor="end" height={48} />
                    <YAxis tick={{ fontSize: 10, fill: '#6b7c7b' }} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Bar dataKey="value" name="Records" radius={[5, 5, 0, 0]}>
                      {report.ageBands.map((entry, index) => (
                        <Cell key={entry.label} fill={AGE_COLORS[index % AGE_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>

            <Card>
              <CardHeader title="Geographic representation" subtitle={geographyCount > 1 ? 'Recorded countries only' : 'No sub-national detail recorded'} />
              <div className="chart-box">
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={report.geography} layout="vertical" margin={{ top: 8, right: 20, left: 12, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#eef2f2" horizontal={false} />
                    <XAxis type="number" tick={{ fontSize: 10, fill: '#6b7c7b' }} axisLine={false} tickLine={false} />
                    <YAxis type="category" dataKey="label" width={104} tick={{ fontSize: 10, fill: '#4b5b5a' }} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Bar dataKey="value" name="Records" radius={[0, 5, 5, 0]} fill="#0ea5e9" barSize={22} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              {geographyCount < 2 ? (
                <p className="metric-note">Only country-level geography is present. Sub-national representation cannot be assessed.</p>
              ) : null}
            </Card>
          </div>

          <div className="grid-2">
            <Card>
              <CardHeader title="Pregnancy-stage distribution" subtitle="Shown only where recorded at source" action={<HeartPulse size={18} className="muted-icon" />} />
              {report.pregnancyStages.length > 0 ? (
                <div className="chart-box">
                  <ResponsiveContainer width="100%" height={240}>
                    <BarChart data={report.pregnancyStages} margin={{ top: 8, right: 8, left: -14, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#eef2f2" vertical={false} />
                      <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#6b7c7b' }} axisLine={false} tickLine={false} interval={0} />
                      <YAxis tick={{ fontSize: 10, fill: '#6b7c7b' }} axisLine={false} tickLine={false} />
                      <Tooltip contentStyle={tooltipStyle} />
                      <Bar dataKey="value" name="Records" radius={[5, 5, 0, 0]} fill="#8b5cf6" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div className="inline-empty">
                  <AlertTriangle size={18} />
                  Pregnancy stage is not applicable to this cohort or was not recorded in the source file. No values
                  are inferred.
                </div>
              )}
            </Card>

            <Card>
              <CardHeader title="Paediatric age groups" subtitle="Grouped from recorded age" action={<Baby size={18} className="muted-icon" />} />
              {report.paediatricGroups.length > 0 ? (
                <div className="chart-box">
                  <ResponsiveContainer width="100%" height={240}>
                    <BarChart data={report.paediatricGroups} margin={{ top: 8, right: 8, left: -14, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#eef2f2" vertical={false} />
                      <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#6b7c7b' }} axisLine={false} tickLine={false} interval={0} />
                      <YAxis tick={{ fontSize: 10, fill: '#6b7c7b' }} axisLine={false} tickLine={false} />
                      <Tooltip contentStyle={tooltipStyle} />
                      <Bar dataKey="value" name="Records" radius={[5, 5, 0, 0]} fill="#f59e0b" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div className="inline-empty">
                  <Users size={18} />
                  Paediatric age groups are not applicable to this dataset. No group values are inferred.
                </div>
              )}
            </Card>
          </div>

          <Card>
            <CardHeader
              title="Unavailable demographic attributes"
              subtitle="Reported explicitly; never inferred"
              action={<Badge tone="warning">{missing.length} shown</Badge>}
            />
            <div className="table-toolbar">
              <div className="search-input">
                <Search size={16} />
                <input
                  type="search"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search unavailable attributes…"
                  aria-label="Search unavailable attributes"
                />
              </div>
              {search ? (
                <button className="icon-btn" onClick={() => setSearch('')} aria-label="Clear search" title="Clear search">
                  <FilterX size={16} />
                </button>
              ) : null}
            </div>
            {missing.length === 0 ? (
              <EmptyState title="No attributes match the search" description="Clear the search to view all unavailable attributes." />
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr><th>Attribute</th><th>Status</th><th>Action</th></tr>
                  </thead>
                  <tbody>
                    {missing.map((item) => (
                      <tr key={item.attribute}>
                        <td><strong>{item.attribute}</strong></td>
                        <td className="muted cell-wrap">{item.detail}</td>
                        <td className="muted cell-wrap">{item.action}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <div className="grid-2">
            <Card>
              <CardHeader title="Coverage notes" subtitle={`Assessed ${formatDate(report.assessedAt)}`} />
              <ul className="bullet-list">
                {report.coverageNotes.map((note) => <li key={note}>{note}</li>)}
              </ul>
            </Card>
            <Card>
              <CardHeader title="How to read this analysis" subtitle="Limits and appropriate use" />
              <ul className="bullet-list">
                <li>Synthetic records may not match real population distributions.</li>
                <li>Absence of an attribute is a data limitation, not evidence of absence.</li>
                <li>Do not use these percentages as population prevalence estimates.</li>
                <li>Representativeness can change with each dataset version.</li>
                <li>AI-readiness uses this analysis as one input, not as the only criterion.</li>
              </ul>
              <div className="coverage-score">
                <span>Coverage score</span>
                <span className={`score-pill ${(dataset.representativenessScore ?? 0) >= 85 ? 'score-good' : (dataset.representativenessScore ?? 0) >= 70 ? 'score-mid' : 'score-low'}`}>
                  {dataset.representativenessScore ?? '—'}
                </span>
              </div>
            </Card>
          </div>
        </>
      )}
    </>
  );
};
