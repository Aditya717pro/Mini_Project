import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Database, FileUp, FlaskConical, Search, ShieldCheck, Wand2 } from 'lucide-react';
import { Badge, Card, CardHeader, EmptyState, PageHeader, StatCard } from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { formatNumber } from '../lib/format';

export const SynthMed = () => {
  const { datasets, synthGenerated } = useDemo();
  const [search, setSearch] = useState('');

  const sourceDatasets = useMemo(() => {
    const term = search.trim().toLowerCase();
    return datasets
      .filter((dataset) => dataset.status === 'Available')
      .filter((dataset) =>
        !term ||
        dataset.title.toLowerCase().includes(term) ||
        dataset.domain.toLowerCase().includes(term) ||
        dataset.tags.some((tag) => tag.toLowerCase().includes(term)),
      )
      .sort((a, b) => a.title.localeCompare(b.title));
  }, [datasets, search]);

  return (
    <>
      <PageHeader
        eyebrow="Synthetic data"
        title="SynthMed workspace"
        description="Choose a repository dataset or upload a new temporary source for a synthetic cohort. Original source files are never modified."
      />

      <div className="grid-2" data-testid="synthmed-source-methods">
        <Link to="/repository" className="dataset-select-card" data-testid="synthmed-source-repository">
          <span className="dataset-select-head"><strong>Use a repository dataset</strong><Badge tone="info">Existing source</Badge></span>
          <span className="dataset-select-meta">Select a dataset or a specific version from My Repository. Its stored file is reused without modification.</span>
          <span className="dataset-select-cta">Browse My Repository <ArrowRight size={14} /></span>
        </Link>
        <Link to="/synthmed/upload" className="dataset-select-card" data-testid="synthmed-source-upload">
          <span className="dataset-select-head"><strong>Upload a new source</strong><Badge tone="purple">Temporary source</Badge></span>
          <span className="dataset-select-meta">Upload a CSV, XLSX or JSON source for this generation session. Temporary sources are not stored in My Repository.</span>
          <span className="dataset-select-cta"><FileUp size={14} /> Upload source data <ArrowRight size={14} /></span>
        </Link>
      </div>

      <ol className="checklist" data-testid="synthmed-stepper">
        <li><span>1</span><div><strong>Choose repository or uploaded source</strong><p>Select an authorised dataset/version, or upload a temporary source.</p></div></li>
        <li><span>2</span><div><strong>Configure generation</strong><p>Set a genuine CTGAN training job and review the source profile.</p></div></li>
        <li><span>3</span><div><strong>Review and register</strong><p>Preview, download, and optionally add the synthetic output to the repository.</p></div></li>
      </ol>

      <div className="stats-grid">
        <StatCard
          label="Repository sources"
          value={formatNumber(datasets.filter((dataset) => dataset.status === 'Available').length)}
          hint="Eligible source datasets"
          icon={<Database size={20} />}
          tone="info"
        />
        <StatCard
          label="Generated datasets"
          value={formatNumber(synthGenerated.length)}
          hint="Saved in SynthMed"
          icon={<FlaskConical size={20} />}
          tone="success"
        />
        <StatCard
          label="Synthetic records"
          value={formatNumber(synthGenerated.reduce((sum, dataset) => sum + dataset.recordCount, 0))}
          hint="Across generated outputs"
          icon={<Wand2 size={20} />}
          tone="purple"
        />
        <StatCard
          label="Governed outputs"
          value={formatNumber(synthGenerated.filter((dataset) => dataset.repositoryDatasetId).length)}
          hint="Registered in the repository"
          icon={<ShieldCheck size={20} />}
          tone="purple"
        />
      </div>

      <Card>
        <CardHeader
          title="1. Select a source dataset"
          subtitle="Only datasets already available in your repository can be used as SynthMed sources."
          action={<Badge tone="purple">{sourceDatasets.length} available</Badge>}
        />
        <label className="search-field">
          <Search size={16} />
          <input
            className="input"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search repository datasets by title, domain or tag"
            aria-label="Search repository source datasets"
          />
        </label>
        {sourceDatasets.length === 0 ? (
          <EmptyState
            title="No eligible repository datasets"
            description="No available datasets match this search. Add an authorised dataset to My Repository first, then return to SynthMed."
            action={<Link to="/repository"><Badge tone="info">Back to repository</Badge></Link>}
          />
        ) : (
          <div className="dataset-select-grid">
            {sourceDatasets.map((dataset) => (
              <Link
                key={dataset.id}
                to={`/synthmed/generate?datasetId=${encodeURIComponent(dataset.id)}`}
                className="dataset-select-card"
                data-testid={`select-dataset-${dataset.id}`}
              >
                <span className="dataset-select-head">
                  <strong>{dataset.title}</strong>
                  <Badge tone="success">{dataset.status}</Badge>
                </span>
                <span className="dataset-select-meta">
                  <Badge tone="info">{dataset.domain}</Badge>
                  <Badge tone="neutral">{dataset.format}</Badge>
                </span>
                <span className="dataset-select-facts">
                  <div><span>Records</span><strong>{formatNumber(dataset.records)}</strong></div>
                  <div><span>Columns</span><strong>{formatNumber(dataset.columns)}</strong></div>
                </span>
                <span className="dataset-select-cta">Use as source <ArrowRight size={14} /></span>
              </Link>
            ))}
          </div>
        )}
      </Card>
    </>
  );
};
