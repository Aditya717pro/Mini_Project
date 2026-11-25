import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowRight, Database, Download, Eye, FileText, FilterX, FlaskConical, GitBranch, History, Layers, X } from 'lucide-react';
import { AccessBadge, Badge, Button, Card, DemoNotice, EmptyState, PageHeader, Pagination, SearchInput, StatCard, StatusBadge } from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { domains } from '../data/mockData';
import { formatDate, formatNumber } from '../lib/format';
import type { Dataset } from '../types';

const PAGE_SIZE = 8;
const getType = (d: Dataset) => (d.origin === 'Synthetic' ? 'Synthetic' : (d.versions?.length ?? 0) > 1 ? 'Processed' : 'Original');

export const Repository = () => {
  const { datasets, requests, role, user, downloadDataset } = useDemo();
  const [searchParams] = useSearchParams();
  const [search, setSearch] = useState(() => searchParams.get('q') ?? '');
  const [domain, setDomain] = useState('all');
  const [type, setType] = useState('all');
  const [format, setFormat] = useState('all');
  const [access, setAccess] = useState('all');
  const [owner, setOwner] = useState('all');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [page, setPage] = useState(1);

  useEffect(() => { setSearch(searchParams.get('q') ?? ''); setPage(1); }, [searchParams]);

  const owners = useMemo(() => Array.from(new Set(datasets.map((d) => d.owner))).sort(), [datasets]);
  const formats = useMemo(() => Array.from(new Set(datasets.map((d) => d.format))).sort(), [datasets]);
  const approvedDatasetIds = useMemo(
    () => new Set(requests.filter((r) => r.direction === 'Outgoing' && r.status === 'Approved').map((r) => r.datasetId)),
    [requests],
  );

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return datasets.filter((d) => {
      if (domain !== 'all' && d.domain !== domain) return false;
      if (type !== 'all' && getType(d) !== type) return false;
      if (format !== 'all' && d.format !== format) return false;
      if (access !== 'all') {
        const isPublic = d.access === 'Open';
        if (access === 'Public' && !isPublic) return false;
        if (access === 'Private' && isPublic) return false;
        if (access !== 'Public' && access !== 'Private' && d.access !== access) return false;
      }
      if (owner !== 'all' && d.owner !== owner) return false;
      const created = (d.createdAt || '').slice(0, 10);
      if (dateFrom && created < dateFrom) return false;
      if (dateTo && created > dateTo) return false;
      if (!q) return true;
      return [d.title, d.description, d.id, d.owner, d.domain, d.format, ...(d.tags ?? [])].join(' ').toLowerCase().includes(q);
    }).sort((a, b) => (b.updatedAt || b.createdAt || '').localeCompare(a.updatedAt || a.createdAt || ''));
  }, [datasets, domain, type, format, access, owner, dateFrom, dateTo, search]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const visible = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);
  const reset = () => { setSearch(''); setDomain('all'); setType('all'); setFormat('all'); setAccess('all'); setOwner('all'); setDateFrom(''); setDateTo(''); setPage(1); };
  const filtersActive = [search, domain !== 'all', type !== 'all', format !== 'all', access !== 'all', owner !== 'all', dateFrom, dateTo].some(Boolean);

  const total = datasets.length;
  const original = datasets.filter((d) => getType(d) === 'Original').length;
  const processed = datasets.filter((d) => getType(d) === 'Processed').length;
  const synthetic = datasets.filter((d) => getType(d) === 'Synthetic').length;
  const recent = datasets.filter((d) => { const t = new Date(d.createdAt || d.updatedAt).getTime(); return Number.isFinite(t) && Date.now() - t < 30 * 24 * 3600 * 1000; }).length;

  return (
    <>
      <PageHeader
        eyebrow="Repository"
        title="My Repository"
        description="Explore original, processed, and synthetic datasets with provenance, access controls, and validation metadata."
      />
      <DemoNotice />

      <div className="stats-grid">
        <StatCard label="Total datasets" value={total} hint="All repository records" icon={<Database size={20} />} tone="info" />
        <StatCard label="Original" value={original} hint="Source datasets" icon={<Database size={20} />} tone="neutral" />
        <StatCard label="Processed" value={processed} hint="Datasets with versions" icon={<Layers size={20} />} tone="warning" />
        <StatCard label="Synthetic" value={synthetic} hint="Generated datasets" icon={<FlaskConical size={20} />} tone="purple" />
        <StatCard label="Recently added" value={recent} hint="Last 30 days" icon={<Database size={20} />} tone="success" />
      </div>

      <Card>
        <div className="repository-toolbar">
          <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Search by name..." />
          <div className="toolbar-filters">
            <select className="input input-sm" value={domain} onChange={(e) => { setDomain(e.target.value); setPage(1); }} aria-label="Filter by disease category"><option value="all">All categories</option>{domains.map((d) => <option key={d} value={d}>{d}</option>)}</select>
            <select className="input input-sm" value={type} onChange={(e) => { setType(e.target.value); setPage(1); }} aria-label="Filter by type"><option value="all">All types</option><option value="Original">Original</option><option value="Processed">Processed</option><option value="Synthetic">Synthetic</option></select>
            <select className="input input-sm" value={format} onChange={(e) => { setFormat(e.target.value); setPage(1); }} aria-label="Filter by format"><option value="all">All formats</option>{formats.map((f) => <option key={f} value={f}>{f}</option>)}</select>
            <select className="input input-sm" value={access} onChange={(e) => { setAccess(e.target.value); setPage(1); }} aria-label="Filter by access"><option value="all">All visibility</option><option value="Public">Public</option><option value="Private">Private</option></select>
            <select className="input input-sm" value={owner} onChange={(e) => { setOwner(e.target.value); setPage(1); }} aria-label="Filter by owner"><option value="all">All owners</option>{owners.map((o) => <option key={o} value={o}>{o}</option>)}</select>
            <input className="input input-sm" type="date" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(1); }} aria-label="Date added from" />
            <input className="input input-sm" type="date" value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(1); }} aria-label="Date added to" />
            {filtersActive ? <button className="icon-btn" onClick={reset} title="Clear filters" aria-label="Clear filters"><FilterX size={16} /></button> : null}
          </div>
        </div>

        <div className="result-bar">
          <span>{filtered.length} dataset{filtered.length === 1 ? '' : 's'} found</span>
          {search ? <span className="filter-chip">“{search}”<button onClick={() => setSearch('')} aria-label="Remove search filter"><X size={12} /></button></span> : null}
          {type !== 'all' ? <span className="filter-chip">{type}<button onClick={() => setType('all')} aria-label="Remove type filter"><X size={12} /></button></span> : null}
        </div>

        {visible.length === 0 ? (
          <EmptyState title="No datasets match" description="Adjust or clear filters to see repository datasets." action={<Button variant="secondary" onClick={reset}>Clear filters</Button>} />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Dataset</th><th>Type</th><th>Category</th><th className="num">Records</th><th>Format</th><th>Date added</th><th>Owner</th><th>Access</th><th>Status</th><th></th></tr></thead>
              <tbody>
                {visible.map((d) => {
                  const t = getType(d);
                  return (
                    <tr key={d.id}>
                      <td>
                        <Link to={`/datasets/${d.id}`} className="table-title">{d.title}</Link>
                        <span className="table-sub">
                          {t === 'Synthetic' ? `Source: ${d.sourceRepositoryDatasetId ? datasets.find((x) => x.id === d.sourceRepositoryDatasetId)?.title ?? 'Repository dataset' : '—'} • Model: ${d.generationModel || '—'} • Job: ${d.generationJobId?.slice(0, 8) || '—'}` : d.description?.slice(0, 80)}
                        </span>
                      </td>
                      <td><Badge tone={t === 'Synthetic' ? 'purple' : t === 'Processed' ? 'warning' : 'neutral'}>{t}</Badge></td>
                      <td className="muted">{d.domain}</td>
                      <td className="num">{formatNumber(d.records)}</td>
                      <td>{d.format}</td>
                      <td className="muted small">{formatDate(d.createdAt || d.updatedAt)}</td>
                      <td className="muted">{d.owner}</td>
                      <td><AccessBadge access={d.access} /></td>
                      <td><StatusBadge status={d.status} /></td>
                      <td>
                        <div className="row-actions">
                          <Link to={`/datasets/${d.id}`} className="icon-btn" aria-label={`View ${d.title}`} title="View details" data-testid={`repo-view-${d.id}`}><ArrowRight size={15} /></Link>
                          <Link to={`/datasets/${d.id}?tab=preview`} className="icon-btn" aria-label={`Preview ${d.title}`} title="Preview" data-testid={`repo-preview-${d.id}`}><Eye size={15} /></Link>
                          <button
                            type="button"
                            className="icon-btn"
                            aria-label={`Download ${d.title}`}
                            title="Download"
                            data-testid={`repo-download-${d.id}`}
                            disabled={!(d.status === 'Available' && (d.access === 'Open' || role === 'Administrator' || d.owner === user.name || approvedDatasetIds.has(d.id)))}
                            onClick={() => void downloadDataset(d)}
                          >
                            <Download size={15} />
                          </button>
                          <Link to={`/datasets/${d.id}?tab=versions`} className="icon-btn" aria-label={`Versions ${d.title}`} title="Versions" data-testid={`repo-versions-${d.id}`}><History size={15} /></Link>
                          <Link to={`/datasets/${d.id}?tab=lineage`} className="icon-btn" aria-label={`Lineage ${d.title}`} title="Lineage" data-testid={`repo-lineage-${d.id}`}><GitBranch size={15} /></Link>
                          <Link to={`/datasets/${d.id}?tab=reports`} className="icon-btn" aria-label={`Reports ${d.title}`} title="Reports" data-testid={`repo-reports-${d.id}`}><FileText size={15} /></Link>
                          <Link to={`/synthmed/generate?datasetId=${encodeURIComponent(d.id)}`} className="icon-btn" aria-label={`Generate synthetic data from ${d.title}`} title="Generate Synthetic Data" data-testid={`repo-generate-${d.id}`}><FlaskConical size={15} /></Link>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {visible.length > 0 ? <Pagination page={safePage} pageCount={pageCount} onPageChange={setPage} totalLabel={`Showing ${visible.length} of ${filtered.length}`} /> : null}
      </Card>
    </>
  );
};
