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

export interface SynthMedGeneratedDataset {
  id: string;
  sourceDatasetId: string;
  datasetName: string;
  sourceDatasetName: string;
  generationMethod: string;
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

export interface SynthMedGenerationStartPayload {
  sourceDatasetId: string;
  datasetName: string;
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
}

export interface SynthMedGenerationJob {
  id: string;
  sourceDatasetId: string;
  generatedDatasetId: string;
  status: SynthMedGenerationStatus;
  modelName: string;
  epochs: number;
  batchSize: number;
  seed: number | null;
  requestedRecordCount: number;
  generatedRecordCount: number;
  trainingDurationSeconds: number | null;
  createdAt: string;
  startedAt: string;
  completedAt: string;
  error: string;
  config: Record<string, unknown>;
}

export interface SynthMedGeneratedDatasetDetail extends SynthMedGeneratedDataset {
  generationJobId: string;
  modelName: string;
  trainingDurationSeconds: number | null;
  availableFormats: FileFormat[];
  reportTypes: string[];
  trainingConfig: {
    epochs: number | null;
    batchSize: number | null;
    seed: number | null;
    preserveMissingness: boolean;
    includedColumns: string[];
  };
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
}

export interface SynthMedComparisonDetail extends SynthMedComparisonListItem {
  method: string;
  columns: SynthMedComparisonColumnMetric[];
  charts: SynthMedComparisonChart[];
  limitations: string[];
}

export interface ToastMessage {
  id: string;
  type: 'success' | 'error' | 'info';
  title: string;
  message?: string;
}
