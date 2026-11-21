import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  ArrowRight,
  Download,
  GitCompare,
  Layers,
  Play,
  RefreshCw,
  ShieldCheck,
  Stethoscope,
} from 'lucide-react';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  InfoRow,
  LoadingState,
  PageHeader,
  StatCard,
  type Tone,
} from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { asConditionSatisfaction, conditionLabel, formatDateTime, formatNumber } from '../lib/format';
import type { SynthMedComparisonDetail } from '../types';

const tooltipStyle = {
  borderRadius: 10,
  border: '1px solid var(--border)',
  fontSize: 12,
  boxShadow: 'var(--shadow)',
};

const percent = (value: number | null | undefined) =>
  value == null ? '—' : `${(value * 100).toFixed(1)}%`;

const similarityTone = (value: number | null | undefined): Tone => {
  if (value == null) return 'neutral';
  if (value >= 0.85) return 'success';
  if (value >= 0.7) return 'warning';
  return 'danger';
};

export const SynthMedComparison = () => {
  const { comparisonId } = useParams();
  const navigate = useNavigate();
  const {
    synthSources,
    synthGenerated,
    synthComparisons,
    listSynthMedComparisons,
    getSynthMedComparison,
    createSynthMedComparison,
    downloadSynthMedComparisonReport,
    notify,
  } = useDemo();

  const [sourceId, setSourceId] = useState('');
  const [generatedId, setGeneratedId] = useState('');
  const [name, setName] = useState('');
  const [detail, setDetail] = useState<SynthMedComparisonDetail | null>(null);
  const [chartColumn, setChartColumn] = useState('');
  const [historyLoading, setHistoryLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [running, setRunning] = useState(false);

  const availableGenerated = useMemo(
    () => synthGenerated.filter((item) => synthSources.some((source) => source.id === item.sourceDatasetId)),
    [synthGenerated, synthSources],
  );

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        await listSynthMedComparisons();
      } catch {
        // Store already reports the error.
      } finally {
        if (!cancelled) setHistoryLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [listSynthMedComparisons]);

  useEffect(() => {
    if (!generatedId && availableGenerated.length) {
      setGeneratedId(availableGenerated[0].id);
    }
  }, [availableGenerated, generatedId]);

  useEffect(() => {
    if (!generatedId) return;
    const selected = availableGenerated.find((item) => item.id === generatedId);
    if (selected && selected.sourceDatasetId !== sourceId) {
      setSourceId(selected.sourceDatasetId);
    }
  }, [availableGenerated, generatedId, sourceId]);

  useEffect(() => {
    if (!comparisonId) {
      setDetail(null);
      setChartColumn('');
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    const load = async () => {
      try {
        const result = await getSynthMedComparison(comparisonId);
        if (!cancelled) {
          setDetail(result);
          setChartColumn(result.charts[0]?.column ?? '');
        }
      } catch {
        // Store already reports the error.
      } finally {
        if (!cancelled) setDetailLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [comparisonId, getSynthMedComparison]);

  const activeChart = useMemo(() => {
    if (!detail) return null;
    return detail.charts.find((chart) => chart.column === chartColumn) ?? detail.charts[0] ?? null;
  }, [chartColumn, detail]);

  const generatedMetadata = detail?.generatedMetadata;
  const comparisonSatisfaction = asConditionSatisfaction(generatedMetadata?.conditionSatisfaction);
  const clinical = detail?.clinical;

  const chartData = useMemo(
    () =>
      (activeChart?.points ?? []).map((point) => ({
        label: point.category ?? point.bucket ?? '',
        original: point.original,
        synthetic: point.synthetic,
      })),
    [activeChart],
  );

  const runComparison = useCallback(async () => {
    if (!sourceId || !generatedId) {
      notify('error', 'Select two datasets', 'Choose an original source and its synthetic output.');
      return;
    }
    setRunning(true);
    try {
      const result = await createSynthMedComparison({
        sourceDatasetId: sourceId,
        generatedDatasetId: generatedId,
        name,
      });
      setDetail(result);
      setChartColumn(result.charts[0]?.column ?? '');
      setName('');
      navigate(`/synthmed/comparison/${result.id}`);
    } catch {
      // Store already reports the error.
    } finally {
      setRunning(false);
    }
  }, [createSynthMedComparison, generatedId, name, navigate, notify, sourceId]);

  const refreshHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      await listSynthMedComparisons();
    } catch {
      // Store already reports the error.
    } finally {
      setHistoryLoading(false);
    }
  }, [listSynthMedComparisons]);

  return (
    <>
      <PageHeader
        eyebrow="SynthMed"
        title="Original vs Synthetic Comparison"
        description="Calculate stored, chart-ready comparisons from an authorised source dataset and its real synthetic output."
        actions={
          <Link to="/synthmed">
            <Button variant="secondary" icon={<ArrowRight size={16} />}>SynthMed overview</Button>
          </Link>
        }
      />

      <Alert tone="warning" title="Interpretation limits">
        These statistics describe observed similarity only. They do not establish clinical validity, anonymity, or fitness
        for a particular research use. Review column coverage and every limitation below before using an output.
      </Alert>

      <Card className="selector-card">
        <CardHeader
          title="New comparison"
          subtitle="Choose a synthetic dataset; its original source is selected automatically from the generation record."
        />
        {availableGenerated.length === 0 ? (
          <EmptyState
            title="No comparable datasets available"
            description="Upload an original dataset and generate a completed synthetic output before running a comparison."
            action={<Link to="/synthmed/generate"><Button icon={<Play size={16} />}>Generate synthetic data</Button></Link>}
          />
        ) : (
          <>
            <div className="selector-row">
              <div>
                <label className="field-label" htmlFor="comparison-source">Original dataset</label>
                <select
                  id="comparison-source"
                  className="input"
                  value={sourceId}
                  onChange={(event) => setSourceId(event.target.value)}
                >
                  {synthSources.map((source) => (
                    <option key={source.id} value={source.id}>{source.datasetName}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="field-label" htmlFor="comparison-generated">Synthetic dataset</label>
                <select
                  id="comparison-generated"
                  className="input"
                  value={generatedId}
                  onChange={(event) => setGeneratedId(event.target.value)}
                >
                  {availableGenerated.map((item) => (
                    <option key={item.id} value={item.id}>{item.datasetName}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="field-label" htmlFor="comparison-name">Comparison name</label>
                <input
                  id="comparison-name"
                  className="input"
                  value={name}
                  placeholder="Optional label"
                  onChange={(event) => setName(event.target.value)}
                />
              </div>
              <Button icon={<GitCompare size={16} />} onClick={() => void runComparison()} disabled={running}>
                {running ? 'Calculating…' : 'Run comparison'}
              </Button>
            </div>
            <p className="field-hint">
              Calculations run against the stored files on the server. No statistics are generated in the browser.
            </p>
          </>
        )}
      </Card>

      <div className="grid-2">
        <Card>
          <CardHeader
            title="Comparison history"
            subtitle="Calculations saved for this account"
            action={
              <Button variant="ghost" size="sm" icon={<RefreshCw size={14} />} onClick={() => void refreshHistory()}>
                Refresh
              </Button>
            }
          />
          {historyLoading ? (
            <LoadingState label="Loading comparisons…" />
          ) : synthComparisons.length === 0 ? (
            <EmptyState
              title="No saved comparisons"
              description="Run your first comparison above. Results, charts and report files are stored with the SynthMed module."
            />
          ) : (
            <div className="metric-list">
              {synthComparisons.map((item) => (
                <div key={item.id} className="metric-row">
                  <div>
                    <button
                      type="button"
                      className="inline-link"
                      onClick={() => navigate(`/synthmed/comparison/${item.id}`)}
                    >
                      {item.name}
                    </button>
                    <div className="stat-hint">
                      {item.generatedDatasetName}
                      {item.generatedMetadata?.model || item.generatedMetadata?.generationMode
                        ? ` · ${item.generatedMetadata?.generationMode ?? 'Unconditional'} · ${item.generatedMetadata?.model ?? '—'}`
                        : ''}
                    </div>
                  </div>
                  <div className="selector-meta">
                    <Badge tone={similarityTone(item.summary.overallSimilarity)}>
                      {percent(item.summary.overallSimilarity)}
                    </Badge>
                    <span className="stat-hint">{formatDateTime(item.createdAt)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <CardHeader
            title="Selected comparison"
            subtitle={detail ? detail.method : 'No comparison selected'}
            action={
              detail?.reportAvailable ? (
                <Button
                  variant="secondary"
                  size="sm"
                  icon={<Download size={14} />}
                  onClick={() => void downloadSynthMedComparisonReport(detail.id)}
                >
                  Report
                </Button>
              ) : null
            }
          />
          {detailLoading ? (
            <LoadingState label="Loading comparison…" />
          ) : !detail ? (
            <EmptyState
              title="Select a saved comparison"
              description="Choose a comparison from history or run a new one to inspect distribution charts and column metrics."
            />
          ) : (
            <>
              <InfoRow label="Original">{detail.sourceDatasetName}</InfoRow>
              <InfoRow label="Synthetic">{detail.generatedDatasetName}</InfoRow>
              <InfoRow label="Generation mode">{generatedMetadata?.generationMode ?? 'Unconditional'}</InfoRow>
              <InfoRow label="Generation profile">
                {clinical?.generationProfile ?? generatedMetadata?.generationProfile ?? 'Standard'}
              </InfoRow>
              <InfoRow label="Selected model">
                {generatedMetadata?.modelName ?? generatedMetadata?.model ?? '—'}
              </InfoRow>
              <InfoRow label="Requested conditions">
                {generatedMetadata?.requestedConditions?.length ? (
                  <ul className="checklist">
                    {generatedMetadata.requestedConditions.map((condition, index) => (
                      <li key={index}><ShieldCheck size={14} />{conditionLabel(condition)}</li>
                    ))}
                  </ul>
                ) : (
                  'None'
                )}
              </InfoRow>
              <InfoRow label="Condition satisfaction">
                {comparisonSatisfaction ? (
                  <Badge
                    tone={comparisonSatisfaction.passed === false ? 'danger' : 'success'}
                    title={comparisonSatisfaction.method}
                  >
                    {comparisonSatisfaction.passed === false ? 'Failed' : 'Passed'}
                    {comparisonSatisfaction.combined
                      ? ` · ${percent(comparisonSatisfaction.combined.satisfactionPercentage)}`
                      : ''}
                  </Badge>
                ) : (
                  'Not applicable'
                )}
              </InfoRow>
              <InfoRow label="Created">{formatDateTime(detail.createdAt)} by {detail.createdBy}</InfoRow>
              <InfoRow label="Report">{detail.reportAvailable ? 'JSON report stored' : 'Not available'}</InfoRow>
            </>
          )}
        </Card>
      </div>

      {detail ? (
        <>
          <div className="stats-grid">
            <StatCard
              label="Overall similarity"
              value={percent(detail.summary.overallSimilarity)}
              hint="Mean of computable column distances"
              icon={<GitCompare size={20} />}
              tone={similarityTone(detail.summary.overallSimilarity)}
            />
            <StatCard
              label="Columns compared"
              value={formatNumber(detail.summary.sharedColumns)}
              hint={`${detail.summary.onlySourceColumns.length} original-only · ${detail.summary.onlySyntheticColumns.length} synthetic-only`}
              icon={<Layers size={20} />}
              tone="info"
            />
            <StatCard
              label="Record count delta"
              value={formatNumber(detail.summary.rowDifference)}
              hint={`${formatNumber(detail.summary.sourceRows)} → ${formatNumber(detail.summary.syntheticRows)} rows`}
              icon={<Play size={20} />}
              tone="purple"
            />
            <StatCard
              label="Missingness delta"
              value={detail.summary.missingnessDeltaPercentage == null
                ? '—'
                : `${detail.summary.missingnessDeltaPercentage.toFixed(2)}%`}
              hint="Mean absolute percentage-point difference"
              icon={<ShieldCheck size={20} />}
              tone="warning"
            />
          </div>

          {clinical ? (
            <Card>
              <CardHeader
                title="Clinical comparison"
                subtitle="Original and synthetic records screened with the same documented references."
                action={<Badge tone={clinical.generationProfile === 'Standard' ? 'neutral' : 'purple'}>
                  {clinical.generationProfile}
                </Badge>}
              />
              <div className="grid-2 grid-2-wide">
                <div>
                  <h4>Original records</h4>
                  <div className="info-list">
                    <InfoRow label="Measurements">
                      {formatNumber(clinical.sourceMedicalProfile.clinicalMeasurementColumns.length)}
                    </InfoRow>
                    <InfoRow label="Records checked">
                      {formatNumber(clinical.sourceValidation.totalRecords ?? 0)}
                    </InfoRow>
                    <InfoRow label="Warnings">
                      {formatNumber(clinical.sourceValidation.warnings?.length ?? 0)}
                    </InfoRow>
                  </div>
                </div>
                <div>
                  <h4>Synthetic records</h4>
                  <div className="info-list">
                    <InfoRow label="Measurements">
                      {formatNumber(clinical.syntheticMedicalProfile.clinicalMeasurementColumns.length)}
                    </InfoRow>
                    <InfoRow label="Records checked">
                      {formatNumber(clinical.syntheticValidation.totalRecords ?? 0)}
                    </InfoRow>
                    <InfoRow label="Warnings">
                      {formatNumber(clinical.syntheticValidation.warnings?.length ?? 0)}
                    </InfoRow>
                  </div>
                </div>
              </div>
              {clinical.sourceValidation.classificationCounts ||
              clinical.syntheticValidation.classificationCounts ? (
                <div className="table-wrap">
                  <table className="table table-compact">
                    <thead>
                      <tr>
                        <th>Classification</th>
                        <th className="num">Original</th>
                        <th className="num">Synthetic</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Array.from(
                        new Set([
                          ...Object.keys(clinical.sourceValidation.classificationCounts ?? {}),
                          ...Object.keys(clinical.syntheticValidation.classificationCounts ?? {}),
                        ]),
                      ).map((label) => (
                        <tr key={label}>
                          <td>{label.replace(/_/g, ' ')}</td>
                          <td className="num">
                            {formatNumber(clinical.sourceValidation.classificationCounts?.[label] ?? 0)}
                          </td>
                          <td className="num">
                            {formatNumber(clinical.syntheticValidation.classificationCounts?.[label] ?? 0)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
              <InfoRow label="Approved output schema">
                <Badge tone={clinical.schemaValidation.passed ? 'success' : 'danger'}>
                  {clinical.schemaValidation.passed ? 'Passed' : 'Failed'}
                </Badge>
              </InfoRow>
              <InfoRow label="Rejection sampling">
                {clinical.rejectionSampling.attempts ?? '—'} / {clinical.rejectionSampling.maxAttempts ?? '—'} attempts ·{' '}
                {formatNumber(clinical.rejectionSampling.rejectedRecords ?? 0)} rejected
              </InfoRow>
              {clinical.limitations.length ? (
                <ul className="checklist">
                  {clinical.limitations.map((limitation) => (
                    <li key={limitation}><Stethoscope size={14} />{limitation}</li>
                  ))}
                </ul>
              ) : null}
            </Card>
          ) : null}

          <Card>
            <CardHeader
              title="Distribution comparison"
              subtitle={activeChart ? activeChart.title : 'No chartable shared columns'}
              action={
                detail.charts.length > 1 ? (
                  <select
                    className="input input-sm"
                    value={chartColumn}
                    onChange={(event) => setChartColumn(event.target.value)}
                    aria-label="Choose chart column"
                  >
                    {detail.charts.map((chart) => (
                      <option key={chart.column} value={chart.column}>{chart.column}</option>
                    ))}
                  </select>
                ) : null
              }
            />
            {activeChart && chartData.length ? (
              <div className="chart-box">
                <ResponsiveContainer width="100%" height={340}>
                  <BarChart data={chartData} margin={{ top: 12, right: 16, bottom: 12, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="label" tick={{ fontSize: 10, fill: 'var(--text-2)' }} interval={0} angle={-15} />
                    <YAxis tick={{ fontSize: 11, fill: 'var(--text-2)' }} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="original" name="Original" fill="var(--primary)" radius={[3, 3, 0, 0]} />
                    <Bar dataKey="synthetic" name="Synthetic" fill="var(--success)" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <EmptyState
                title="No distribution chart available"
                description="Shared columns had no comparable values, or their recorded kinds differ. Inspect the table below."
              />
            )}
          </Card>

          <Card>
            <CardHeader
              title="Column-level metrics"
              subtitle="Distances are calculated on stored values; select a column name to view its chart where available."
            />
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Column</th>
                    <th>Kind</th>
                    <th>Distance metric</th>
                    <th className="num">Similarity</th>
                    <th className="num">Missing original</th>
                    <th className="num">Missing synthetic</th>
                    <th className="num">Unique original</th>
                    <th className="num">Unique synthetic</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.columns.map((column) => (
                    <tr key={column.name}>
                      <td>
                        <button type="button" className="inline-link" onClick={() => setChartColumn(column.name)}>
                          {column.name}
                        </button>
                      </td>
                      <td>{column.sourceKind}{column.sourceKind !== column.syntheticKind ? ` → ${column.syntheticKind}` : ''}</td>
                      <td>{column.metric}</td>
                      <td className="num">
                        <Badge tone={similarityTone(column.similarity)}>{percent(column.similarity)}</Badge>
                      </td>
                      <td className="num">{column.sourceMissingPercentage.toFixed(2)}%</td>
                      <td className="num">{column.syntheticMissingPercentage.toFixed(2)}%</td>
                      <td className="num">{formatNumber(column.sourceUniqueCount)}</td>
                      <td className="num">{formatNumber(column.syntheticUniqueCount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <div className="grid-2">
            <Card>
              <CardHeader title="Schema coverage" subtitle="Columns present in only one dataset" />
              <InfoRow label="Only in original">
                {detail.summary.onlySourceColumns.length ? detail.summary.onlySourceColumns.join(', ') : 'None'}
              </InfoRow>
              <InfoRow label="Only in synthetic">
                {detail.summary.onlySyntheticColumns.length ? detail.summary.onlySyntheticColumns.join(', ') : 'None'}
              </InfoRow>
              <InfoRow label="Numeric similarity">{percent(detail.summary.numericSimilarity)}</InfoRow>
              <InfoRow label="Categorical similarity">{percent(detail.summary.categoricalSimilarity)}</InfoRow>
            </Card>
            <Card>
              <CardHeader title="Method & limitations" subtitle="Read before interpreting the scores" />
              <p className="muted">{detail.method}</p>
              <ul className="activity-list">
                {detail.limitations.map((item) => (
                  <li key={item}><span>{item}</span></li>
                ))}
              </ul>
            </Card>
          </div>
        </>
      ) : null}
    </>
  );
};
