export type Role = 'Administrator' | 'Researcher' | 'Contributor';

export type ThemeMode = 'default' | 'light' | 'dark';

export type AccessLevel = 'Open' | 'Controlled' | 'Restricted';

export type DatasetStatus =
  | 'Available'
  | 'Processing'
  | 'Pending review'
  | 'Changes requested'
  | 'Failed';

export type Domain =
  | "Women's health"
  | 'Paediatric health'
  | 'Maternal & neonatal'
  | 'Adolescent health'
  | 'Reproductive health';

export type FileFormat = 'CSV' | 'XLSX' | 'JSON';

export interface DatasetVersion {
  version: string;
  date: string;
  note: string;
  records: number;
  checksum: string;
  status: 'Current' | 'Superseded';
}

export interface Dataset {
  id: string;
  title: string;
  description: string;
  domain: Domain;
  access: AccessLevel;
  status: DatasetStatus;
  owner: string;
  ownerOrganisation: string;
  format: FileFormat;
  records: number;
  columns: number;
  sizeMb: number;
  createdAt: string;
  updatedAt: string;
  version: string;
  qualityScore: number | null;
  readinessScore: number | null;
  representativenessScore: number | null;
  tags: string[];
  ageRange: string;
  geography: string[];
  ethicsApproved: boolean;
  license: string;
  studyDesign: string;
  collectionPeriod: string;
  dataDictionaryAvailable: boolean;
  consentScope: string;
  checksum: string;
  missingRate: number;
  duplicateRate: number;
  intendedTasks: string[];
  labelColumn: string | null;
  versions: DatasetVersion[];
  isLocalPreview?: boolean;
}

export type QualityDimensionKey =
  | 'completeness'
  | 'validity'
  | 'consistency'
  | 'uniqueness'
  | 'typeCorrectness';

export interface QualityIssue {
  id: string;
  dimension: QualityDimensionKey;
  severity: 'High' | 'Medium' | 'Low';
  field: string;
  description: string;
  affectedRecords: number;
  recommendation: string;
}

export interface QualityReport {
  datasetId: string;
  overall: number;
  grade: 'Excellent' | 'Good' | 'Fair' | 'Poor';
  dimensions: Record<QualityDimensionKey, number>;
  issues: QualityIssue[];
  assessedAt: string;
  rulesVersion: string;
  sampleSize: number;
  method: string;
}

export interface ReadinessCategory {
  key:
    | 'dataQuality'
    | 'featureAvailability'
    | 'labelAvailability'
    | 'missingValues'
    | 'metadataCompleteness'
    | 'documentation'
    | 'representativeness'
    | 'taskSuitability';
  label: string;
  score: number;
  weight: number;
  note: string;
}

export interface ReadinessReport {
  datasetId: string;
  task: string;
  overall: number;
  verdict: 'Ready' | 'Ready with caveats' | 'Not ready';
  categories: ReadinessCategory[];
  limitations: string[];
  recommendations: string[];
  assessedAt: string;
  method: string;
}

export interface RepresentativenessReport {
  datasetId: string;
  ageBands: { label: string; value: number }[];
  pregnancyStages: { label: string; value: number }[];
  paediatricGroups: { label: string; value: number }[];
  geography: { label: string; value: number }[];
  missingAttributes: { attribute: string; detail: string; action: string }[];
  coverageNotes: string[];
  assessedAt: string;
}

export type JobStatus =
  | 'Queued'
  | 'Profiling'
  | 'Review required'
  | 'Approved'
  | 'Processing'
  | 'Running'
  | 'Completed'
  | 'Failed'
  | 'Cancelled'
  | 'Rejected';

export type StageState = 'Queued' | 'Running' | 'Completed' | 'Failed' | 'Awaiting review';

export interface EtlStage {
  key: 'extract' | 'transform' | 'load';
  label: string;
  state: StageState;
  detail: string;
}

export type MappingDecisionType = 'Approved' | 'Rejected' | 'Unmapped';

export interface MappingDecisionInput {
  source: string;
  decision: MappingDecisionType;
  target?: string | null;
  note?: string;
}

export interface MappingSuggestion {
  source: string;
  target: string;
  confidence: number;
  status: string;
  note: string;
  inferredType?: string;
  proposedTarget?: string;
  decision?: MappingDecisionType | null;
  decidedBy?: string | null;
  decidedAt?: string | null;
}

export interface EtlLog {
  time: string;
  level: string;
  stage: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface EtlProfileIssue {
  code: string;
  field?: string;
  severity?: string;
  message: string;
  affected?: number;
  detail?: string;
}

export interface EtlProfileColumn {
  name: string;
  inferred_type: string;
  missing: number;
  missing_pct: number;
  unique_sample: number;
  sample_values: string[];
}

export interface EtlProfile {
  row_count?: number;
  column_count?: number;
  missing_cells?: number;
  missing_pct?: number;
  duplicate_rows?: number;
  duplicate_pct?: number;
  columns?: EtlProfileColumn[];
  issues?: EtlProfileIssue[];
  preview_rows?: Record<string, unknown>[];
}

export interface EtlRowIssue {
  row?: number;
  source?: string;
  target?: string;
  severity?: string;
  code?: string;
  value?: unknown;
  message?: string;
}

export interface EtlTransformationSummary {
  rowsIn?: number | null;
  rowsOut?: number | null;
  errors?: Record<string, number>;
  warnings?: Record<string, number>;
  duplicates?: number | null;
  rowIssues?: EtlRowIssue[];
  profileIssues?: EtlProfileIssue[];
}

export interface EtlJob {
  id: string;
  datasetId: string;
  datasetTitle: string;
  status: JobStatus;
  progress: number;
  stages: EtlStage[];
  logs: EtlLog[];
  startedAt: string;
  finishedAt: string | null;
  rowsIn: number;
  rowsOut: number;
  mappings: MappingSuggestion[];
  currentStage?: string;
  profile?: EtlProfile;
  errorMessage?: string | null;
  approvedAt?: string | null;
  approvedBy?: string | null;
  rejectionReason?: string | null;
  transformationSummary?: EtlTransformationSummary;
}

export type RequestStatus = 'Pending' | 'Approved' | 'Rejected' | 'Withdrawn';

export interface AccessRequest {
  id: string;
  datasetId: string;
  datasetTitle: string;
  requester: string;
  role: Role;
  organisation: string;
  purpose: string;
  projectTitle: string;
  requestedAt: string;
  status: RequestStatus;
  decidedAt: string | null;
  reviewer: string | null;
  decisionNote: string | null;
  direction: 'Incoming' | 'Outgoing';
}

export interface ColumnProfile {
  name: string;
  inferredType: 'Numeric' | 'Date' | 'Boolean' | 'Text' | 'Empty' | 'Mixed';
  missing: number;
  missingPct: number;
  uniqueSample: number;
  sampleValues: string[];
}

export interface ExtractPreview {
  sheetName: string;
  rowCount: number;
  columnCount: number;
  missingCells: number;
  missingPct: number;
  duplicateRows: number;
  duplicatePct: number;
  columns: ColumnProfile[];
  previewRows: Record<string, unknown>[];
}

export interface UploadMetadata {
  title: string;
  description: string;
  domain: Domain;
  access: AccessLevel;
  tags: string[];
  ageRange: string;
  geography: string;
  studyDesign: string;
  license: string;
  ethicsApproved: boolean;
  dataDictionaryAvailable: boolean;
  intendedTasks: string[];
  labelColumn: string;
}

export interface CurrentUser {
  name: string;
  email: string;
  phone?: string | null;
  role: Role;
  organisation: string;
  title: string;
}

export interface SynthMedSourceDataset {
  id: string;
  datasetName: string;
  description: string;
  originalFilename: string;
  fileFormat: FileFormat;
  fileSizeBytes: number;
  uploadDate: string;
  uploadedBy: string;
  uploadStatus: string;
  checksumSha256: string;
  rowCount: number;
  columnCount: number;
}

export type SynthMedModelName = 'CTGAN' | 'TVAE' | 'GaussianCopula';

export type SynthMedGenerationMode = 'Unconditional' | 'Conditional';

export interface SynthMedModelCapability {
  model: SynthMedModelName;
  sdvClass: string;
  samplingApi: string;
  conditionalSampling: boolean;
  multipleConditions: boolean;
  exactEquality: boolean;
  rangeOperators: boolean;
  primaryKeyConditions: boolean;
  missingValueConditions: boolean;
  unconditionalSampling?: boolean;
  implemented?: boolean;
  sdvVersion?: string;
  samplingStrategy: string;
  notes: string[];
}

export interface SynthMedModelsResponse {
  models: SynthMedModelCapability[];
  sdvVersion: string;
  message: string;
}

export interface SynthMedEligibleColumn {
  name: string;
  sdtype: string;
  missingCount: number;
  uniqueCount: number;
}

export interface SynthMedIneligibleColumn {
  name: string;
  reason: string;
}

export interface SynthMedDatasetColumns {
  sourceDatasetId: string;
  totalColumns: number;
  eligibleColumns: SynthMedEligibleColumn[];
  ineligibleColumns: SynthMedIneligibleColumn[];
  numericalColumns: string[];
  categoricalColumns: string[];
  booleanColumns: string[];
  datetimeColumns: string[];
  potentialIdentifierColumns: string[];
  generationReady: boolean;
  guidance: string;
}

export type SynthMedConditionOperator = 'eq';

export interface SynthMedCondition {
  column: string;
  operator: SynthMedConditionOperator;
  value: string | number | boolean;
  numRows: number;
}

export interface SynthMedConditionValidationRequest {
  sourceDatasetId: string;
  model: SynthMedModelName;
  conditions: SynthMedCondition[];
  recordCount?: number | null;
  selectedColumns?: string[] | null;
  identifierColumns: string[];
  primaryKey: string | null;
  categoricalColumns: string[];
  numericalColumns: string[];
  preserveMissingness: boolean;
  categoricalValues?: Record<string, string[]>;
  numericRanges?: Record<string, { min?: number | null; max?: number | null }>;
}

export interface SynthMedConditionValidationResponse {
  valid: boolean;
  model: string;
  capabilities: SynthMedModelCapability;
  eligibleColumns: SynthMedEligibleColumn[];
  ineligibleColumns: SynthMedIneligibleColumn[];
  normalizedConditions: Record<string, unknown>[];
  samplingPlan: Record<string, unknown>[];
  errors: string[];
  warnings: string[];
}

export interface SynthMedConditionResult {
  index: number;
  column: string;
  operator: string;
  requestedValue: unknown;
  requestedRows: number;
  totalGeneratedRecords: number;
  satisfyingRecords: number;
  nonSatisfyingRecords: number;
  satisfactionPercentage: number;
}

export interface SynthMedConditionCohort {
  index: number;
  mode: string;
  conditions: { column: string; operator: string; value: unknown }[];
  requestedRows: number;
  totalGeneratedRecords: number;
  satisfyingRecords: number;
  nonSatisfyingRecords: number;
  satisfactionPercentage: number;
  passed: boolean;
}

export interface SynthMedConditionSummary {
  requestedConditions?: number;
  totalGeneratedRecords: number;
  satisfyingRecords: number;
  nonSatisfyingRecords: number;
  satisfactionPercentage: number;
}

export interface SynthMedConditionSatisfaction {
  method?: string;
  conditional?: boolean;
  requestedConditions?: SynthMedCondition[];
  conditions?: SynthMedConditionResult[];
  cohorts?: SynthMedConditionCohort[];
  combined?: SynthMedConditionSummary;
  generatedRecordCount?: number;
  expectedRecordCount?: number;
  recordCountMatches?: boolean;
  allConditionsSatisfied?: boolean;
  passed?: boolean;
  limitations?: string[];
}

export interface SynthMedGeneratedEvaluationSummary {
  generatedDatasetId?: string;
  generationMode: SynthMedGenerationMode;
  selectedModel: SynthMedModelName;
  availableReports: string[];
  quality: Record<string, unknown> | null;
  privacy: Record<string, unknown> | null;
  conditions: SynthMedConditionSatisfaction | null;
  clinical?: SynthMedClinicalReportBundle | null;
  generationProfile?: SynthMedGenerationProfile;
  limitations?: string[];
}

export interface SynthMedGeneratedMetadata {
  model?: string;
  modelName?: string;
  generationMode?: string;
  requestedConditions?: SynthMedCondition[];
  conditionSatisfaction?: SynthMedConditionSatisfaction;
  generationDurationSeconds?: number | null;
  recordCount?: number;
  generationProfile?: SynthMedGenerationProfile;
  clinicalValidation?: SynthMedClinicalValidationReport;
  schemaValidation?: SynthMedSchemaValidation;
  rejectionSampling?: SynthMedRejectionSampling;
  clinicalVariables?: SynthMedClinicalVariable[];
  referenceOverrides?: SynthMedReferenceOverride[];
  diseaseRules?: SynthMedClinicalRule[];
  approvedOutputColumns?: string[];
  excludedOutputColumns?: string[];
  status?: string;
}

export interface SynthMedGeneratedDataset {
  id: string;
  sourceDatasetId: string;
  datasetName: string;
  sourceDatasetName: string;
  generationMethod: string;
  generationMode?: SynthMedGenerationMode;
  selectedModel?: SynthMedModelName;
  recordCount: number;
  columnCount: number;
  generationDate: string;
  fileFormat: FileFormat;
  fileSizeBytes: number;
  fileName: string;
  status: string;
}

export interface SynthMedDownloads {
  sources: SynthMedSourceDataset[];
  generated: SynthMedGeneratedDataset[];
}

export type SynthMedGenerationStatus =
  | 'Queued'
  | 'Preprocessing'
  | 'Training'
  | 'Generating'
  | 'Validating'
  | 'Evaluating'
  | 'Completed'
  | 'Failed';

export type SynthMedColumnKind = 'numerical' | 'categorical' | 'datetime' | 'boolean' | 'unknown';

export interface SynthMedColumnAnalysis {
  name: string;
  dtype: string;
  kind: SynthMedColumnKind;
  missingCount: number;
  missingPercentage: number;
  uniqueCount: number;
  constant: boolean;
  potentialIdentifier: boolean;
  quasiIdentifier: boolean;
}

export interface SynthMedGenerationAnalysis {
  sourceDatasetId: string;
  datasetName: string;
  originalFilename: string;
  totalRecords: number;
  totalColumns: number;
  columns: SynthMedColumnAnalysis[];
  numericalColumns: string[];
  categoricalColumns: string[];
  datetimeColumns: string[];
  booleanColumns: string[];
  potentialIdentifierColumns: string[];
  quasiIdentifierColumns: string[];
  constantColumns: string[];
  duplicateRecords: number;
  generationReady: boolean;
  guidance: string;
}

export type SynthMedGenerationProfile = 'Standard' | 'NormalRange' | 'ClinicalDistribution';

export interface SynthMedClinicalVariable {
  column: string;
  measurement: string;
  unit?: string;
  context?: string;
  referenceKey?: string;
  ageColumn?: string;
  sexColumn?: string;
  pregnantColumn?: string;
  ageYears?: number | null;
  sex?: string;
  pregnant?: boolean | null;
  enabled?: boolean;
}

export interface SynthMedReferenceOverride {
  key: string;
  active?: boolean;
  lower?: number | null;
  upper?: number | null;
  plausibleLower?: number | null;
  plausibleUpper?: number | null;
  approvalStatus?: 'Approved' | 'PendingReview' | 'Unavailable';
  sourceOrganization?: string;
  sourceUrl?: string;
  citation?: string;
  version?: string;
  date?: string;
}

export interface SynthMedClinicalRule {
  disease: string;
  column: string;
  min?: number | null;
  max?: number | null;
  source?: string;
  reviewed?: boolean;
}

export interface SynthMedMedicalProfileColumn {
  originalName: string;
  standardisedName: string;
  role: string;
  kind: string;
  unit: string;
  unitEvidence: string;
  requiresUnitConfirmation: boolean;
  potentialIdentifier: boolean;
  approved: boolean;
  note: string;
}

export interface SynthMedMedicalProfile {
  sourceDatasetId?: string;
  datasetName?: string;
  totalColumns: number;
  columns: SynthMedMedicalProfileColumn[];
  demographicColumns: string[];
  diseaseColumns: string[];
  diseaseLevelColumns: string[];
  clinicalMeasurementColumns: string[];
  columnsRequiringConfirmation: string[];
  excludedIdentifierColumns: string[];
  approvedOutputColumns: string[];
  warnings: string[];
  limitations: string[];
}

export interface SynthMedClinicalReference {
  key: string;
  measurement: string;
  unit: string;
  population: string;
  context: string;
  sourceOrganization: string;
  sourceUrl: string;
  citation: string;
  version: string;
  date: string;
  approvalStatus: 'Approved' | 'PendingReview' | 'Unavailable';
  available: boolean;
  lower?: number | null;
  upper?: number | null;
  lowerInclusive?: boolean;
  upperInclusive?: boolean;
  plausibleLower?: number | null;
  plausibleUpper?: number | null;
  reason?: string;
  notes?: string[];
}

export interface SynthMedClinicalValidationReport {
  method?: string;
  generationProfile?: string;
  totalRecords?: number;
  classificationCounts?: Record<string, number>;
  variables?: Record<string, unknown>[];
  relationships?: Record<string, unknown>[];
  diseaseConsistency?: Record<string, unknown>[];
  warnings?: string[];
  limitations?: string[];
}

export interface SynthMedSchemaValidation {
  passed: boolean;
  errors: string[];
  approvedColumns?: string[];
  prohibitedIdentifierColumns?: string[];
  unapprovedColumns?: string[];
}

export interface SynthMedRejectionSampling {
  method?: string;
  generationProfile?: SynthMedGenerationProfile;
  attempts?: number;
  maxAttempts?: number;
  sampledRecords?: number;
  acceptedRecords?: number;
  rejectedRecords?: number;
  rejectionCounts?: Record<string, number>;
  limitations?: string[];
}

export interface SynthMedClinicalReportBundle {
  clinicalValidation: SynthMedClinicalValidationReport;
  schemaValidation: SynthMedSchemaValidation;
  rejectionSampling: SynthMedRejectionSampling;
}

export interface SynthMedClinicalReferencesResponse {
  references: SynthMedClinicalReference[];
  count: number;
  message?: string;
}

export interface SynthMedMedicalProfileResponse {
  sourceDatasetId: string;
  datasetName: string;
  profile: SynthMedMedicalProfile;
  message?: string;
}

export interface SynthMedSourceClinicalValidationResponse {
  sourceDatasetId: string;
  generatedDatasetId?: string;
  generationProfile: SynthMedGenerationProfile;
  report: SynthMedClinicalValidationReport;
  schemaValidation: SynthMedSchemaValidation;
  warnings?: string[];
}

export interface SynthMedGenerationStartPayload {
  sourceDatasetId: string;
  datasetName: string;
  model: SynthMedModelName;
  generationMode: SynthMedGenerationMode;
  conditions: SynthMedCondition[];
  selectedColumns: string[];
  categoricalColumns: string[];
  numericalColumns: string[];
  identifierColumns: string[];
  primaryKey: string | null;
  seed: number | null;
  epochs: number;
  batchSize: number;
  recordCount: number;
  preserveMissingness: boolean;
  generationProfile?: SynthMedGenerationProfile;
  enforceStrictSchema?: boolean;
  approvedOutputColumns?: string[];
  clinicalVariables?: SynthMedClinicalVariable[];
  referenceOverrides?: SynthMedReferenceOverride[];
  diseaseRules?: SynthMedClinicalRule[];
  maxSamplingAttempts?: number;
}

export interface SynthMedGenerationJob {
  id: string;
  sourceDatasetId: string;
  generatedDatasetId: string;
  status: SynthMedGenerationStatus;
  modelName: string;
  generationMode: SynthMedGenerationMode;
  selectedModel: SynthMedModelName;
  epochs: number;
  batchSize: number;
  seed: number | null;
  requestedRecordCount: number;
  generatedRecordCount: number;
  trainingDurationSeconds: number | null;
  conditions: SynthMedCondition[];
  conditionValidation: SynthMedConditionValidationResponse | Record<string, unknown>;
  conditionSatisfaction: SynthMedConditionSatisfaction | Record<string, unknown>;
  createdAt: string;
  startedAt: string;
  completedAt: string;
  error: string;
  config: Record<string, unknown>;
  generationProfile?: SynthMedGenerationProfile;
  clinicalValidation?: SynthMedClinicalValidationReport;
  schemaValidation?: SynthMedSchemaValidation;
}

export interface SynthMedGeneratedDatasetDetail extends SynthMedGeneratedDataset {
  generationJobId: string;
  modelName: string;
  generationMode?: SynthMedGenerationMode;
  selectedModel?: SynthMedModelName;
  trainingDurationSeconds: number | null;
  availableFormats: FileFormat[];
  reportTypes: string[];
  trainingConfig: {
    model?: SynthMedModelName;
    samplingStrategy?: string;
    epochs: number | null;
    batchSize: number | null;
    seed: number | null;
    preserveMissingness: boolean;
    includedColumns: string[];
  };
  conditions: SynthMedCondition[];
  conditionSatisfaction: SynthMedConditionSatisfaction | Record<string, unknown>;
  generationProfile?: SynthMedGenerationProfile;
  clinicalValidation?: SynthMedClinicalValidationReport;
  schemaValidation?: SynthMedSchemaValidation;
}

export interface SynthMedGeneratedPreview {
  generatedDatasetId: string;
  columns: string[];
  rows: Record<string, unknown>[];
  totalRecords: number;
  page: number;
  pageSize: number;
}

export interface SynthMedEvaluationReport {
  id: string;
  generatedDatasetId: string;
  reportType: string;
  method: string;
  score: number | null;
  report: Record<string, unknown>;
  createdAt: string;
  generationMode?: SynthMedGenerationMode;
  selectedModel?: SynthMedModelName;
  conditions?: SynthMedCondition[];
}

export interface SynthMedExportResponse {
  generatedDatasetId: string;
  format: FileFormat;
  fileName: string;
}

export interface SynthMedComparisonCreatePayload {
  sourceDatasetId: string;
  generatedDatasetId: string;
  name: string;
}

export interface SynthMedComparisonChartPoint {
  bucket?: string;
  category?: string;
  original: number;
  synthetic: number;
}

export interface SynthMedComparisonChart {
  column: string;
  kind: 'numerical' | 'categorical' | string;
  title: string;
  points: SynthMedComparisonChartPoint[];
}

export interface SynthMedComparisonColumnMetric {
  name: string;
  sourceKind: string;
  syntheticKind: string;
  shared: boolean;
  similarity: number | null;
  metric: string;
  sourceMissingPercentage: number;
  syntheticMissingPercentage: number;
  sourceUniqueCount: number;
  syntheticUniqueCount: number;
  sourceStats: Record<string, unknown>;
  syntheticStats: Record<string, unknown>;
}

export interface SynthMedComparisonSummary {
  sourceRows: number;
  syntheticRows: number;
  rowDifference: number;
  sourceColumns: number;
  syntheticColumns: number;
  sharedColumns: number;
  onlySourceColumns: string[];
  onlySyntheticColumns: string[];
  overallSimilarity: number | null;
  numericSimilarity: number | null;
  categoricalSimilarity: number | null;
  missingnessDeltaPercentage: number | null;
}

export interface SynthMedComparisonListItem {
  id: string;
  name: string;
  sourceDatasetId: string;
  sourceDatasetName: string;
  generatedDatasetId: string;
  generatedDatasetName: string;
  summary: SynthMedComparisonSummary;
  createdAt: string;
  createdBy: string;
  reportAvailable: boolean;
  generatedMetadata?: SynthMedGeneratedMetadata;
}

export interface SynthMedComparisonClinical {
  generationProfile: SynthMedGenerationProfile;
  sourceMedicalProfile: SynthMedMedicalProfile;
  syntheticMedicalProfile: SynthMedMedicalProfile;
  sourceValidation: SynthMedClinicalValidationReport;
  syntheticValidation: SynthMedClinicalValidationReport;
  schemaValidation: SynthMedSchemaValidation;
  rejectionSampling: SynthMedRejectionSampling;
  limitations: string[];
}

export interface SynthMedComparisonDetail extends SynthMedComparisonListItem {
  method: string;
  columns: SynthMedComparisonColumnMetric[];
  charts: SynthMedComparisonChart[];
  limitations: string[];
  clinical?: SynthMedComparisonClinical | null;
}

export interface ToastMessage {
  id: string;
  type: 'success' | 'error' | 'info';
  title: string;
  message?: string;
}
