import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ArrowRight,
  Database,
  FileKey2,
  FilterX,
  LayoutGrid,
  List,
  Lock,
  ShieldCheck,
  X,
} from 'lucide-react';
import {
  AccessBadge,
  Badge,
  Button,
  Card,
  DemoBadge,
  DemoNotice,
  EmptyState,
  PageHeader,
  Pagination,
  SearchInput,
  StatCard,
  StatusBadge,
} from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { domains } from '../data/mockData';
import { formatDate, formatNumber } from '../lib/format';
import type { Dataset } from '../types';

const PAGE_SIZE = 6;

const matchesQuality = (dataset: Dataset, minimum: string) => {
  if (minimum === 'all') return true;
  if (dataset.qualityScore == null) return false;
  return dataset.qualityScore >= Number(minimum);
};

export const Repository = () => {
  const { datasets } = useDemo();
  const [searchParams] = useSearchParams();
  const [search, setSearch] = useState(() => searchParams.get('q') ?? '');
  const [domain, setDomain] = useState('all');
  const [access, setAccess] = useState('all');
  const [quality, setQuality] = useState('all');
  const [status, setStatus] = useState('all');
  const [sort, setSort] = useState('updated');
  const [view, setView] = useState<'grid' | 'table'>('grid');
  const [page, setPage] = useState(1);

  useEffect(() => {
    const query = searchParams.get('q') ?? '';
    setSearch(query);
    setPage(1);
  }, [searchParams]);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return datasets
      .filter((dataset) => {
        if (domain !== 'all' && dataset.domain !== domain) return false;
        if (access !== 'all' && dataset.access !== access) return false;
        if (status !== 'all' && dataset.status !== status) return false;
        if (!matchesQuality(dataset, quality)) return false;
        if (!query) return true;
        return [dataset.title, dataset.description, dataset.id, dataset.owner, dataset.domain, ...dataset.tags]
          .join(' ')
          .toLowerCase()
          .includes(query);
      })
      .sort((a, b) => {
        if (sort === 'quality') return (b.qualityScore ?? -1) - (a.qualityScore ?? -1);
        if (sort === 'records') return b.records - a.records;
        if (sort === 'title') return a.title.localeCompare(b.title);
        return b.updatedAt.localeCompare(a.updatedAt);
      });
  }, [access, datasets, domain, quality, search, sort, status]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const visible = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  const reset = () => {
    setSearch('');
    setDomain('all');
    setAccess('all');
    setQuality('all');
    setStatus('all');
    setSort('updated');
    setPage(1);
  };

  const filtersActive =
    search !== '' || domain !== 'all' || access !== 'all' || quality !== 'all' || status !== 'all';

  const totalRecords = datasets.reduce((sum, dataset) => sum + dataset.records, 0);
  const controlled = datasets.filter((dataset) => dataset.access !== 'Open').length;
  const pending = datasets.filter((dataset) => dataset.status === 'Pending review' || dataset.status === 'Changes requested').length;

  return (
    <>
      <PageHeader
        eyebrow="Discovery"
        title="Dataset repository"
        description="Find reusable women's and paediatric health datasets, inspect quality and readiness metadata, and request controlled access."
        actions={
          <Link to="/upload">
            <Button variant="secondary">Contribute dataset</Button>
          </Link>
        }
      />

      <DemoNotice />

      <div className="stats-grid">
        <StatCard label="Datasets indexed" value={datasets.length} hint="Synthetic records only" icon={<Database size={20} />} tone="success" />
        <StatCard label="Records discoverable" value={formatNumber(totalRecords)} hint="Metadata-level counts" icon={<ShieldCheck size={20} />} tone="info" />
        <StatCard label="Controlled or restricted" value={controlled} hint="Require an access request" icon={<Lock size={20} />} tone="warning" />
        <StatCard label="Under governance review" value={pending} hint="Not yet published" icon={<FileKey2 size={20} />} tone="purple" />
      </div>

      <Card>
        <div className="repository-toolbar">
          <SearchInput
            value={search}
            onChange={(value) => { setSearch(value); setPage(1); }}
            placeholder="Search title, tags, owner or description…"
          />
          <div className="toolbar-filters">
            <select className="input input-sm" value={domain} onChange={(event) => { setDomain(event.target.value); setPage(1); }} aria-label="Filter by domain">
              <option value="all">All domains</option>
              {domains.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <select className="input input-sm" value={access} onChange={(event) => { setAccess(event.target.value); setPage(1); }} aria-label="Filter by access">
              <option value="all">All access</option>
              {['Open', 'Controlled', 'Restricted'].map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <select className="input input-sm" value={quality} onChange={(event) => { setQuality(event.target.value); setPage(1); }} aria-label="Filter by minimum quality">
              <option value="all">Any quality</option>
              <option value="90">Quality 90+</option>
              <option value="80">Quality 80+</option>
              <option value="70">Quality 70+</option>
            </select>
            <select className="input input-sm" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }} aria-label="Filter by review status">
              <option value="all">All statuses</option>
              {['Available', 'Processing', 'Pending review', 'Changes requested', 'Failed'].map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
            <select className="input input-sm" value={sort} onChange={(event) => setSort(event.target.value)} aria-label="Sort results">
              <option value="updated">Recently updated</option>
              <option value="quality">Highest quality</option>
              <option value="records">Most records</option>
              <option value="title">Title A–Z</option>
            </select>
            {filtersActive ? (
              <button className="icon-btn" onClick={reset} title="Clear filters" aria-label="Clear filters">
                <FilterX size={16} />
              </button>
            ) : null}
          </div>
          <div className="view-toggle" role="group" aria-label="View mode">
            <button
              className={`icon-btn ${view === 'grid' ? 'icon-btn-active' : ''}`}
              onClick={() => setView('grid')}
              title="Grid view"
              aria-label="Grid view"
            >
              <LayoutGrid size={16} />
            </button>
            <button
              className={`icon-btn ${view === 'table' ? 'icon-btn-active' : ''}`}
              onClick={() => setView('table')}
              title="Table view"
              aria-label="Table view"
            >
              <List size={16} />
            </button>
          </div>
        </div>

        <div className="result-bar">
          <span>{filtered.length} dataset{filtered.length === 1 ? '' : 's'} found</span>
          {search ? (
            <span className="filter-chip">
              “{search}”
              <button onClick={() => setSearch('')} aria-label="Remove search filter"><X size={12} /></button>
            </span>
          ) : null}
          {domain !== 'all' ? (
            <span className="filter-chip">
              {domain}
              <button onClick={() => setDomain('all')} aria-label="Remove domain filter"><X size={12} /></button>
            </span>
          ) : null}
          {access !== 'all' ? (
            <span className="filter-chip">
              {access}
              <button onClick={() => setAccess('all')} aria-label="Remove access filter"><X size={12} /></button>
            </span>
          ) : null}
        </div>

        {visible.length === 0 ? (
          <EmptyState
            title="No datasets match your search"
            description="Try a different keyword, remove filters or browse all available domains."
            action={<Button variant="secondary" onClick={reset}>Clear all filters</Button>}
          />
        ) : view === 'grid' ? (
          <div className="dataset-grid">
            {visible.map((dataset) => (
              <Card key={dataset.id} className="dataset-card">
                <div className="dataset-card-top">
                  <div className="dataset-card-badges">
                    <AccessBadge access={dataset.access} />
                    <StatusBadge status={dataset.status} />
                    {dataset.isLocalPreview ? <DemoBadge label="Preview" /> : null}
                  </div>
                  {dataset.qualityScore != null ? (
                    <span className={`score-pill ${dataset.qualityScore >= 85 ? 'score-good' : dataset.qualityScore >= 70 ? 'score-mid' : 'score-low'}`} title="Data quality score">
                      {dataset.qualityScore}
                    </span>
                  ) : (
                    <span className="muted small">Not assessed</span>
                  )}
                </div>
                <Link to={`/datasets/${dataset.id}`} className="dataset-card-title">{dataset.title}</Link>
                <p className="dataset-card-desc">{dataset.description}</p>
                <div className="dataset-card-tags">
                  <Badge tone="purple">{dataset.domain}</Badge>
                  {dataset.tags.slice(0, 2).map((tag) => <span key={tag} className="tag">#{tag}</span>)}
                </div>
                <div className="dataset-card-stats">
                  <div><span>Records</span><strong>{formatNumber(dataset.records)}</strong></div>
                  <div><span>Columns</span><strong>{dataset.columns}</strong></div>
                  <div><span>Readiness</span><strong>{dataset.readinessScore ?? '—'}</strong></div>
                </div>
                <div className="dataset-card-meta">
                  <span>{dataset.ownerOrganisation}</span>
                  <span>Updated {formatDate(dataset.updatedAt)}</span>
                </div>
                <div className="dataset-card-actions">
                  <Link to={`/datasets/${dataset.id}`}>
                    <Button size="sm" variant="secondary" icon={<ArrowRight size={14} />}>View dataset</Button>
                  </Link>
                  {dataset.access !== 'Open' && dataset.status === 'Available' ? (
                    <Link to={`/datasets/${dataset.id}`} className="inline-link">Request access</Link>
                  ) : dataset.status !== 'Available' ? (
                    <span className="muted small">Access unavailable</span>
                  ) : (
                    <span className="muted small">Open access metadata</span>
                  )}
                </div>
              </Card>
            ))}
          </div>
        ) : (
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
                  <th aria-label="Open" />
                </tr>
              </thead>
              <tbody>
                {visible.map((dataset) => (
                  <tr key={dataset.id}>
                    <td>
                      <Link to={`/datasets/${dataset.id}`} className="table-title">{dataset.title}</Link>
                      <span className="table-sub">{dataset.id} · {dataset.ownerOrganisation}</span>
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
                    <td>{dataset.readinessScore ?? <span className="muted">—</span>}</td>
                    <td><StatusBadge status={dataset.status} /></td>
                    <td className="muted small">{formatDate(dataset.updatedAt)}</td>
                    <td>
                      <Link to={`/datasets/${dataset.id}`} className="icon-btn" aria-label={`View ${dataset.title}`} title="View dataset">
                        <ArrowRight size={15} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {visible.length > 0 ? (
          <Pagination
            page={safePage}
            pageCount={pageCount}
            onPageChange={setPage}
            totalLabel={`Showing ${visible.length} of ${filtered.length}`}
          />
        ) : null}
      </Card>
    </>
  );
};
