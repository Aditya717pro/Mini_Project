import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { CheckCircle2, Cpu, Download, FlaskConical, Plus, ShieldCheck, Trash2, Wand2 } from 'lucide-react';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  Field,
  InfoRow,
  LoadingState,
  PageHeader,
} from '../components/ui';
import { useDemo } from '../store/DemoStore';
import {
  asConditionSatisfaction,
  conditionLabel,
  formatDateTime,
  formatNumber,
} from '../lib/format';
import type {
  SynthMedColumnAnalysis,
  SynthMedCondition,
  SynthMedConditionSatisfaction,
  SynthMedConditionValidationRequest,
  SynthMedConditionValidationResponse,
  SynthMedDatasetColumns,
  SynthMedEvaluationReport,
  SynthMedGenerationAnalysis,
  SynthMedGenerationJob,
  SynthMedGenerationStatus,
  SynthMedModelName,
  SynthMedModelsResponse,
} from '../types';

type ColumnRole = 'Auto' | 'Numerical' | 'Categorical' | 'Identifier';

interface ConditionDraft {
  column: string;
  value: string;
  numRows: number;
}

const MODEL_OPTIONS: SynthMedModelName[] = ['CTGAN', 'TVAE', 'GaussianCopula'];
const TERMINAL_STATUSES: SynthMedGenerationStatus[] = ['Completed', 'Failed'];
const JOB_STAGES: SynthMedGenerationStatus[] = [
  'Queued',
  'Preprocessing',
  'Training',
  'Generating',
  'Validating',
  'Evaluating',
  'Completed',
];

const jobTone = (
  status: SynthMedGenerationStatus,
): 'success' | 'info' | 'warning' | 'danger' | 'neutral' | 'purple' => {
  if (status === 'Completed') return 'success';
  if (status === 'Failed') return 'danger';
  if (status === 'Training' || status === 'Generating') return 'purple';
  if (status === 'Queued') return 'neutral';
  return 'info';
};

const kindLabel = (column: SynthMedColumnAnalysis): string => {
  if (column.constant) return 'Constant';
  if (column.potentialIdentifier) return 'Identifier';
  return column.kind.charAt(0).toUpperCase() + column.kind.slice(1);
};

const defaultRole = (column: SynthMedColumnAnalysis): ColumnRole => {
  if (column.potentialIdentifier) return 'Identifier';
  if (column.kind === 'numerical') return 'Numerical';
  if (column.kind === 'categorical') return 'Categorical';
  return 'Auto';
};

const errorMessage = (error: unknown) => (error instanceof Error ? error.message : 'Unexpected API error');

const SatisfactionCard = ({ satisfaction }: { satisfaction: SynthMedConditionSatisfaction }) => {
  const passed = satisfaction.passed ?? satisfaction.allConditionsSatisfied ?? false;
  const combined = satisfaction.combined;
  return (
    <Card>
      <CardHeader
        title="Condition satisfaction"
        subtitle={satisfaction.method ?? 'Measured from the generated records.'}
        action={<Badge tone={passed ? 'success' : 'danger'}>{passed ? 'All conditions satisfied' : 'Not satisfied'}</Badge>}
      />
      {combined ? (
        <div className="info-list">
          <InfoRow label="Conditions requested">{formatNumber(combined.requestedConditions ?? 0)}</InfoRow>
          <InfoRow label="Generated records">{formatNumber(combined.totalGeneratedRecords)}</InfoRow>
          <InfoRow label="Satisfying records">{formatNumber(combined.satisfyingRecords)}</InfoRow>
          <InfoRow label="Satisfaction">{combined.satisfactionPercentage.toFixed(1)}%</InfoRow>
        </div>
      ) : null}
      {satisfaction.conditions?.length ? (
        <>
          <h3 className="section-title">Per-condition results</h3>
          <div className="table-wrap">
            <table className="table table-compact">
              <thead>
                <tr>
                  <th>Condition</th>
                  <th className="num">Requested rows</th>
                  <th className="num">Satisfying rows</th>
                  <th className="num">Satisfaction</th>
                </tr>
              </thead>
              <tbody>
                {satisfaction.conditions.map((result) => (
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
      {satisfaction.cohorts?.length ? (
        <>
          <h3 className="section-title">Sampling cohorts</h3>
          <div className="table-wrap">
            <table className="table table-compact">
              <thead>
                <tr>
                  <th>Cohort</th>
                  <th>Conditions</th>
                  <th className="num">Requested</th>
                  <th className="num">Satisfying</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {satisfaction.cohorts.map((cohort) => (
                  <tr key={cohort.index}>
                    <td>{cohort.mode}</td>
                    <td>
                      {cohort.conditions.map((condition) => conditionLabel(condition)).join(' AND ') || 'All records'}
                    </td>
                    <td className="num">{formatNumber(cohort.requestedRows)}</td>
                    <td className="num">{formatNumber(cohort.satisfyingRecords)}</td>
                    <td><Badge tone={cohort.passed ? 'success' : 'danger'}>{cohort.passed ? 'Passed' : 'Failed'}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </Card>
  );
};

export const SynthMedGenerate = () => {
  const {
    synthSources,
    createSynthMedSourceFromRepository,
    downloadSynthMedSource,
    analyseSynthMedGeneration,
    listSynthMedModels,
    getSynthMedDatasetColumns,
    validateSynthMedConditions,
    startSynthMedGeneration,
    getSynthMedGenerationJob,
    getSynthMedGenerationJobConditions,
    refreshSynthMed,
  } = useDemo();

  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const querySourceId = searchParams.get('sourceId') || '';
  const repositoryDatasetId = searchParams.get('datasetId') || '';
  const repositoryVersionId = searchParams.get('versionId') || '';
  const [sourceId, setSourceId] = useState(querySourceId);
  const [sourcePreparing, setSourcePreparing] = useState(Boolean(repositoryDatasetId));
  const [sourcePrepareError, setSourcePrepareError] = useState('');
  const sourcePreparationRef = useRef<{
    datasetId: string;
    versionId: string;
    promise: ReturnType<typeof createSynthMedSourceFromRepository>;
  } | null>(null);
  const selectedSource = useMemo(
    () => synthSources.find((item) => item.id === sourceId),
    [synthSources, sourceId],
  );
  const [analysis, setAnalysis] = useState<SynthMedGenerationAnalysis | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState('');
  const [selectedColumns, setSelectedColumns] = useState<string[]>([]);
  const [roles, setRoles] = useState<Record<string, ColumnRole>>({});
  const [datasetName, setDatasetName] = useState('');
  const [seed, setSeed] = useState('');
  const [epochs, setEpochs] = useState('20');
  const [batchSize, setBatchSize] = useState('100');
  const [recordCount, setRecordCount] = useState('1000');
  const [preserveMissingness, setPreserveMissingness] = useState(true);
  const [sourcePreservingMode, setSourcePreservingMode] = useState(false);
  const [ageToleranceYears, setAgeToleranceYears] = useState('5');
  const [models, setModels] = useState<SynthMedModelsResponse | null>(null);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState('');
  const [model, setModel] = useState<SynthMedModelName>('CTGAN');
  const [columnInfo, setColumnInfo] = useState<SynthMedDatasetColumns | null>(null);
  const [columnInfoLoading, setColumnInfoLoading] = useState(false);
  const [columnInfoError, setColumnInfoError] = useState('');
  const [conditionalEnabled, setConditionalEnabled] = useState(false);
  const [andMode, setAndMode] = useState(true);
  const [conditions, setConditions] = useState<ConditionDraft[]>([]);
  const [validation, setValidation] = useState<SynthMedConditionValidationResponse | null>(null);
  const [validated, setValidated] = useState<{ signature: string; result: SynthMedConditionValidationResponse } | null>(
    null,
  );
  const [validationBusy, setValidationBusy] = useState(false);
  const [validationError, setValidationError] = useState('');
  const [formError, setFormError] = useState('');
  const [starting, setStarting] = useState(false);
  const [job, setJob] = useState<SynthMedGenerationJob | null>(null);
  const [conditionReport, setConditionReport] = useState<SynthMedEvaluationReport | null>(null);
  const [conditionReportLoading, setConditionReportLoading] = useState(false);

  useEffect(() => {
    if (querySourceId) {
      setSourceId(querySourceId);
      return;
    }
    if (!repositoryDatasetId && !sourceId && synthSources.length > 0) {
      setSourceId(synthSources[0].id);
    }
  }, [querySourceId, repositoryDatasetId, sourceId, synthSources]);

  useEffect(() => {
    if (!repositoryDatasetId) return;
    let active = true;
    setSourcePreparing(true);
    setSourcePrepareError('');
    const existing = sourcePreparationRef.current;
    const promise =
      existing?.datasetId === repositoryDatasetId && existing.versionId === repositoryVersionId
        ? existing.promise
        : createSynthMedSourceFromRepository(repositoryDatasetId, repositoryVersionId || undefined);
    sourcePreparationRef.current = { datasetId: repositoryDatasetId, versionId: repositoryVersionId, promise };
    void promise
      .then((created) => {
        if (active) setSourceId(created.id);
      })
      .catch((error: unknown) => {
        if (!active) return;
        sourcePreparationRef.current = null;
        setSourcePrepareError(errorMessage(error));
      })
      .finally(() => {
        if (active) setSourcePreparing(false);
      });
    return () => {
      active = false;
    };
  }, [repositoryDatasetId, repositoryVersionId, createSynthMedSourceFromRepository]);

  useEffect(() => {
    let active = true;
    setModelsLoading(true);
    void listSynthMedModels()
      .then((result) => {
        if (active) setModels(result);
      })
      .catch((error: unknown) => {
        if (active) setModelsError(errorMessage(error));
      })
      .finally(() => {
        if (active) setModelsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [listSynthMedModels]);

  useEffect(() => {
    let active = true;
    setJob(null);
    setFormError('');
    if (!sourceId) {
      setAnalysis(null);
      return;
    }
    setAnalysisLoading(true);
    setAnalysisError('');
    void analyseSynthMedGeneration(sourceId)
      .then((result) => {
        if (!active) return;
        setAnalysis(result);
        setDatasetName(`${result.datasetName} synthetic cohort`);
        setSelectedColumns(
          result.columns
            .filter((column) => !column.potentialIdentifier && !column.constant)
            .map((column) => column.name),
        );
        setRoles(Object.fromEntries(result.columns.map((column) => [column.name, defaultRole(column)])));
        setRecordCount(String(Math.min(1000, Math.max(1, result.totalRecords * 2))));
        setConditions([]);
        setConditionalEnabled(false);
        setValidated(null);
        setValidation(null);
        setValidationError('');
      })
      .catch((error: unknown) => {
        if (active) setAnalysisError(errorMessage(error));
      })
      .finally(() => {
        if (active) setAnalysisLoading(false);
      });
    return () => {
      active = false;
    };
  }, [sourceId, analyseSynthMedGeneration]);

  useEffect(() => {
    if (!sourceId) {
      setColumnInfo(null);
      return;
    }
    let active = true;
    setColumnInfoLoading(true);
    setColumnInfoError('');
    void getSynthMedDatasetColumns(sourceId, model)
      .then((result) => {
        if (active) setColumnInfo(result);
      })
      .catch((error: unknown) => {
        if (active) setColumnInfoError(errorMessage(error));
      })
      .finally(() => {
        if (active) setColumnInfoLoading(false);
      });
    return () => {
      active = false;
    };
  }, [sourceId, model, getSynthMedDatasetColumns]);

  useEffect(() => {
    const value = Number(recordCount);
    if (!andMode || !Number.isInteger(value) || value < 1) return;
    setConditions((previous) =>
      previous.every((condition) => condition.numRows === value)
        ? previous
        : previous.map((condition) => ({ ...condition, numRows: value })),
    );
  }, [andMode, recordCount]);

  useEffect(() => {
    if (!job || TERMINAL_STATUSES.includes(job.status)) return;
    let cancelled = false;
    const timer = window.setInterval(() => {
      void getSynthMedGenerationJob(job.id)
        .then((updated) => {
          if (!cancelled) setJob(updated);
        })
        .catch((error: unknown) => {
          if (!cancelled) setFormError(errorMessage(error));
        });
    }, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [job?.id, job?.status, getSynthMedGenerationJob]);

  useEffect(() => {
    if (job?.status === 'Completed') void refreshSynthMed().catch(() => undefined);
  }, [job?.status, job?.id, refreshSynthMed]);

  useEffect(() => {
    if (job?.status === 'Completed' && job.generatedDatasetId) {
      navigate(`/synthmed/generated/${job.generatedDatasetId}`, { replace: true });
    }
  }, [job?.status, job?.generatedDatasetId, navigate]);

  useEffect(() => {
    const satisfaction = asConditionSatisfaction(job?.conditionSatisfaction);
    if (!job || job.generationMode !== 'Conditional' || !TERMINAL_STATUSES.includes(job.status)) {
      setConditionReport(null);
      return;
    }
    if (satisfaction) {
      setConditionReport({
        id: '',
        generatedDatasetId: job.generatedDatasetId,
        reportType: 'conditions',
        method: satisfaction.method ?? '',
        score: null,
        report: satisfaction as unknown as Record<string, unknown>,
        createdAt: job.completedAt,
      });
      return;
    }
    if (!job.generatedDatasetId) return;
    let active = true;
    setConditionReportLoading(true);
    void getSynthMedGenerationJobConditions(job.id)
      .then((result) => {
        if (active) setConditionReport(result);
      })
      .catch(() => undefined)
      .finally(() => {
        if (active) setConditionReportLoading(false);
      });
    return () => {
      active = false;
    };
  }, [
    job?.id,
    job?.status,
    job?.generatedDatasetId,
    job?.generationMode,
    job?.conditionSatisfaction,
    job?.completedAt,
    getSynthMedGenerationJobConditions,
  ]);

  const identifierColumns = useMemo(
    () =>
      analysis?.columns
        .filter((column) => column.potentialIdentifier || roles[column.name] === 'Identifier')
        .map((column) => column.name) ?? [],
    [analysis, roles],
  );

  const includedColumns = useMemo(
    () => selectedColumns.filter((column) => !identifierColumns.includes(column)),
    [selectedColumns, identifierColumns],
  );

  const categoricalColumns = useMemo(
    () => includedColumns.filter((column) => roles[column] === 'Categorical'),
    [includedColumns, roles],
  );

  const numericalColumns = useMemo(
    () => includedColumns.filter((column) => roles[column] === 'Numerical'),
    [includedColumns, roles],
  );

  const capability = models?.models.find((item) => item.model === model) ?? null;
  const modelOptions = models?.models.map((item) => item.model) ?? MODEL_OPTIONS;

  const eligibleColumns = useMemo(
    () => (columnInfo?.eligibleColumns ?? []).filter((column) => includedColumns.includes(column.name)),
    [columnInfo, includedColumns],
  );

  const sdtypeByName = useMemo(() => {
    const mapping: Record<string, string> = {};
    columnInfo?.numericalColumns.forEach((name) => {
      mapping[name] = 'numerical';
    });
    columnInfo?.categoricalColumns.forEach((name) => {
      mapping[name] = 'categorical';
    });
    columnInfo?.booleanColumns.forEach((name) => {
      mapping[name] = 'boolean';
    });
    columnInfo?.datetimeColumns.forEach((name) => {
      mapping[name] = 'datetime';
    });
    columnInfo?.eligibleColumns.forEach((column) => {
      mapping[column.name] = column.sdtype;
    });
    return mapping;
  }, [columnInfo]);

  const recordValue = Number(recordCount);
  const cohortSum = conditions.reduce((sum, condition) => sum + (Number(condition.numRows) || 0), 0);
  const cohortMismatch = !andMode && cohortSum !== recordValue;

  const conditionPayload = useMemo<SynthMedCondition[]>(
    () =>
      conditions.map((condition) => {
        const sdtype = sdtypeByName[condition.column] ?? 'categorical';
        const raw = condition.value;
        const value = sdtype === 'numerical' && raw.trim() !== '' ? Number(raw) : raw;
        const requested = Number(condition.numRows);
        return {
          column: condition.column,
          operator: 'eq',
          value,
          numRows: andMode ? recordValue : Number.isFinite(requested) ? requested : 0,
        };
      }),
    [conditions, sdtypeByName, andMode, recordValue],
  );

  const signature = useMemo(
    () =>
      JSON.stringify({
        sourceId,
        model,
        recordValue,
        includedColumns,
        identifierColumns,
        categoricalColumns,
        numericalColumns,
        preserveMissingness,
        sourcePreservingMode,
        ageToleranceYears,
        conditionPayload,
      }),
    [
      sourceId,
      model,
      recordValue,
      includedColumns,
      identifierColumns,
      categoricalColumns,
      numericalColumns,
      preserveMissingness,
      sourcePreservingMode,
      ageToleranceYears,
      conditionPayload,
    ],
  );

  const validationStale = conditionalEnabled && validated?.signature !== signature;
  const displayedSatisfaction = conditionReport ? asConditionSatisfaction(conditionReport.report) : null;

  const buildValidationPayload = (): SynthMedConditionValidationRequest => ({
    sourceDatasetId: analysis?.sourceDatasetId ?? sourceId,
    model,
    conditions: conditionPayload,
    recordCount: recordValue,
    selectedColumns: includedColumns,
    identifierColumns,
    primaryKey: identifierColumns[0] ?? null,
    categoricalColumns,
    numericalColumns,
    preserveMissingness,
    sourcePreservingMode,
    ageToleranceYears: Number(ageToleranceYears),
  });

  const toggleColumn = (column: SynthMedColumnAnalysis) => {
    if (column.potentialIdentifier) return;
    setSelectedColumns((previous) =>
      previous.includes(column.name) ? previous.filter((name) => name !== column.name) : [...previous, column.name],
    );
    setValidated(null);
  };

  const changeRole = (columnName: string, role: ColumnRole) => {
    setRoles((previous) => ({ ...previous, [columnName]: role }));
    setSelectedColumns((previous) =>
      role === 'Identifier'
        ? previous.filter((name) => name !== columnName)
        : previous.includes(columnName)
          ? previous
          : [...previous, columnName],
    );
    setValidated(null);
  };

  const toggleConditional = (enabled: boolean) => {
    setConditionalEnabled(enabled);
    setValidationError('');
    setValidated(null);
    if (enabled && conditions.length === 0 && eligibleColumns.length > 0) {
      setConditions([{ column: eligibleColumns[0].name, value: '', numRows: recordValue }]);
    }
  };

  const changeAndMode = (enabled: boolean) => {
    setAndMode(enabled);
    setValidated(null);
    if (enabled) {
      setConditions((previous) => previous.map((condition) => ({ ...condition, numRows: recordValue })));
    }
  };

  const addCondition = () => {
    if (eligibleColumns.length === 0) return;
    const column =
      eligibleColumns.find((item) => !conditions.some((condition) => condition.column === item.name)) ??
      eligibleColumns[0];
    setConditions((previous) => [...previous, { column: column.name, value: '', numRows: recordValue }]);
    setValidated(null);
  };

  const updateCondition = (index: number, patch: Partial<ConditionDraft>) => {
    setConditions((previous) => previous.map((item, position) => (position === index ? { ...item, ...patch } : item)));
    setValidated(null);
  };

  const removeCondition = (index: number) => {
    setConditions((previous) => previous.filter((_, position) => position !== index));
    setValidated(null);
  };

  const runValidation = async () => {
    setValidationError('');
    setValidation(null);
    setValidated(null);
    if (!analysis) return;
    if (conditions.length === 0) {
      setValidationError('Add at least one condition before validating.');
      return;
    }
    if (cohortMismatch) {
      setValidationError(`Cohort row counts sum to ${cohortSum}, but ${recordValue} records were requested.`);
      return;
    }
    setValidationBusy(true);
    try {
      const result = await validateSynthMedConditions(buildValidationPayload());
      setValidation(result);
      if (result.valid) setValidated({ signature, result });
    } catch (error) {
      setValidationError(errorMessage(error));
    } finally {
      setValidationBusy(false);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!analysis) return;
    const epochsValue = Number(epochs);
    const batchValue = Number(batchSize);
    const seedValue = seed.trim() ? Number(seed) : null;

    if (includedColumns.length === 0) {
      setFormError('Select at least one non-identifier column to train the model.');
      return;
    }
    if (!Number.isInteger(epochsValue) || epochsValue < 1 || epochsValue > 10000) {
      setFormError('Epochs must be a whole number between 1 and 10000.');
      return;
    }
    if (!Number.isInteger(batchValue) || batchValue < 20 || batchValue > 10000 || batchValue % 10 !== 0) {
      setFormError('Batch size must be a multiple of 10 between 20 and 10000.');
      return;
    }
    if (!Number.isInteger(recordValue) || recordValue < 1 || recordValue > 1000000) {
      setFormError('Record count must be a whole number between 1 and 1000000.');
      return;
    }
    if (seedValue !== null && !Number.isInteger(seedValue)) {
      setFormError('Seed must be a whole number or blank for a random seed.');
      return;
    }
    const ageToleranceValue = Number(ageToleranceYears);
    if (sourcePreservingMode && (!Number.isInteger(ageToleranceValue) || ageToleranceValue < 0 || ageToleranceValue > 120)) {
      setFormError('Age tolerance must be a whole number between 0 and 120 years.');
      return;
    }
    if (conditionalEnabled) {
      if (conditions.length === 0) {
        setFormError('Conditional generation requires at least one condition.');
        return;
      }
      const ineligible = conditionPayload
        .map((condition) => condition.column)
        .filter((name) => !eligibleColumns.some((column) => column.name === name));
      if (ineligible.length > 0) {
        setFormError(`Remove conditions on ineligible or unselected columns: ${ineligible.join(', ')}.`);
        return;
      }
      if (cohortMismatch) {
        setFormError(`Cohort numRows must sum to ${recordValue} (currently ${cohortSum}).`);
        return;
      }
      if (!validated || validated.signature !== signature || !validated.result.valid) {
        setFormError('Validate the conditional configuration before starting generation.');
        return;
      }
    }

    setFormError('');
    setStarting(true);
    try {
      const created = await startSynthMedGeneration({
        sourceDatasetId: analysis.sourceDatasetId,
        datasetName: datasetName.trim() || `${analysis.datasetName} synthetic`,
        model,
        generationMode: conditionalEnabled ? 'Conditional' : 'Unconditional',
        conditions: conditionalEnabled ? conditionPayload : [],
        selectedColumns: includedColumns,
        categoricalColumns,
        numericalColumns,
        identifierColumns,
        primaryKey: identifierColumns[0] ?? null,
        seed: seedValue,
        epochs: epochsValue,
        batchSize: batchValue,
        recordCount: recordValue,
        preserveMissingness,
        sourcePreservingMode,
        ageToleranceYears: ageToleranceValue,
      });
      setJob(created);
      await refreshSynthMed().catch(() => undefined);
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setStarting(false);
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="Synthetic data"
        title="Generate Synthetic Data"
        description="Train a real SDV CTGAN, TVAE or GaussianCopula model on an authorised source dataset, optionally with exact-value conditions, then review the reports before release."
        actions={
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
            {selectedSource ? (
              <Button
                variant="secondary"
                icon={<Download size={16} />}
                onClick={() => void downloadSynthMedSource(selectedSource)}
                title={`Download ${selectedSource.originalFilename}`}
              >
                Download source
              </Button>
            ) : null}
            <Link to="/synthmed/generated">
              <Button variant="secondary" icon={<FlaskConical size={16} />}>
                Generated datasets
              </Button>
            </Link>
            <Link to="/synthmed">
              <Button variant="secondary" icon={<Wand2 size={16} />}>
                Change source
              </Button>
            </Link>
          </div>
        }
      />

              <Alert tone="info" title="Real SDV training on CPU">
                The selected model, capabilities and conditional sampling API are read from the backend. Training runs as an
                authenticated background job; the page polls genuine job states instead of showing simulated progress.
              </Alert>

              <form className="upload-layout" onSubmit={(event) => void submit(event)}>
                <div className="upload-main">
                  <Card>
                    <CardHeader
                      title="1. Select and analyse a source"
                      subtitle="Schema detection runs on the server before training."
                      action={
                        selectedSource ? (
                          <Button
                            type="button"
                            variant="secondary"
                            size="sm"
                            icon={<Download size={14} />}
                            onClick={() => void downloadSynthMedSource(selectedSource)}
                          >
                            Download ({selectedSource.fileFormat})
                          </Button>
                        ) : null
                      }
                    />
                    <div className="profile-summary" data-testid="generate-source-summary">
                      <div><span>Repository dataset</span><strong>{repositoryDatasetId || '—'}</strong></div>
                      <div><span>SynthMed source</span><strong>{selectedSource?.id || 'Preparing…'}</strong></div>
                      <div><span>Status</span><strong>{sourcePreparing ? 'Preparing source' : analysis ? 'Ready to prepare' : 'Waiting for source'}</strong></div>
                    </div>

                    {sourcePreparing ? <LoadingState label="Preparing repository dataset as a SynthMed source…" /> : null}
                    {sourcePrepareError ? (
                      <Alert tone="danger" title="Could not prepare source dataset">{sourcePrepareError}</Alert>
                    ) : null}

                    <Field
                      label="Source dataset"
                      htmlFor="synthmed-generation-source"
                      required
                      hint="Prepared from an authorised dataset in My Repository."
                    >
                      <select
                        id="synthmed-generation-source"
                        className="input"
                        value={sourceId}
                        onChange={(event) => setSourceId(event.target.value)}
                      >
                        <option value="">Select a source dataset…</option>
                        {synthSources.map((source) => (
                          <option key={source.id} value={source.id}>
                            {source.datasetName} · {source.originalFilename}
                          </option>
                        ))}
                      </select>
                    </Field>

                    {analysisLoading ? <LoadingState label="Analysing source schema…" /> : null}
                    {analysisError ? <Alert tone="danger" title="Analysis failed">{analysisError}</Alert> : null}

                    {analysis && !analysisLoading ? (
                      <>
                        <div className="profile-summary">
                          <div><span>Records</span><strong>{formatNumber(analysis.totalRecords)}</strong></div>
                          <div><span>Columns</span><strong>{formatNumber(analysis.totalColumns)}</strong></div>
                          <div><span>Duplicates</span><strong>{formatNumber(analysis.duplicateRecords)}</strong></div>
                          <div><span>Identifiers</span><strong>{analysis.potentialIdentifierColumns.length}</strong></div>
                          <div><span>Ready</span><strong>{analysis.generationReady ? 'Yes' : 'No'}</strong></div>
                        </div>
                        <p className="muted small">{analysis.guidance}</p>
                        {!analysis.generationReady ? (
                          <Alert tone="warning" title="Review source suitability">
                            This source has no modelable columns after identifier and constant-column exclusion.
                          </Alert>
                        ) : null}

                        <div className="column-grid">
                          {analysis.columns.map((column) => {
                            const excluded = column.potentialIdentifier || column.constant;
                            const checked = selectedColumns.includes(column.name) && !excluded;
                            return (
                              <div className={`column-option ${checked ? 'selected' : ''}`} key={column.name}>
                                <div className="column-option-head">
                                  <label>
                                    <input
                                      type="checkbox"
                                      checked={checked}
                                      disabled={excluded}
                                      onChange={() => toggleColumn(column)}
                                    />
                                    <strong>{column.name}</strong>
                                  </label>
                                  <Badge tone={column.potentialIdentifier ? 'warning' : column.constant ? 'neutral' : 'info'}>
                                    {kindLabel(column)}
                                  </Badge>
                                </div>
                                <div className="column-option-meta">
                                  <span>{formatNumber(column.uniqueCount)} unique</span>
                                  <span>{column.missingPercentage}% missing</span>
                                </div>
                                {column.quasiIdentifier && !column.potentialIdentifier ? (
                                  <span className="column-note">Possible quasi-identifier</span>
                                ) : null}
                                {column.potentialIdentifier ? (
                                  <span className="column-note">Excluded and never reproduced</span>
                                ) : null}
                                {!excluded ? (
                                  <select
                                    className="input input-sm"
                                    aria-label={`Role for ${column.name}`}
                                    value={roles[column.name] ?? 'Auto'}
                                    onChange={(event) => changeRole(column.name, event.target.value as ColumnRole)}
                                  >
                                    <option value="Auto">Auto</option>
                                    <option value="Numerical">Numerical</option>
                                    <option value="Categorical">Categorical</option>
                                    <option value="Identifier">Treat as identifier</option>
                                  </select>
                                ) : null}
                              </div>
                            );
                          })}
                        </div>
                      </>
                    ) : null}
                  </Card>

                  <Card>
                    <CardHeader
                      title="2. Select a synthesis model"
                      subtitle="Model capabilities come from the installed SDV runtime."
                      action={<Badge tone="purple">SDV {models?.sdvVersion ?? '—'}</Badge>}
                    />
                    {modelsLoading ? <LoadingState label="Loading model capabilities…" /> : null}
                    {modelsError ? <Alert tone="danger" title="Capabilities unavailable">{modelsError}</Alert> : null}
                    <Field
                      label="Model"
                      htmlFor="synthmed-generation-model"
                      required
                      hint="Every listed model supports unconditional sampling and exact equality conditions."
                    >
                      <select
                        id="synthmed-generation-model"
                        className="input"
                        value={model}
                        onChange={(event) => {
                          setModel(event.target.value as SynthMedModelName);
                          setValidated(null);
                        }}
                      >
                        {modelOptions.map((name) => (
                          <option key={name} value={name}>
                            {name}{models?.models.find((item) => item.model === name)?.sdvClass ? ` · ${models.models.find((item) => item.model === name)?.sdvClass}` : ''}
                          </option>
                        ))}
                      </select>
                    </Field>
                    {capability ? (
                      <>
                        <div className="chip-grid">
                          <Badge tone="info">{capability.samplingApi}</Badge>
                          <Badge tone="purple">{capability.samplingStrategy}</Badge>
                          <Badge tone={capability.conditionalSampling ? 'success' : 'neutral'}>
                            {capability.conditionalSampling ? 'Conditional sampling' : 'No conditional sampling'}
                          </Badge>
                          <Badge tone={capability.exactEquality ? 'success' : 'neutral'}>
                            {capability.exactEquality ? 'Exact equality' : 'No exact equality'}
                          </Badge>
                          <Badge tone={capability.rangeOperators ? 'info' : 'neutral'}>
                            {capability.rangeOperators ? 'Range operators' : 'Equality only'}
                          </Badge>
                          <Badge tone={capability.implemented === false ? 'danger' : 'success'}>
                            {capability.implemented === false ? 'Not implemented' : 'Implemented'}
                          </Badge>
                        </div>
                        <ul className="checklist">
                          {capability.notes.map((note, index) => (
                            <li key={index}><Cpu size={14} />{note}</li>
                          ))}
                        </ul>
                      </>
                    ) : null}
                  </Card>

                  <Card>
                    <CardHeader title="3. Configure generation" subtitle={`Training settings and conditions for ${model}.`} />
                    <div className="review-grid">
                      <Field label="Generated dataset name" htmlFor="synthmed-generation-name" required>
                        <input
                          id="synthmed-generation-name"
                          className="input"
                          value={datasetName}
                          onChange={(event) => setDatasetName(event.target.value)}
                          placeholder="Fictional synthetic cohort"
                        />
                      </Field>
                      <Field
                        label="Seed"
                        htmlFor="synthmed-generation-seed"
                        hint="Blank uses a random seed; the chosen value is recorded with the job."
                      >
                        <input
                          id="synthmed-generation-seed"
                          className="input"
                          type="number"
                          value={seed}
                          onChange={(event) => setSeed(event.target.value)}
                          placeholder="e.g. 42"
                        />
                      </Field>
                      <Field
                        label="Epochs"
                        htmlFor="synthmed-generation-epochs"
                        hint="CTGAN and TVAE use epochs; GaussianCopula ignores them."
                      >
                        <input
                          id="synthmed-generation-epochs"
                          className="input"
                          type="number"
                          min={1}
                          max={10000}
                          value={epochs}
                          onChange={(event) => setEpochs(event.target.value)}
                        />
                      </Field>
                      <Field
                        label="Batch size"
                        htmlFor="synthmed-generation-batch"
                        hint="CTGAN and TVAE require a multiple of 10 between 20 and 10000."
                      >
                        <input
                          id="synthmed-generation-batch"
                          className="input"
                          type="number"
                          min={20}
                          max={10000}
                          step={10}
                          value={batchSize}
                          onChange={(event) => setBatchSize(event.target.value)}
                        />
                      </Field>
                      <Field label="Synthetic records" htmlFor="synthmed-generation-records" required>
                        <input
                          id="synthmed-generation-records"
                          className="input"
                          type="number"
                          min={1}
                          max={1000000}
                          value={recordCount}
                          onChange={(event) => setRecordCount(event.target.value)}
                        />
                      </Field>
                      <div className="field">
                        <span className="field-label">Missing values</span>
                        <label className="check-row">
                          <input
                            type="checkbox"
                            checked={preserveMissingness}
                            onChange={(event) => setPreserveMissingness(event.target.checked)}
                          />
                          Preserve missingness for SDV handling
                        </label>
                        <div className="field-hint">Missing values are never replaced with zero or a medical default.</div>
                      </div>
                      <div className="field">
                        <span className="field-label">Source-preserving mode</span>
                        <label className="check-row">
                          <input
                            type="checkbox"
                            checked={sourcePreservingMode}
                            onChange={(event) => setSourcePreservingMode(event.target.checked)}
                          />
                          Preserve every source row in source order
                        </label>
                        <div className="field-hint">
                          Strict mode aligns each output row to its source row and validates record-level values.
                        </div>
                        {sourcePreservingMode ? (
                          <Field
                            label="Age tolerance (years)"
                            htmlFor="synthmed-generation-age-tolerance"
                            hint="Generated ages must stay within this range of the aligned source row."
                          >
                            <input
                              id="synthmed-generation-age-tolerance"
                              className="input"
                              type="number"
                              min={0}
                              max={120}
                              value={ageToleranceYears}
                              onChange={(event) => setAgeToleranceYears(event.target.value)}
                            />
                          </Field>
                        ) : null}
                      </div>
                    </div>

                    <div className="divider" />
                    <div className="field">
                      <span className="field-label">Generation mode</span>
                      <label className="check-row">
                        <input
                          type="checkbox"
                          checked={conditionalEnabled}
                          onChange={(event) => toggleConditional(event.target.checked)}
                        />
                        Enable conditional generation with exact equality conditions
                      </label>
                      <div className="field-hint">
                        Unconditional sampling is used when this is off. Conditions are validated by the server before a job starts.
                      </div>
                    </div>

                    {conditionalEnabled ? (
                      <>
                        <div className="field">
                          <span className="field-label">Condition mode</span>
                          <label className="check-row">
                            <input type="checkbox" checked={andMode} onChange={(event) => changeAndMode(event.target.checked)} />
                            Combine all conditions with AND for every generated record
                          </label>
                          <div className="field-hint">
                            {andMode
                              ? `Each condition uses all ${formatNumber(recordValue)} records; the backend combines them into one cohort.`
                              : 'Cohort mode samples each condition separately; numRows values must add up to the requested record count.'}
                          </div>
                        </div>

                        {columnInfoLoading ? <LoadingState label="Loading eligible condition columns…" /> : null}
                        {columnInfoError ? <Alert tone="danger" title="Condition columns unavailable">{columnInfoError}</Alert> : null}
                        {!columnInfoLoading && eligibleColumns.length === 0 ? (
                          <Alert tone="warning" title="No eligible columns">
                            Select modelable, non-identifier columns first. Identifier and constant columns cannot be conditioned on.
                          </Alert>
                        ) : null}

                        {conditions.map((condition, index) => {
                          const sdtype = sdtypeByName[condition.column] ?? 'categorical';
                          return (
                            <div className="review-grid" key={index}>
                              <Field label={`Column ${index + 1}`} htmlFor={`condition-column-${index}`}>
                                <select
                                  id={`condition-column-${index}`}
                                  className="input"
                                  value={condition.column}
                                  onChange={(event) => updateCondition(index, { column: event.target.value, value: '' })}
                                >
                                  {eligibleColumns.map((column) => (
                                    <option key={column.name} value={column.name}>
                                      {column.name} · {column.sdtype}
                                    </option>
                                  ))}
                                </select>
                              </Field>
                              <Field label="Operator" htmlFor={`condition-operator-${index}`}>
                                <select id={`condition-operator-${index}`} className="input" value="eq" disabled>
                                  <option value="eq">Equals (=)</option>
                                </select>
                              </Field>
                              <Field
                                label="Exact value"
                                htmlFor={`condition-value-${index}`}
                                hint={`Expected type: ${sdtype}. Use a value present in the source dataset.`}
                              >
                                {sdtype === 'boolean' ? (
                                  <select
                                    id={`condition-value-${index}`}
                                    className="input"
                                    value={condition.value}
                                    onChange={(event) => updateCondition(index, { value: event.target.value })}
                                  >
                                    <option value="">Select a value…</option>
                                    <option value="true">true</option>
                                    <option value="false">false</option>
                                  </select>
                                ) : (
                                  <input
                                    id={`condition-value-${index}`}
                                    className="input"
                                    type={sdtype === 'numerical' ? 'number' : 'text'}
                                    value={condition.value}
                                    onChange={(event) => updateCondition(index, { value: event.target.value })}
                                    placeholder={sdtype === 'datetime' ? 'YYYY-MM-DD' : 'Exact value'}
                                  />
                                )}
                              </Field>
                              <Field label="Rows" htmlFor={`condition-rows-${index}`}>
                                <div className="inline-controls">
                                  <input
                                    id={`condition-rows-${index}`}
                                    className="input input-sm"
                                    type="number"
                                    min={1}
                                    max={recordValue}
                                    value={condition.numRows}
                                    disabled={andMode}
                                    onChange={(event) => updateCondition(index, { numRows: Number(event.target.value) })}
                                  />
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="sm"
                                    icon={<Trash2 size={14} />}
                                    onClick={() => removeCondition(index)}
                                    aria-label={`Remove condition ${index + 1}`}
                                  >
                                    Remove
                                  </Button>
                                </div>
                              </Field>
                            </div>
                          );
                        })}

                        <div className="button-row">
                          <Button
                            type="button"
                            variant="secondary"
                            icon={<Plus size={15} />}
                            disabled={eligibleColumns.length === 0}
                            onClick={addCondition}
                          >
                            Add condition
                          </Button>
                          <Button
                            type="button"
                            variant="secondary"
                            icon={<CheckCircle2 size={15} />}
                            disabled={validationBusy || conditions.length === 0}
                            onClick={() => void runValidation()}
                          >
                            {validationBusy ? 'Validating…' : 'Validate configuration'}
                          </Button>
                        </div>
                        {!andMode ? (
                          <p className="field-hint">
                            Cohort total: {formatNumber(cohortSum)} of {formatNumber(recordValue)} requested records.
                          </p>
                        ) : null}
                        {cohortMismatch ? (
                          <Alert tone="warning" title="Cohort rows do not match">
                            The sum of condition rows ({formatNumber(cohortSum)}) must equal the synthetic record count (
                            {formatNumber(recordValue)}).
                          </Alert>
                        ) : null}
                        {validationError ? <Alert tone="danger" title="Validation not completed">{validationError}</Alert> : null}
                        {validation ? (
                          <Alert
                            tone={validation.valid ? 'success' : 'danger'}
                            title={validation.valid ? 'Configuration validated by the server' : 'Configuration rejected by the server'}
                          >
                            <div>{validation.normalizedConditions.length} condition(s) accepted · {validation.model} · {validation.capabilities.samplingApi}</div>
                            {validation.errors.length ? <ul className="activity-list">{validation.errors.map((item, index) => <li key={index}><span>{item}</span></li>)}</ul> : null}
                            {validation.warnings.length ? <ul className="activity-list">{validation.warnings.map((item, index) => <li key={index}><span>{item}</span></li>)}</ul> : null}
                          </Alert>
                        ) : null}
                        {validationStale ? (
                          <Alert tone="warning" title="Configuration changed">
                            Re-run validation before starting this conditional job.
                          </Alert>
                        ) : null}
                      </>
                    ) : null}

                    {formError ? <Alert tone="danger" title="Generation not started">{formError}</Alert> : null}
                    <div className="button-row">
                      <Button
                        type="submit"
                        disabled={!analysis || !analysis.generationReady || starting}
                        icon={<Wand2 size={16} />}
                      >
                        {starting ? 'Starting job…' : `Start ${model} generation`}
                      </Button>
                      <Link to="/synthmed/generated">
                        <Button type="button" variant="secondary">View generated datasets</Button>
                      </Link>
                    </div>
                  </Card>

                  {job ? (
                    <>
                      <Card>
                        <CardHeader
                          title="4. Generation job"
                          subtitle={`${job.modelName} · ${job.generationMode} · ${formatNumber(job.requestedRecordCount)} requested records`}
                          action={<Badge tone={jobTone(job.status)}>{job.status}</Badge>}
                        />
                        <div className="pipeline-steps compact-steps">
                          {JOB_STAGES.map((stage) => {
                            const currentIndex = JOB_STAGES.indexOf(job.status === 'Failed' ? 'Completed' : job.status);
                            const stageIndex = JOB_STAGES.indexOf(stage);
                            const done = job.status === 'Completed' || stageIndex < currentIndex;
                            const active = job.status !== 'Completed' && stageIndex === currentIndex;
                            return (
                              <li key={stage}>
                                <span>{done ? <CheckCircle2 size={14} /> : stageIndex + 1}</span>
                                <div>
                                  <strong>{stage}</strong>
                                  <p>{active ? 'Currently running on the server' : done ? 'Finished' : 'Waiting'}</p>
                                </div>
                              </li>
                            );
                          })}
                        </div>
                        <div className="info-list">
                          <InfoRow label="Job ID"><code className="code small">{job.id}</code></InfoRow>
                          <InfoRow label="Model">{job.selectedModel} · {job.modelName}</InfoRow>
                          <InfoRow label="Mode">{job.generationMode}</InfoRow>
                          <InfoRow label="Requested conditions">{formatNumber(job.conditions.length)}</InfoRow>
                          <InfoRow label="Requested records">{formatNumber(job.requestedRecordCount)}</InfoRow>
                          <InfoRow label="Generated records">{formatNumber(job.generatedRecordCount)}</InfoRow>
                          <InfoRow label="Epochs / batch size">{job.epochs} / {job.batchSize}</InfoRow>
                          <InfoRow label="Seed">{job.seed ?? 'Random'}</InfoRow>
                          <InfoRow label="Training duration">
                            {job.trainingDurationSeconds == null ? '—' : `${job.trainingDurationSeconds.toFixed(1)} s`}
                          </InfoRow>
                          {job.startedAt ? <InfoRow label="Started">{formatDateTime(job.startedAt)}</InfoRow> : null}
                          {job.completedAt ? <InfoRow label="Completed">{formatDateTime(job.completedAt)}</InfoRow> : null}
                        </div>
                        {job.conditions.length ? (
                          <>
                            <h3 className="section-title">Requested conditions</h3>
                            <ul className="checklist">
                              {job.conditions.map((condition, index) => (
                                <li key={index}><ShieldCheck size={14} />{conditionLabel(condition)}</li>
                              ))}
                            </ul>
                          </>
                        ) : null}
                        {job.status === 'Failed' ? (
                          <Alert tone="danger" title="Generation failed">
                            {job.error || 'The job failed without a detailed message.'}
                          </Alert>
                        ) : null}
                      </Card>
                      {conditionReportLoading ? <LoadingState label="Loading condition satisfaction…" /> : null}
                      {displayedSatisfaction ? <SatisfactionCard satisfaction={displayedSatisfaction} /> : null}
                    </>
                  ) : null}
                </div>

                <aside className="upload-side">
                  <Card>
                    <CardHeader title="Generation controls" subtitle="Server-enforced" />
                    <ul className="checklist">
                      <li><Cpu size={14} /> CPU-only SDV training; no GPU required.</li>
                      <li><ShieldCheck size={14} /> Identifier columns are excluded from modelling and conditioning.</li>
                      <li>Conditions use exact equality only and are validated before a job starts.</li>
                      <li>Missing values are preserved, not zero-filled.</li>
                      <li>Reports are generated before the dataset is released.</li>
                    </ul>
                  </Card>
                  <Card>
                    <CardHeader title="Selected columns" subtitle={`${includedColumns.length} of ${analysis?.totalColumns ?? 0}`} />
                    {includedColumns.length === 0 ? (
                      <p className="muted small">No columns selected.</p>
                    ) : (
                      <div className="chip-grid">
                        {includedColumns.map((column) => (
                          <span className="chip" key={column}>{column}</span>
                        ))}
                      </div>
                    )}
                  </Card>
                  <Card>
                    <CardHeader title="Limits" subtitle="No clinical claims" />
                    <p className="muted small">
                      Synthetic data is statistically modelled, not clinically validated. Exact source files remain untouched in
                      separate storage.
                    </p>
                  </Card>
                </aside>
              </form>
            </>
            );
};
