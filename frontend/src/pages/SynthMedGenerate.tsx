import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  Cpu,
  Download,
  FlaskConical,
  Plus,
  ShieldCheck,
  Stethoscope,
  Trash2,
  UploadCloud,
  Wand2,
} from 'lucide-react';
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
  SynthMedClinicalReference,
  SynthMedClinicalValidationReport,
  SynthMedClinicalVariable,
  SynthMedColumnAnalysis,
  SynthMedCondition,
  SynthMedConditionSatisfaction,
  SynthMedConditionValidationRequest,
  SynthMedConditionValidationResponse,
  SynthMedDatasetColumns,
  SynthMedEvaluationReport,
  SynthMedGenerationAnalysis,
  SynthMedGenerationJob,
  SynthMedGenerationProfile,
  SynthMedGenerationStatus,
  SynthMedMedicalProfile,
  SynthMedModelName,
  SynthMedModelsResponse,
  SynthMedRejectionSampling,
  SynthMedSchemaValidation,
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

const ClinicalReportCard = ({
  report,
  schema,
  rejection,
}: {
  report: SynthMedClinicalValidationReport;
  schema?: SynthMedSchemaValidation;
  rejection?: SynthMedRejectionSampling;
}) => {
  const counts = report.classificationCounts ?? {};
  const failed = rejection && rejection.rejectedRecords ? rejection.rejectedRecords > 0 : false;
  return (
    <Card>
      <CardHeader
        title="Clinical validation"
        subtitle={report.method ?? 'Configured reference-interval and relationship checks.'}
        action={
          <Badge tone={schema?.passed === false ? 'danger' : failed ? 'warning' : 'success'}>
            {schema?.passed === false ? 'Schema failed' : failed ? 'Records rejected' : 'Checks passed'}
          </Badge>
        }
      />
      <div className="info-list">
        <InfoRow label="Profile">{report.generationProfile ?? 'Standard'}</InfoRow>
        <InfoRow label="Records checked">{formatNumber(report.totalRecords ?? 0)}</InfoRow>
        <InfoRow label="Generated by sampling">{formatNumber(rejection?.acceptedRecords ?? 0)}</InfoRow>
        <InfoRow label="Rejected by sampling">{formatNumber(rejection?.rejectedRecords ?? 0)}</InfoRow>
      </div>
      <div className="chip-grid">
        {Object.entries(counts).map(([classification, count]) => (
          <Badge key={classification} tone={classification === 'normal' ? 'success' : 'warning'}>
            {classification}: {formatNumber(count)}
          </Badge>
        ))}
      </div>
      {schema && !schema.passed ? (
        <Alert tone="danger" title="Strict output schema failed">
          {(schema.errors ?? []).join('; ') || 'The generated columns were not approved for release.'}
        </Alert>
      ) : null}
      {(report.warnings ?? []).length ? (
        <Alert tone="warning" title="Clinical review notes">
          <ul className="activity-list">
            {(report.warnings ?? []).map((item, index) => <li key={index}><span>{item}</span></li>)}
          </ul>
        </Alert>
      ) : null}
      <p className="muted small">
        Reference checks are screening aids for research datasets, not clinical decision support.
      </p>
    </Card>
  );
};

export const SynthMedGenerate = () => {
  const {
    synthSources,
    downloadSynthMedSource,
    analyseSynthMedGeneration,
    listSynthMedModels,
    getSynthMedDatasetColumns,
    listSynthMedClinicalReferences,
    getSynthMedMedicalProfile,
    validateSynthMedSourceClinical,
    validateSynthMedConditions,
    startSynthMedGeneration,
    getSynthMedGenerationJob,
    getSynthMedGenerationJobConditions,
    getSynthMedClinicalReport,
    refreshSynthMed,
  } = useDemo();

  const [searchParams] = useSearchParams();
  const querySourceId = searchParams.get('sourceId') || '';
  const [sourceId, setSourceId] = useState(querySourceId);
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
  const [generationProfile, setGenerationProfile] = useState<SynthMedGenerationProfile>('Standard');
  const enforceStrictSchema = false;
  const [maxSamplingAttempts, setMaxSamplingAttempts] = useState('4');
  const [clinicalReferences, setClinicalReferences] = useState<SynthMedClinicalReference[]>([]);
  const [referencesLoading, setReferencesLoading] = useState(false);
  const [medicalProfile, setMedicalProfile] = useState<SynthMedMedicalProfile | null>(null);
  const [medicalProfileLoading, setMedicalProfileLoading] = useState(false);
  const [medicalProfileError, setMedicalProfileError] = useState('');
  const [clinicalVariables, setClinicalVariables] = useState<SynthMedClinicalVariable[]>([]);
  const [clinicalValidation, setClinicalValidation] = useState<SynthMedClinicalValidationReport | null>(null);
  const [clinicalSchemaValidation, setClinicalSchemaValidation] = useState<SynthMedSchemaValidation | null>(null);
  const [clinicalBusy, setClinicalBusy] = useState(false);
  const [clinicalError, setClinicalError] = useState('');
  const [clinicalReport, setClinicalReport] = useState<SynthMedEvaluationReport | null>(null);

  useEffect(() => {
    const fromParam = searchParams.get('sourceId');
    if (fromParam) {
      setSourceId(fromParam);
    } else if (!sourceId && synthSources.length > 0) {
      setSourceId(synthSources[0].id);
    }
  }, [searchParams, sourceId, synthSources]);

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
    setReferencesLoading(true);
    void listSynthMedClinicalReferences()
      .then((result) => {
        if (active) setClinicalReferences(result.references);
      })
      .catch(() => undefined)
      .finally(() => {
        if (active) setReferencesLoading(false);
      });
    return () => {
      active = false;
    };
  }, [listSynthMedClinicalReferences]);

  useEffect(() => {
    let active = true;
    setMedicalProfile(null);
    setSelectedColumns([]);
    setClinicalValidation(null);
    setClinicalSchemaValidation(null);
    setClinicalError('');
    if (!sourceId) {
      setClinicalVariables([]);
      return;
    }
    setMedicalProfileLoading(true);
    void getSynthMedMedicalProfile(sourceId)
      .then((result) => {
        if (!active) return;
        setMedicalProfile(result.profile);
        setSelectedColumns(result.profile.approvedOutputColumns);
        setValidated(null);
        const ageColumn = result.profile.demographicColumns.find((name) => /age/i.test(name)) ?? '';
        const sexColumn = result.profile.demographicColumns.find((name) => /gender|sex/i.test(name)) ?? '';
        setClinicalVariables(
          result.profile.clinicalMeasurementColumns.map((column) => {
            const detail = result.profile.columns.find((item) => item.originalName === column);
            return {
              column,
              measurement: detail?.standardisedName ?? column,
              unit: detail?.unit ?? '',
              context: detail?.note ?? '',
              ageColumn,
              sexColumn,
              enabled: true,
            };
          }),
        );
      })
      .catch((error: unknown) => {
        if (active) setMedicalProfileError(errorMessage(error));
      })
      .finally(() => {
        if (active) setMedicalProfileLoading(false);
      });
    return () => {
      active = false;
    };
  }, [sourceId, getSynthMedMedicalProfile]);

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
    if (!job || job.status !== 'Completed' || !job.generatedDatasetId) {
      setClinicalReport(null);
      return;
    }
    let active = true;
    if (job.clinicalValidation) {
      setClinicalReport({
        id: '',
        generatedDatasetId: job.generatedDatasetId,
        reportType: 'clinical',
        method: job.clinicalValidation.method ?? '',
        score: null,
        report: job.clinicalValidation as unknown as Record<string, unknown>,
        createdAt: job.completedAt,
      });
      return;
    }
    void getSynthMedClinicalReport(job.generatedDatasetId)
      .then((result) => {
        if (active) setClinicalReport(result);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [
    job?.id,
    job?.status,
    job?.generatedDatasetId,
    job?.clinicalValidation,
    job?.completedAt,
    getSynthMedClinicalReport,
  ]);

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

  const clinicalEnabled = generationProfile !== 'Standard' || enforceStrictSchema;
  const approvedOutputColumns = useMemo(
    () => medicalProfile?.approvedOutputColumns.filter((column) => includedColumns.includes(column)) ?? includedColumns,
    [includedColumns, medicalProfile],
  );
  const excludedOutputColumns = includedColumns.filter((column) => !approvedOutputColumns.includes(column));
  const clinicalMeasurementColumns = useMemo(
    () => clinicalVariables.filter((variable) => variable.enabled !== false).map((variable) => variable.column),
    [clinicalVariables],
  );
  const missingClinicalColumns = clinicalMeasurementColumns.filter((column) => !includedColumns.includes(column));
  const profileReferenceCount = clinicalReferences.filter(
    (reference) => reference.approvalStatus === 'Approved' && reference.available,
  ).length;
  const availableClinicalColumns =
    medicalProfile?.clinicalMeasurementColumns.filter(
      (column) => !clinicalVariables.some((variable) => variable.column === column),
    ) ?? [];

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
        conditionPayload,
        generationProfile,
        enforceStrictSchema,
        clinicalVariables,
        maxSamplingAttempts,
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
      conditionPayload,
      generationProfile,
      enforceStrictSchema,
      clinicalVariables,
      maxSamplingAttempts,
    ],
  );

  const validationStale = conditionalEnabled && validated?.signature !== signature;
  const displayedSatisfaction = conditionReport ? asConditionSatisfaction(conditionReport.report) : null;
  const displayedClinical = clinicalReport?.report as unknown as SynthMedClinicalValidationReport | undefined;
  const displayedClinicalSchema = clinicalReport?.report.schemaValidation as SynthMedSchemaValidation | undefined;
  const displayedRejection = clinicalReport?.report.rejectionSampling as SynthMedRejectionSampling | undefined;

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
  });

  const buildClinicalPayload = () => ({
    sourceDatasetId: analysis?.sourceDatasetId ?? sourceId,
    generationProfile,
    clinicalVariables: clinicalVariables.filter((variable) => variable.enabled !== false),
    referenceOverrides: [],
    diseaseRules: [],
    approvedOutputColumns,
    enforceStrictSchema,
  });

  const runClinicalValidation = async () => {
    setClinicalError('');
    setClinicalValidation(null);
    setClinicalSchemaValidation(null);
    if (!analysis) return;
    if (!clinicalEnabled) {
      setClinicalError('Select a clinical profile or enable strict schema first.');
      return;
    }
    if (missingClinicalColumns.length) {
      setClinicalError(`Clinical variables use unselected columns: ${missingClinicalColumns.join(', ')}.`);
      return;
    }
    setClinicalBusy(true);
    try {
      const result = await validateSynthMedSourceClinical(buildClinicalPayload());
      setClinicalValidation(result.report);
      setClinicalSchemaValidation(result.schemaValidation);
    } catch (error) {
      setClinicalError(errorMessage(error));
    } finally {
      setClinicalBusy(false);
    }
  };

  const updateClinicalVariable = (index: number, patch: Partial<SynthMedClinicalVariable>) => {
    setClinicalVariables((previous) =>
      previous.map((item, position) => (position === index ? { ...item, ...patch } : item)),
    );
    setClinicalValidation(null);
  };

  const addClinicalVariable = () => {
    const column = availableClinicalColumns[0];
    if (!column) return;
    const detail = medicalProfile?.columns.find((item) => item.originalName === column);
    setClinicalVariables((previous) => [
      ...previous,
      {
        column,
        measurement: detail?.standardisedName ?? column,
        unit: detail?.unit ?? '',
        context: detail?.note ?? '',
        ageColumn: previous.find((item) => item.ageColumn)?.ageColumn ?? '',
        sexColumn: previous.find((item) => item.sexColumn)?.sexColumn ?? '',
        enabled: true,
      },
    ]);
    setClinicalValidation(null);
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

    if (medicalProfileLoading) {
      setFormError('Medical column profiling is still in progress.');
      return;
    }
    if (medicalProfileError) {
      setFormError(`Medical column profiling failed: ${medicalProfileError}`);
      return;
    }
    if (approvedOutputColumns.length === 0) {
      setFormError('No approved medical columns were found. Upload a source with clinical measurements, age, gender or disease data.');
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
    const attemptsValue = Number(maxSamplingAttempts);
    if (clinicalEnabled && (!Number.isInteger(attemptsValue) || attemptsValue < 1 || attemptsValue > 50)) {
      setFormError('Maximum sampling attempts must be a whole number between 1 and 50.');
      return;
    }
    if (clinicalEnabled && missingClinicalColumns.length) {
      setFormError(`Clinical variables use unselected columns: ${missingClinicalColumns.join(', ')}.`);
      return;
    }
    if (clinicalEnabled && !clinicalValidation) {
      setFormError('Validate the clinical configuration before starting generation.');
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
        generationProfile,
        enforceStrictSchema,
        approvedOutputColumns,
        clinicalVariables: clinicalEnabled ? clinicalVariables.filter((variable) => variable.enabled !== false) : [],
        referenceOverrides: [],
        diseaseRules: [],
        maxSamplingAttempts: clinicalEnabled ? attemptsValue : undefined,
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
            <Link to="/synthmed/upload">
              <Button variant="secondary" icon={<UploadCloud size={16} />}>
                Upload source dataset
              </Button>
            </Link>
          </div>
        }
      />

      <form className="upload-layout" onSubmit={(event) => void submit(event)}>
        <div className="upload-main">
          <Card>
            <CardHeader title="1. Choose a source" subtitle="Approved medical columns are selected automatically." />
            <Field
              label="Source dataset"
              htmlFor="synthmed-generation-source"
              required
              hint="Only source datasets uploaded by your account are listed."
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
                <div className="profile-summary profile-summary-compact">
                  <div><span>Records</span><strong>{formatNumber(analysis.totalRecords)}</strong></div>
                  <div><span>Columns</span><strong>{formatNumber(analysis.totalColumns)}</strong></div>
                  <div><span>Identifiers</span><strong>{analysis.potentialIdentifierColumns.length}</strong></div>
                </div>
                {medicalProfile ? (
                  <p className="muted small">
                    Using: {approvedOutputColumns.join(', ') || 'no approved medical columns'}
                  </p>
                ) : null}
                {!analysis.generationReady || (medicalProfile && approvedOutputColumns.length === 0) ? (
                  <Alert tone="warning" title="Source needs review">
                    No approved medical columns are available for generation. Choose a source with clinical measurements,
                    age, gender or disease data.
                  </Alert>
                ) : null}
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
              </>
            ) : null}
          </Card>

          <Card>
            <CardHeader
              title="3. Review clinical constraints"
              subtitle="Documented reference intervals, approved output columns and relationship checks."
              action={<Badge tone="purple"><Stethoscope size={14} /> {profileReferenceCount} approved references</Badge>}
            />
            <div className="review-grid">
              <Field
                label="Generation profile"
                htmlFor="synthmed-generation-profile"
              >
                <select
                  id="synthmed-generation-profile"
                  className="input"
                  value={generationProfile}
                  onChange={(event) => {
                    setGenerationProfile(event.target.value as SynthMedGenerationProfile);
                    setClinicalValidation(null);
                  }}
                >
                  <option value="Standard">Standard — legacy statistical generation</option>
                  <option value="NormalRange">Normal Range — documented reference intervals</option>
                  <option value="ClinicalDistribution">Clinical Distribution — plausible abnormal values</option>
                </select>
              </Field>
              {generationProfile !== 'Standard' ? (
                <Field
                  label="Maximum sampling attempts"
                  htmlFor="synthmed-clinical-attempts"
                >
                  <input
                    id="synthmed-clinical-attempts"
                    className="input"
                    type="number"
                    min={1}
                    max={50}
                    value={maxSamplingAttempts}
                    onChange={(event) => setMaxSamplingAttempts(event.target.value)}
                  />
                </Field>
              ) : null}
            </div>

            {generationProfile !== 'Standard' ? (
            <details className="compact-details">
              <summary>Reference catalogue ({profileReferenceCount} approved)</summary>
              <div>
                {referencesLoading ? <LoadingState label="Loading clinical references…" /> : null}
                {clinicalReferences.length ? (
                  <div className="table-wrap">
                    <table className="table table-compact">
                      <thead>
                        <tr>
                          <th>Reference</th>
                          <th>Context</th>
                          <th>Approval</th>
                          <th>Source</th>
                        </tr>
                      </thead>
                      <tbody>
                        {clinicalReferences.map((reference) => (
                          <tr key={reference.key}>
                            <td>
                              <strong>{reference.measurement}</strong>
                              <div className="muted small">{reference.unit} · {reference.population || 'General'}</div>
                            </td>
                            <td>{reference.context || 'Any'}</td>
                            <td>
                              <Badge tone={reference.available ? 'success' : 'warning'}>
                                {reference.approvalStatus}
                              </Badge>
                            </td>
                            <td>
                              {reference.sourceUrl.startsWith('http') ? (
                                <a href={reference.sourceUrl} target="_blank" rel="noreferrer">
                                  {reference.sourceOrganization}
                                </a>
                              ) : (
                                reference.sourceOrganization || '—'
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}
              </div>
            </details>
            ) : null}

            {generationProfile !== 'Standard' ? (
            <>
            {medicalProfileLoading ? <LoadingState label="Profiling clinical columns…" /> : null}
            {medicalProfileError ? <Alert tone="danger" title="Medical profile unavailable">{medicalProfileError}</Alert> : null}
            {medicalProfile ? (
              <>
                <p className="muted small">
                  Measurements: {medicalProfile.clinicalMeasurementColumns.length} · Rules: {clinicalVariables.length}
                  {excludedOutputColumns.length ? ` · Excluded from output: ${excludedOutputColumns.join(', ')}` : ''}
                </p>
                {medicalProfile.columnsRequiringConfirmation.length ? (
                  <p className="muted small">Check units/context: {medicalProfile.columnsRequiringConfirmation.join(', ')}</p>
                ) : null}

                <details className="compact-details">
                  <summary>Clinical variable mapping ({clinicalVariables.length})</summary>
                  <div>
                {clinicalVariables.map((variable, index) => (
                  <div className="review-grid" key={`${variable.column}-${index}`}>
                    <Field label="Column" htmlFor={`clinical-column-${index}`}>
                      <select
                        id={`clinical-column-${index}`}
                        className="input"
                        value={variable.column}
                        onChange={(event) => {
                          const detail = medicalProfile.columns.find((item) => item.originalName === event.target.value);
                          updateClinicalVariable(index, {
                            column: event.target.value,
                            measurement: detail?.standardisedName ?? event.target.value,
                            unit: detail?.unit ?? '',
                          });
                        }}
                      >
                        {medicalProfile.clinicalMeasurementColumns.map((column) => (
                          <option key={column} value={column}>{column}</option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Measurement" htmlFor={`clinical-measurement-${index}`}>
                      <input
                        id={`clinical-measurement-${index}`}
                        className="input"
                        value={variable.measurement}
                        onChange={(event) => updateClinicalVariable(index, { measurement: event.target.value })}
                      />
                    </Field>
                    <Field label="Unit" htmlFor={`clinical-unit-${index}`}>
                      <input
                        id={`clinical-unit-${index}`}
                        className="input"
                        value={variable.unit ?? ''}
                        onChange={(event) => updateClinicalVariable(index, { unit: event.target.value })}
                        placeholder="e.g. mg/dL"
                      />
                    </Field>
                    <Field label="Context" htmlFor={`clinical-context-${index}`}>
                      <input
                        id={`clinical-context-${index}`}
                        className="input"
                        value={variable.context ?? ''}
                        onChange={(event) => updateClinicalVariable(index, { context: event.target.value })}
                        placeholder="fasting / resting"
                      />
                    </Field>
                    <Field label="Age column" htmlFor={`clinical-age-${index}`}>
                      <input
                        id={`clinical-age-${index}`}
                        className="input"
                        value={variable.ageColumn ?? ''}
                        onChange={(event) => updateClinicalVariable(index, { ageColumn: event.target.value })}
                      />
                    </Field>
                    <Field label="Sex column" htmlFor={`clinical-sex-${index}`}>
                      <input
                        id={`clinical-sex-${index}`}
                        className="input"
                        value={variable.sexColumn ?? ''}
                        onChange={(event) => updateClinicalVariable(index, { sexColumn: event.target.value })}
                      />
                    </Field>
                  </div>
                ))}
                  <div className="button-row">
                    <Button
                      type="button"
                      variant="secondary"
                      icon={<Plus size={15} />}
                      disabled={availableClinicalColumns.length === 0}
                      onClick={addClinicalVariable}
                    >
                      Add clinical variable
                    </Button>
                  </div>
                  </div>
                </details>
                <div className="button-row">
                  <Button
                    type="button"
                    icon={<Activity size={15} />}
                    disabled={clinicalBusy || !clinicalEnabled || clinicalVariables.length === 0}
                    onClick={() => void runClinicalValidation()}
                  >
                    {clinicalBusy ? 'Validating…' : 'Validate clinical setup'}
                  </Button>
                </div>
                {missingClinicalColumns.length ? (
                  <Alert tone="warning" title="Unselected clinical columns">
                    Select these columns for training too: {missingClinicalColumns.join(', ')}.
                  </Alert>
                ) : null}
                {clinicalError ? <Alert tone="danger" title="Clinical validation failed">{clinicalError}</Alert> : null}
                {clinicalValidation ? (
                  <ClinicalReportCard
                    report={clinicalValidation}
                    schema={clinicalSchemaValidation ?? undefined}
                  />
                ) : null}
              </>
            ) : null}
            </>
            ) : null}
            {generationProfile === 'Standard' ? (
              <p className="muted small">Approved medical output columns are still enforced.</p>
            ) : null}
          </Card>

          <Card>
            <CardHeader title="4. Configure generation" subtitle={`Training settings and conditions for ${model}.`} />
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
            </div>

            {conditionalEnabled ? (
              <>
                <div className="field">
                  <span className="field-label">Condition mode</span>
                  <label className="check-row">
                    <input type="checkbox" checked={andMode} onChange={(event) => changeAndMode(event.target.checked)} />
                    Combine all conditions with AND for every generated record
                  </label>
                  <p className="muted small">
                    {andMode ? 'All conditions apply to every record.' : 'Each condition samples its own cohort; rows must add up.'}
                  </p>
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
            </div>
          </Card>

          {job ? (
            <>
              <Card>
                <CardHeader
                  title="5. Generation job"
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
                  <InfoRow label="Model">{job.modelName}</InfoRow>
                  <InfoRow label="Records">{formatNumber(job.generatedRecordCount)} of {formatNumber(job.requestedRecordCount)}</InfoRow>
                  <InfoRow label="Conditions">{formatNumber(job.conditions.length)}</InfoRow>
                  <InfoRow label="Seed">{job.seed ?? 'Random'}</InfoRow>
                  {job.completedAt ? <InfoRow label="Completed">{formatDateTime(job.completedAt)}</InfoRow> : null}
                </div>
                {job.status === 'Failed' ? (
                  <Alert tone="danger" title="Generation failed">
                    {job.error || 'The job failed without a detailed message.'}
                  </Alert>
                ) : null}
                {displayedClinical ? (
                  <ClinicalReportCard
                    report={displayedClinical}
                    schema={displayedClinicalSchema}
                    rejection={displayedRejection}
                  />
                ) : null}
                {job.status === 'Completed' && job.generatedDatasetId ? (
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '12px' }}>
                    <Link to={`/synthmed/generated/${job.generatedDatasetId}`}>
                      <Button icon={<ArrowRight size={16} />}>Open generated dataset</Button>
                    </Link>
                  </div>
                ) : null}
              </Card>
              {conditionReportLoading ? <LoadingState label="Loading condition satisfaction…" /> : null}
              {displayedSatisfaction ? <SatisfactionCard satisfaction={displayedSatisfaction} /> : null}
            </>
          ) : null}
        </div>

        <aside className="upload-side">
          <Card>
            <CardHeader title="Privacy & scope" subtitle="Always enforced" />
            <ul className="checklist">
              <li><ShieldCheck size={14} /> Only approved medical columns are generated.</li>
              <li><Cpu size={14} /> Training runs on CPU as a background job.</li>
              <li><FlaskConical size={14} /> Research use only; not a clinical decision tool.</li>
            </ul>
          </Card>
        </aside>
      </form>
    </>
  );
};
