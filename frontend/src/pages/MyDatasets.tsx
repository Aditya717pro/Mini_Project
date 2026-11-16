import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Download,
  Eye,
  FilterX,
  FolderOpen,
  ListFilter,
  UploadCloud,
  Workflow,
} from 'lucide-react';
import {
  AccessBadge,
  Button,
  Card,
  DemoNotice,
  EmptyState,
  PageHeader,
  Pagination,
  SearchInput,
  StatCard,
  StatusBadge,
  Tabs,
} from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { domains } from '../data/mockData';
import { formatDate, formatNumber } from '../lib/format';

const PAGE_SIZE = 7;

export const MyDatasets = () => {
  const { datasets, user, notify } = useDemo();
  const [tab, setTab] = useState('all');
  const [search, setSearch] = useState('');
  const [domain, setDomain] = useState('all');
  const [status, setStatus] = useState('all');
  const [access, setAccess] = useState('all');
  const [page, setPage] = useState(1);

  const mine = datasets.filter((dataset) => dataset.owner === user.name);

  const tabs = [
    { id: 'all', label: 'All', count: mine.length },
    { id: 'published', label: 'Published', count: mine.filter((d) => d.status === 'Available').length },
    { id: 'pipeline', label: 'In pipeline', count: mine.filter((d) => d.status === 'Processing' || d.status === 'Pending review').length },
    { id: 'attention', label: 'Needs attention', count: mine.filter((d) => d.status === 'Changes requested' || d.status === 'Failed').length },
  ];

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return mine
      .filter((dataset) => {
        if (tab === 'published' && dataset.status !== 'Available') return false;
        if (tab === 'pipeline' && !['Processing', 'Pending review'].includes(dataset.status)) return false;
        if (tab === 'attention' && !['Changes requested', 'Failed'].includes(dataset.status)) return false;
        if (domain !== 'all' && dataset.domain !== domain) return false;
        if (status !== 'all' && dataset.status !== status) return false;
        if (access !== 'all' && dataset.access !== access) return false;
        if (!query) return true;
        return [dataset.title, dataset.id, dataset.description, ...dataset.tags]
          .join(' ')
          .toLowerCase()
          .includes(query);
      })
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  }, [access, domain, mine, search, status, tab]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const visible = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  const clearFilters = () => {
    setSearch('');
    setDomain('all');
    setStatus('all');
    setAccess('all');
    setPage(1);
  };

  const filtersActive = search || domain !== 'all' || status !== 'all' || access !== 'all';

  const totalRecords = mine.reduce((sum, dataset) => sum + dataset.records, 0);
  const meanQuality = (() => {
    const scored = mine.filter((dataset) => dataset.qualityScore != null);
    if (scored.length === 0) return 0;
    return Math.round(scored.reduce((sum, dataset) => sum + (dataset.qualityScore ?? 0), 0) / scored.length);
  })();

  return (
    <>
      <PageHeader
        eyebrow="Contributed data"
        title="My datasets"
        description="Manage datasets you own, follow pipeline progress and review quality findings before publication."
        actions={
          <Link to="/upload">
            <Button icon={<UploadCloud size={16} />}>Upload dataset</Button>
          </Link>
        }
      />

      <DemoNotice />

      <div className="stats-grid stats-grid-3">
        <StatCard label="Owned datasets" value={mine.length} hint={`${formatNumber(totalRecords)} synthetic records`} icon={<FolderOpen size={20} />} tone="success" />
        <StatCard label="Awaiting governance" value={mine.filter((d) => d.status === 'Pending review' || d.status === 'Changes requested').length} hint="Cannot be downloaded while pending" icon={<Workflow size={20} />} tone="warning" />
        <StatCard label="Mean quality score" value={meanQuality || '—'} hint="Across datasets with completed assessment" icon={<ListFilter size={20} />} tone="info" />
      </div>

      <Card>
        <div className="table-toolbar">
          <Tabs tabs={tabs} active={tab} onChange={(id) => { setTab(id); setPage(1); }} />
          <div className="toolbar-filters">
            <SearchInput value={search} onChange={(value) => { setSearch(value); setPage(1); }} placeholder="Search my datasets…" />
            <select className="input input-sm" value={domain} onChange={(event) => { setDomain(event.target.value); setPage(1); }} aria-label="Filter by domain">
              <option value="all">All domains</option>
              {domains.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <select className="input input-sm" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }} aria-label="Filter by status">
              <option value="all">All statuses</option>
              {['Available', 'Processing', 'Pending review', 'Changes requested', 'Failed'].map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
            <select className="input input-sm" value={access} onChange={(event) => { setAccess(event.target.value); setPage(1); }} aria-label="Filter by access">
              <option value="all">All access</option>
              {['Open', 'Controlled', 'Restricted'].map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            {filtersActive ? (
              <button className="icon-btn" onClick={clearFilters} title="Clear filters" aria-label="Clear filters">
                <FilterX size={16} />
              </button>
            ) : null}
          </div>
        </div>

        {visible.length === 0 ? (
          <EmptyState
            title="No datasets match these filters"
            description="Adjust the search or filters. If you have not uploaded data yet, start with a synthetic CSV or XLSX file."
            action={<Button variant="secondary" onClick={clearFilters}>Clear filters</Button>}
          />
        ) : (
          <>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Dataset</th>
                    <th>Domain</th>
                    <th className="num">Records</th>
                    <th>Access</th>
                    <th>Quality</th>
                    <th>Readiness</th>
                    <th>Status</th>
                    <th>Updated</th>
                    <th aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {visible.map((dataset) => (
                    <tr key={dataset.id}>
                      <td>
                        <Link to={`/datasets/${dataset.id}`} className="table-title">{dataset.title}</Link>
                        <span className="table-sub">
                          {dataset.id} · v{dataset.version.replace(/^v/, '')} · {dataset.format}
                          {dataset.isLocalPreview ? ' · local preview' : ''}
                        </span>
                      </td>
                      <td className="muted">{dataset.domain}</td>
                      <td className="num">{formatNumber(dataset.records)}</td>
                      <td><AccessBadge access={dataset.access} /></td>
                      <td>
                        {dataset.qualityScore == null ? <span className="muted">—</span> : (
                          <span className={`score-pill ${dataset.qualityScore >= 85 ? 'score-good' : dataset.qualityScore >= 70 ? 'score-mid' : 'score-low'}`}>
                            {dataset.qualityScore}
                          </span>
                        )}
                      </td>
                      <td>
                        {dataset.readinessScore == null ? <span className="muted">—</span> : (
                          <span className="score-plain">{dataset.readinessScore}</span>
                        )}
                      </td>
                      <td><StatusBadge status={dataset.status} /></td>
                      <td className="muted small">{formatDate(dataset.updatedAt)}</td>
                      <td>
                        <div className="row-actions">
                          <Link to={`/datasets/${dataset.id}`} className="icon-btn" title="View details" aria-label={`View ${dataset.title}`}>
                            <Eye size={15} />
                          </Link>
                          <Link to="/etl" className="icon-btn" title="Open ETL workspace" aria-label="Open ETL workspace">
                            <Workflow size={15} />
                          </Link>
                          <button
                            className="icon-btn"
                            disabled
                            title="Secure downloads are not connected yet (Phase 5/11)."
                            aria-label="Download unavailable in demo"
                          >
                            <Download size={15} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination
              page={safePage}
              pageCount={pageCount}
              onPageChange={setPage}
              totalLabel={`${filtered.length} dataset${filtered.length === 1 ? '' : 's'} · showing ${visible.length}`}
            />
          </>
        )}
      </Card>

      <div className="callout-row">
        <Card className="callout">
          <div className="callout-icon"><Download size={18} /></div>
          <div>
            <strong>Downloads are intentionally disabled</strong>
            <p>
              File access will use authenticated, signed download URLs with role checks. This demo exposes metadata
              only. Clicking the disabled icon is not a substitute for the backend access-control implementation.
            </p>
            <button
              className="inline-link button-link"
              onClick={() => notify('info', 'Download not available', 'The demo has no file storage; signed downloads arrive with the FastAPI backend.')}
            >
              Why is this disabled?
            </button>
          </div>
        </Card>
      </div>
    </>
  );
};
