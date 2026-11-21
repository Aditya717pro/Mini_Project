import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Download, ShieldCheck, Wand2 } from 'lucide-react';
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
  ScoreRing,
} from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { asConditionSatisfaction, conditionLabel, formatDateTime, formatNumber } from '../lib/format';
import type { SynthMedEvaluationReport, SynthMedGeneratedEvaluationSummary } from '../types';

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' ? (value as Record<string, unknown>) : {};

const asRows = (value: unknown): Record<string, unknown>[] =>
  Array.isArray(value) ? (value.filter((row) => row && typeof row === 'object') as Record<string, unknown>[]) : [];

const asStrings = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];

const cellText = (value: unknown): string => {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

const percent = (value: number | null | undefined): string =>
  value == null ? '—' : `${(value * 100).toFixed(1)}%`;

const ObjectTable = ({ rows }: { rows: Record<string, unknown>[] }) => {
  const columns = rows.length > 0 ? Object.keys(rows[0]) : [];
  if (columns.length === 0) return <p className="muted small">No detail rows available.</p>;
  return (
    <div className="table-wrap">
      <table className="table table-compact">
        <thead>
          <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {columns.map((column) => <td key={column}>{cellText(row[column])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

const ReportDownload = ({
  generatedId,
  reportType,
  onDownload,
}: {
  generatedId: string;
  reportType: string;
  onDownload: (generatedId: string, reportType: string) => Promise<void>;
}) => (
  <Button
    variant="secondary"
    size="sm"
    icon={<Download size={14} />}
    onClick={() => void onDownload(generatedId, reportType)}
  >
    Download JSON
  </Button>
);

export const SynthMedEvaluation = () => {
  const {
    synthGenerated,
    getSynthMedQualityReport,
    getSynthMedPrivacyReport,
    getSynthMedGeneratedEvaluation,
    getSynthMedGeneratedConditions,
    downloadSynthMedReport,
  } = useDemo();
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get('dataset') ?? '';
  const selectedId = synthGenerated.some((dataset) => dataset.id === requested)
    ? requested
    : (synthGenerated[0]?.id ?? '');

  const [quality, setQuality] = useState<SynthMedEvaluationReport | null>(null);
  const [privacy, setPrivacy] = useState<SynthMedEvaluationReport | null>(null);
  const [conditions, setConditions] = useState<SynthMedEvaluationReport | null>(null);
  const [summary, setSummary] = useState<SynthMedGeneratedEvaluationSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    setError('');
    if (!selectedId) {
      setQuality(null);
      setPrivacy(null);
      setConditions(null);
      setSummary(null);
      return;
    }
    setLoading(true);
    void (async () => {
      try {
        const [qualityReport, privacyReport, evaluationSummary] = await Promise.all([
          getSynthMedQualityReport(selectedId).catch(() => null),
          getSynthMedPrivacyReport(selectedId).catch(() => null),
          getSynthMedGeneratedEvaluation(selectedId).catch(() => null),
        ]);
        if (!active) return;
        setQuality(qualityReport);
        setPrivacy(privacyReport);
        setSummary(evaluationSummary);
        if (!qualityReport && !privacyReport && !evaluationSummary?.availableReports.length) {
          setError('No evaluation reports are available for this dataset.');
        }
        if (evaluationSummary?.availableReports.includes('conditions')) {
          const conditionReport = await getSynthMedGeneratedConditions(selectedId).catch(() => null);
          if (active) setConditions(conditionReport);
        } else {
          setConditions(null);
        }
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [
    selectedId,
    getSynthMedQualityReport,
    getSynthMedPrivacyReport,
    getSynthMedGeneratedEvaluation,
    getSynthMedGeneratedConditions,
  ]);

  const qualityData = quality ? asRecord(quality.report) : null;
  const privacyData = privacy ? asRecord(privacy.report) : null;
  const conditionData = conditions ? asConditionSatisfaction(conditions.report) : null;
  const conditionPassed = conditionData?.passed ?? conditionData?.allConditionsSatisfied;
  const selectedDataset = synthGenerated.find((dataset) => dataset.id === selectedId);

  return (
    <>
      <PageHeader
        eyebrow="Synthetic data"
        title="Quality & Privacy Evaluation"
        description="Review SDMetrics utility results and privacy-risk screening for each generated dataset."
        actions={
          <Link to="/synthmed/generated">
            <Button variant="secondary">Generated datasets</Button>
          </Link>
        }
      />

      <Alert tone="warning" title="Interpret reports carefully">
        Statistical fidelity and heuristic privacy checks do not prove clinical validity, safety or anonymity. No
        differential privacy mechanism is applied.
      </Alert>

      {synthGenerated.length === 0 ? (
        <Card>
          <EmptyState
            title="No datasets to evaluate"
            description="Generate a synthetic dataset first; quality and privacy reports are produced by the generation job."
            action={
              <Link to="/synthmed/generate">
                <Button icon={<Wand2 size={15} />}>Generate data</Button>
              </Link>
            }
          />
        </Card>
      ) : (
        <>
          <Card>
            <CardHeader
              title="Dataset under review"
              subtitle="Reports are generated by SDMetrics and the SynthMed privacy checker."
              action={<Badge tone="purple">{synthGenerated.length} available</Badge>}
            />
            <div className="field">
              <label className="field-label" htmlFor="synthmed-evaluation-dataset">Generated dataset</label>
              <select
                id="synthmed-evaluation-dataset"
                className="input"
                value={selectedId}
                onChange={(event) => setSearchParams({ dataset: event.target.value })}
              >
                {synthGenerated.map((dataset) => (
                  <option key={dataset.id} value={dataset.id}>
                    {dataset.datasetName} · {formatDateTime(dataset.generationDate)}
                  </option>
                ))}
              </select>
            </div>
            {selectedDataset ? (
              <div className="profile-summary">
                <div><span>Records</span><strong>{selectedDataset.recordCount}</strong></div>
                <div><span>Columns</span><strong>{selectedDataset.columnCount}</strong></div>
                <div><span>Mode</span><strong>{summary?.generationMode ?? selectedDataset.generationMode ?? '—'}</strong></div>
                <div><span>Model</span><strong>{summary?.selectedModel ?? selectedDataset.selectedModel ?? '—'}</strong></div>
                <div><span>Method</span><strong>{selectedDataset.generationMethod}</strong></div>
                <div><span>Format</span><strong>{selectedDataset.fileFormat}</strong></div>
                <div><span>Status</span><strong>{selectedDataset.status}</strong></div>
              </div>
            ) : null}
          </Card>

          {loading ? <Card><LoadingState label="Loading evaluation reports…" /></Card> : null}
          {error ? <Alert tone="warning" title="Evaluation unavailable">{error}</Alert> : null}

          {conditions ? (
            <Card>
              <CardHeader
                title="Condition satisfaction"
                subtitle={conditions.method}
                action={
                  <ReportDownload
                    generatedId={conditions.generatedDatasetId}
                    reportType="conditions"
                    onDownload={downloadSynthMedReport}
                  />
                }
              />
              {conditionData ? (
                <>
                  <div className="info-list">
                    <InfoRow label="Generation mode">{summary?.generationMode ?? conditions.generationMode ?? '—'}</InfoRow>
                    <InfoRow label="Selected model">{summary?.selectedModel ?? conditions.selectedModel ?? '—'}</InfoRow>
                    <InfoRow label="Result">
                      <Badge tone={conditionPassed === false ? 'danger' : 'success'}>
                        {conditionPassed === false ? 'Not satisfied' : 'Satisfied'}
                      </Badge>
                    </InfoRow>
                    <InfoRow label="Generated records">
                      {conditionData.combined ? formatNumber(conditionData.combined.totalGeneratedRecords) : '—'}
                    </InfoRow>
                    <InfoRow label="Satisfying records">
                      {conditionData.combined ? formatNumber(conditionData.combined.satisfyingRecords) : '—'}
                    </InfoRow>
                    <InfoRow label="Satisfaction">
                      {conditionData.combined ? `${conditionData.combined.satisfactionPercentage.toFixed(1)}%` : '—'}
                    </InfoRow>
                  </div>
                  {conditionData.requestedConditions?.length ? (
                    <>
                      <h3 className="section-title">Requested conditions</h3>
                      <ul className="checklist">
                        {conditionData.requestedConditions.map((condition, index) => (
                          <li key={index}><ShieldCheck size={14} />{conditionLabel(condition)}</li>
                        ))}
                      </ul>
                    </>
                  ) : null}
                  {conditionData.conditions?.length ? (
                    <>
                      <h3 className="section-title">Per-condition results</h3>
                      <div className="table-wrap">
                        <table className="table table-compact">
                          <thead>
                            <tr>
                              <th>Condition</th>
                              <th className="num">Requested</th>
                              <th className="num">Satisfying</th>
                              <th className="num">Satisfaction</th>
                            </tr>
                          </thead>
                          <tbody>
                            {conditionData.conditions.map((result) => (
                              <tr key={result.index}>
                                <td>{conditionLabel({ column: result.column, operator: result.operator, value: result.requestedValue })}</td>
                                <td className="num">{formatNumber(result.requestedRows)}</td>
                                <td className="num">{formatNumber(result.satisfyingRecords)}</td>
                                <td className="num">{result.satisfactionPercentage.toFixed(1)}%</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </>
                  ) : null}
                  {conditionData.cohorts?.length ? (
                    <>
                      <h3 className="section-title">Cohorts</h3>
                      <ul className="checklist">
                        {conditionData.cohorts.map((cohort) => (
                          <li key={cohort.index}>
                            <ShieldCheck size={14} />
                            {cohort.conditions.map((item) => conditionLabel(item)).join(' AND ')}:{' '}
                            {formatNumber(cohort.satisfyingRecords)}/{formatNumber(cohort.requestedRows)} rows ·{' '}
                            {cohort.passed ? 'Passed' : 'Failed'}
                          </li>
                        ))}
                      </ul>
                    </>
                  ) : null}
                  {conditionData.limitations?.length ? (
                    <ul className="checklist">
                      {conditionData.limitations.map((item, index) => (
                        <li key={index}><ShieldCheck size={14} />{item}</li>
                      ))}
                    </ul>
                  ) : null}
                </>
              ) : (
                <Alert tone="warning" title="Condition report could not be parsed">
                  The stored report is available for download but its structure is not recognised.
                </Alert>
              )}
            </Card>
          ) : null}

          {quality && qualityData ? (
            <div className="grid-2 grid-2-wide">
              <Card>
                <CardHeader
                  title="Quality report"
                  subtitle={quality.method}
                  action={<ReportDownload generatedId={quality.generatedDatasetId} reportType="quality" onDownload={downloadSynthMedReport} />}
                />
                <div className="score-layout">
                  <ScoreRing value={Math.round((quality.score ?? 0) * 100)} label="quality" sublabel="score" />
                  <div className="info-list">
                    <InfoRow label="Overall score">{percent(quality.score)}</InfoRow>
                    <InfoRow label="SDMetrics quality">{percent(qualityData.overallQualityScore as number)}</InfoRow>
                    <InfoRow label="Diagnostic score">{percent(qualityData.diagnosticScore as number)}</InfoRow>
                    <InfoRow label="Created">{formatDateTime(quality.createdAt)}</InfoRow>
                  </div>
                </div>
                <h3 className="section-title">Property scores</h3>
                <div className="chip-grid">
                  {Object.entries(asRecord(qualityData.propertyScores)).map(([name, value]) => (
                    <span className="chip" key={name}>{name}: {percent(value as number)}</span>
                  ))}
                  {Object.entries(asRecord(qualityData.diagnosticProperties)).map(([name, value]) => (
                    <span className="chip" key={name}>{name}: {percent(value as number)}</span>
                  ))}
                </div>
                <h3 className="section-title">Column-level similarity</h3>
                <ObjectTable rows={asRows(qualityData.columnLevel)} />
                <h3 className="section-title">Validity diagnostics</h3>
                <ObjectTable rows={asRows(qualityData.diagnostics)} />
                <ul className="checklist">
                  {asStrings(qualityData.limitations).map((item, index) => (
                    <li key={index}><ShieldCheck size={14} />{item}</li>
                  ))}
                </ul>
              </Card>

              <Card>
                <CardHeader
                  title="Privacy report"
                  subtitle={privacy?.method ?? 'Privacy-risk screening'}
                  action={privacy ? (
                    <ReportDownload
                      generatedId={privacy.generatedDatasetId}
                      reportType="privacy"
                      onDownload={downloadSynthMedReport}
                    />
                  ) : undefined}
                />
                {privacy && privacyData ? (
                  <>
                    {privacy.score != null ? (
                      <div className="score-layout">
                        <ScoreRing value={Math.round(privacy.score * 100)} label="new rows" sublabel="score" />
                      </div>
                    ) : null}
                    <div className="info-list">
                      <InfoRow label="Exact overlaps">{String(privacyData.exactOverlapRecords ?? '—')}</InfoRow>
                      <InfoRow label="Overlap percentage">{String(privacyData.exactOverlapPercentage ?? '—')}%</InfoRow>
                      <InfoRow label="Synthetic duplicates">{String(privacyData.syntheticDuplicateRecords ?? '—')}</InfoRow>
                      <InfoRow label="Source duplicates">{String(privacyData.realDuplicateRecords ?? '—')}</InfoRow>
                      <InfoRow label="NewRowSynthesis">{percent(privacyData.newRowSynthesisScore as number)}</InfoRow>
                      <InfoRow label="Created">{formatDateTime(privacy.createdAt)}</InfoRow>
                    </div>
                    <h3 className="section-title">Nearest neighbour</h3>
                    <div className="info-list">
                      {Object.entries(asRecord(privacyData.nearestNeighbourDistance)).map(([name, value]) => (
                        <InfoRow key={name} label={name}>{cellText(value)}</InfoRow>
                      ))}
                    </div>
                    <h3 className="section-title">Warnings</h3>
                    <ul className="checklist">
                      {asStrings(privacyData.warnings).map((item, index) => (
                        <li key={index}><ShieldCheck size={14} />{item}</li>
                      ))}
                    </ul>
                    <h3 className="section-title">Limitations</h3>
                    <ul className="checklist">
                      {asStrings(privacyData.limitations).map((item, index) => (
                        <li key={index}><ShieldCheck size={14} />{item}</li>
                      ))}
                    </ul>
                  </>
                ) : (
                  <Alert tone="warning" title="Privacy report unavailable">
                    This dataset has no privacy report attached.
                  </Alert>
                )}
              </Card>
            </div>
          ) : null}

          {!quality && privacy ? (
            <Card>
              <CardHeader title="Quality report unavailable" subtitle="No quality report is attached to this dataset." />
              <ReportDownload
                generatedId={privacy.generatedDatasetId}
                reportType="privacy"
                onDownload={downloadSynthMedReport}
              />
            </Card>
          ) : null}
        </>
      )}
    </>
  );
};
