import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, FlaskConical, Plus, RefreshCw } from 'lucide-react';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  Field,
  LoadingState,
  Modal,
  PageHeader,
  Pagination,
  SearchInput,
  type Tone,
} from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { formatDateTime, formatNumber } from '../lib/format';
import type { SynthMedExperimentResponse } from '../types';

const PAGE_SIZE = 10;

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};

const cellText = (value: unknown): string => {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

const experimentModel = (experiment: SynthMedExperimentResponse): string => {
  const metadata = asRecord(experiment.metadata);
  return experiment.configurationSnapshot?.modelName
    ?? cellText(metadata.modelName ?? metadata.model ?? metadata.selectedModel)
    ?? '—';
};

const statusTone = (status: string): Tone => {
  const value = status.toLowerCase();
  if (value.includes('complete') || value.includes('active') || value.includes('ready')) return 'success';
  if (value.includes('fail') || value.includes('error') || value.includes('reject')) return 'danger';
  if (value.includes('run') || value.includes('process') || value.includes('queued')) return 'info';
  if (value.includes('review') || value.includes('pending')) return 'warning';
  return 'neutral';
};

export const SynthMedExperiments = () => {
  const navigate = useNavigate();
  const {
    synthExperiments,
    synthJobs,
    listSynthMedExperiments,
    listSynthMedGenerationJobs,
    createSynthMedExperiment,
  } = useDemo();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const [model, setModel] = useState('');
  const [source, setSource] = useState('');
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState('');
  const [form, setForm] = useState({ name: '', description: '', generationJobId: '', notes: '' });

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [experiments] = await Promise.all([
        listSynthMedExperiments(),
        listSynthMedGenerationJobs().catch(() => synthJobs),
      ]);
      setPage(1);
      return experiments;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unexpected API error');
      return [];
    } finally {
      setLoading(false);
    }
  }, [listSynthMedExperiments, listSynthMedGenerationJobs, synthJobs]);

  useEffect(() => {
    void load();
  }, [load]);

  const statusOptions = useMemo(
    () => Array.from(new Set(synthExperiments.map((experiment) => experiment.status).filter(Boolean))).sort(),
    [synthExperiments],
  );
  const modelOptions = useMemo(
    () => Array.from(new Set(synthExperiments.map(experimentModel).filter((value) => value !== '—'))).sort(),
    [synthExperiments],
  );
  const sourceOptions = useMemo(
    () => Array.from(new Set(synthExperiments.map((experiment) => experiment.sourceDatasetId).filter((value): value is string => !!value))).sort(),
    [synthExperiments],
  );

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return synthExperiments.filter((experiment) => {
      if (needle && ![experiment.name, experiment.id, experiment.notes, experiment.description]
        .some((value) => value.toLowerCase().includes(needle))) return false;
      if (status && experiment.status !== status) return false;
      if (model && experimentModel(experiment) !== model) return false;
      if (source && experiment.sourceDatasetId !== source) return false;
      return true;
    });
  }, [synthExperiments, query, status, model, source]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const visible = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const selectedJob = synthJobs.find((job) => job.id === form.generationJobId);

  const submitCreate = async () => {
    if (!form.name.trim()) {
      setCreateError('Give the experiment a name.');
      return;
    }
    setCreating(true);
    setCreateError('');
    try {
      const experiment = await createSynthMedExperiment({
        name: form.name.trim(),
        description: form.description.trim() || undefined,
        notes: form.notes.trim() || undefined,
        generationJobId: selectedJob?.id ?? null,
        sourceDatasetId: selectedJob?.sourceDatasetId ?? null,
        generatedDatasetId: selectedJob?.generatedDatasetId || null,
      });
      setCreateOpen(false);
      setForm({ name: '', description: '', generationJobId: '', notes: '' });
      navigate(`/synthmed/experiments/${experiment.id}`);
    } catch (reason) {
      setCreateError(reason instanceof Error ? reason.message : 'Unexpected API error');
    } finally {
      setCreating(false);
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="SynthMed"
        title="Experiments"
        description="Group generation jobs, immutable configurations, lineage, privacy and utility results into one record."
        actions={
          <>
            <Button variant="secondary" icon={<RefreshCw size={15} />} onClick={() => void load()}>Refresh</Button>
            <Button icon={<Plus size={15} />} onClick={() => setCreateOpen(true)}>New experiment</Button>
          </>
        }
      />

      {error ? <Alert tone="danger" title="Could not load experiments">{error}</Alert> : null}
      {loading ? (
        <Card><LoadingState label="Loading experiments…" /></Card>
      ) : (
        <Card>
          <CardHeader
            title="Stored experiments"
            subtitle={`${formatNumber(filtered.length)} of ${formatNumber(synthExperiments.length)} experiments shown`}
            action={<Badge tone="purple">SynthMed</Badge>}
          />
          <div className="filter-grid">
            <SearchInput value={query} onChange={(value) => { setQuery(value); setPage(1); }} placeholder="Search name or ID…" />
            <select className="input" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }} aria-label="Filter by status">
              <option value="">All statuses</option>
              {statusOptions.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
            <select className="input" value={model} onChange={(event) => { setModel(event.target.value); setPage(1); }} aria-label="Filter by model">
              <option value="">All models</option>
              {modelOptions.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
            <select className="input" value={source} onChange={(event) => { setSource(event.target.value); setPage(1); }} aria-label="Filter by source dataset">
              <option value="">All source datasets</option>
              {sourceOptions.map((option) => <option key={option} value={option}><code>{option}</code></option>)}
            </select>
          </div>

          {filtered.length === 0 ? (
            <EmptyState
              title={synthExperiments.length === 0 ? 'No experiments recorded' : 'No experiments match the filters'}
              description={synthExperiments.length === 0
                ? 'Create an experiment from a generation job to capture its reproducible configuration and results.'
                : 'Change or clear the filters to see more records.'}
              action={synthExperiments.length === 0 ? (
                <Button icon={<FlaskConical size={15} />} onClick={() => setCreateOpen(true)}>Create experiment</Button>
              ) : undefined}
            />
          ) : (
            <>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Experiment</th><th>Status</th><th>Model</th><th>Source dataset</th><th>Generated dataset</th><th>Created</th><th />
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((experiment) => (
                      <tr key={experiment.id}>
                        <td>
                          <Link to={`/synthmed/experiments/${experiment.id}`} className="inline-link">{experiment.name}</Link>
                          <div className="stat-hint"><code className="code small">{experiment.id.slice(0, 12)}</code></div>
                        </td>
                        <td><Badge tone={statusTone(experiment.status)}>{experiment.status}</Badge></td>
                        <td>{experimentModel(experiment)}</td>
                        <td>{experiment.sourceDatasetId ? <code className="code small">{experiment.sourceDatasetId.slice(0, 12)}</code> : '—'}</td>
                        <td>{experiment.generatedDatasetId ? <code className="code small">{experiment.generatedDatasetId.slice(0, 12)}</code> : '—'}</td>
                        <td>{experiment.createdAt ? formatDateTime(experiment.createdAt) : '—'}</td>
                        <td>
                          <Link to={`/synthmed/experiments/${experiment.id}`}>
                            <Button size="sm" variant="secondary" icon={<ArrowRight size={14} />}>Open</Button>
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination
                page={page}
                pageCount={pageCount}
                onPageChange={setPage}
                totalLabel={`${formatNumber(filtered.length)} experiments`}
              />
            </>
          )}
        </Card>
      )}

      <Modal
        open={createOpen}
        title="Create experiment"
        subtitle="Attach an existing generation job and its immutable configuration snapshot."
        onClose={() => setCreateOpen(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button disabled={creating} onClick={() => void submitCreate()}>{creating ? 'Creating…' : 'Create experiment'}</Button>
          </>
        }
      >
        {createError ? <Alert tone="danger" title="Experiment not created">{createError}</Alert> : null}
        <div className="stack">
          <Field label="Name" htmlFor="experiment-name" required>
            <input
              id="experiment-name"
              className="input"
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              placeholder="e.g. Conditional cohort generation v3"
            />
          </Field>
          <Field label="Generation job" htmlFor="experiment-job" hint="Source and generated dataset IDs are taken from the selected job.">
            <select
              id="experiment-job"
              className="input"
              value={form.generationJobId}
              onChange={(event) => setForm({ ...form, generationJobId: event.target.value })}
            >
              <option value="">No linked job</option>
              {synthJobs.map((job) => (
                <option key={job.id} value={job.id}>
                  {job.modelName} · {job.status} · {job.createdAt ? formatDateTime(job.createdAt) : job.id}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Description" htmlFor="experiment-description">
            <textarea
              id="experiment-description"
              className="input"
              rows={3}
              value={form.description}
              onChange={(event) => setForm({ ...form, description: event.target.value })}
            />
          </Field>
          <Field label="Notes" htmlFor="experiment-notes">
            <textarea
              id="experiment-notes"
              className="input"
              rows={3}
              value={form.notes}
              onChange={(event) => setForm({ ...form, notes: event.target.value })}
            />
          </Field>
          {selectedJob ? (
            <Alert tone="info" title="Linked job selected">
              Source <code className="code small">{selectedJob.sourceDatasetId}</code> · generated{' '}
              <code className="code small">{selectedJob.generatedDatasetId || 'pending'}</code>
            </Alert>
          ) : null}
        </div>
      </Modal>
    </>
  );
};
