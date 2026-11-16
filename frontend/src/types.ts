export type Role = 'Administrator' | 'Researcher' | 'Contributor';

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

export type StageState = 'Queued' | 'Running' | 'Completed' | 'Failed' | 'Awaiting review';

export interface EtlStage {
  key: 'extract' | 'transform' | 'load';
  label: string;
  state: StageState;
  detail: string;
}

export interface MappingSuggestion {
  source: string;
  target: string;
  confidence: number;
  status: 'Approved' | 'Suggested' | 'Unmapped';
  note: string;
}

export interface EtlJob {
  id: string;
  datasetId: string;
  datasetTitle: string;
  status: 'Queued' | 'Running' | 'Completed' | 'Failed' | 'Review required';
  progress: number;
  stages: EtlStage[];
  logs: { time: string; level: 'INFO' | 'WARN' | 'ERROR'; stage: string; message: string }[];
  startedAt: string;
  finishedAt: string | null;
  rowsIn: number;
  rowsOut: number;
  mappings: MappingSuggestion[];
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
  role: Role;
  organisation: string;
  title: string;
}

export interface ToastMessage {
  id: string;
  type: 'success' | 'error' | 'info';
  title: string;
  message?: string;
}
