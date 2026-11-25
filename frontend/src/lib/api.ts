import type {
  AccessLevel,
  AccessRequest,
  CurrentUser,
  Dataset,
  DatasetLineageResponse,
  DatasetVersionComparison,
  DatasetVersionRecord,
  DatasetVersionsResponse,
  Domain,
  EtlJob,
  FileFormat,
  MappingDecisionInput,
  QualityReport,
  ReadinessReport,
  RepresentativenessReport,
  ResearchReport,
  ResearchReportGeneratePayload,
  ResearchReportListResponse,
  ResearchReportStatusResponse,
  ResearchReportType,
  Role,
  SynthMedComparisonCreatePayload,
  SynthMedComparisonDetail,
  SynthMedClinicalReferencesResponse,
  SynthMedClinicalRule,
  SynthMedClinicalVariable,
  SynthMedComparisonListItem,
  SynthMedConditionValidationRequest,
  SynthMedConditionValidationResponse,
  SynthMedDatasetColumns,
  SynthMedDatasetLineageResponse,
  SynthMedDownloads,
  SynthMedEvaluationReport,
  SynthMedConfigSnapshot,
  SynthMedExperimentCreatePayload,
  SynthMedExperimentHistory,
  SynthMedExperimentReusePayload,
  SynthMedExperimentResponse,
  SynthMedExperimentReport,
  SynthMedExportResponse,
  SynthMedGeneratedDataset,
  SynthMedGeneratedDatasetDetail,
  SynthMedGeneratedDatasetRegisterPayload,
  SynthMedGeneratedEvaluationSummary,
  SynthMedGeneratedPreview,
  SynthMedGenerationAnalysis,
  SynthMedGenerationJob,
  SynthMedGenerationProfile,
  SynthMedGenerationStartPayload,
  SynthMedMedicalProfileResponse,
  SynthMedModelName,
  SynthMedModelsResponse,
  SynthMedReferenceOverride,
  SynthMedRegisterResponse,
  SynthMedSourceClinicalValidationResponse,
  SynthMedSourceDataset,
  SynthMedUtilityEvaluation,
  SynthMedUtilityEvaluationCreatePayload,
  SynthMedVersionComparison,
  SynthMedVersionResponse,
} from '../types';

const RAW_BASE = (import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000')
  .replace(/\/+$/, '')
  .replace(/^http:\/\/localhost:8000$/i, 'http://127.0.0.1:8000');
const API_ROOT = RAW_BASE.endsWith('/api/v1') ? RAW_BASE : `${RAW_BASE}/api/v1`;
const TOKEN_KEY = 'meddatahub.access_token';

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export const tokenStore = {
  get: () => window.localStorage.getItem(TOKEN_KEY),
  set: (token: string) => window.localStorage.setItem(TOKEN_KEY, token),
  clear: () => window.localStorage.removeItem(TOKEN_KEY),
};

const errorDetail = async (response: Response): Promise<string> => {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === 'string') return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((item) => (typeof item === 'object' && item && 'msg' in item ? String(item.msg) : String(item)))
        .join('; ');
    }
  } catch {
    return response.statusText || 'Request failed';
  }
  return response.statusText || 'Request failed';
};

const detailFromText = (text: string, fallback: string): string => {
  try {
    const body = JSON.parse(text) as { detail?: unknown };
    if (typeof body.detail === 'string') return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((item) => (typeof item === 'object' && item && 'msg' in item ? String(item.msg) : String(item)))
        .join('; ');
    }
  } catch {
    return fallback || 'Request failed';
  }
  return fallback || 'Request failed';
};

const request = async <T>(path: string, options: RequestInit = {}): Promise<T> => {
  const headers = new Headers(options.headers);
  const token = tokenStore.get();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const response = await fetch(`${API_ROOT}${path}`, { ...options, headers });
  if (!response.ok) {
    const message = await errorDetail(response);
    if (response.status === 401) {
      tokenStore.clear();
      window.dispatchEvent(new Event('meddatahub:unauthorized'));
    }
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
};

const uploadWithProgress = <T>(
  path: string,
  form: FormData,
  onProgress: (percent: number) => void,
): Promise<T> =>
  new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_ROOT}${path}`);
    const token = tokenStore.get();
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress(100);
        try {
          resolve(JSON.parse(xhr.responseText) as T);
        } catch (error) {
          reject(error);
        }
        return;
      }
      if (xhr.status === 401) {
        tokenStore.clear();
        window.dispatchEvent(new Event('meddatahub:unauthorized'));
      }
      reject(new ApiError(xhr.status, detailFromText(xhr.responseText, xhr.statusText)));
    };
    xhr.onerror = () => reject(new ApiError(0, 'Network error during upload'));
    xhr.send(form);
  });

const downloadBlob = async (path: string, filename: string): Promise<void> => {
  const token = tokenStore.get();
  const response = await fetch(`${API_ROOT}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!response.ok) {
    const message = await errorDetail(response);
    if (response.status === 401) {
      tokenStore.clear();
      window.dispatchEvent(new Event('meddatahub:unauthorized'));
    }
    throw new ApiError(response.status, message);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
};

interface ApiUser {
  id: string;
  email: string;
  phone_number: string | null;
  full_name: string;
  role: Role;
  organisation: string;
  title: string;
  is_active: boolean;
}

interface ApiTokenResponse {
  access_token: string;
  expires_in: number;
  user: ApiUser;
}

interface ApiDataset {
  id: string;
  title: string;
  description: string;
  domain: string;
  access: AccessLevel;
  status: Dataset['status'];
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
  versions: Dataset['versions'];
}

interface ApiUploadResponse {
  dataset: ApiDataset;
  jobId: string;
  message: string;
}

interface ApiReportsResponse {
  quality: QualityReport | null;
  readiness: ReadinessReport | null;
  representativeness: RepresentativenessReport | null;
}

export interface SynthMedUploadPayload {
  file: File;
  datasetName: string;
  description: string;
}

export interface SynthMedSourceClinicalValidationPayload {
  sourceDatasetId: string;
  generationProfile: SynthMedGenerationProfile;
  clinicalVariables: SynthMedClinicalVariable[];
  referenceOverrides: SynthMedReferenceOverride[];
  diseaseRules: SynthMedClinicalRule[];
  approvedOutputColumns?: string[];
  enforceStrictSchema?: boolean;
}

export interface UploadPayload {
  file?: File;
  format?: FileFormat;
  generatedDatasetId?: string;
  title: string;
  description: string;
  domain: Domain;
  access: AccessLevel;
  tags: string[];
  ageRange: string;
  geography: string[];
  studyDesign: string;
  license: string;
  ethicsApproved: boolean;
  dataDictionaryAvailable: boolean;
  intendedTasks: string[];
  labelColumn: string;
  researchTask: string;
}

export const toCurrentUser = (user: ApiUser): CurrentUser => ({
  name: user.full_name,
  email: user.email,
  phone: user.phone_number,
  role: user.role,
  organisation: user.organisation,
  title: user.title,
});

const toDataset = (dataset: ApiDataset): Dataset => ({ ...dataset, domain: dataset.domain as Domain });

const toReportKeyed = <T extends { datasetId: string }>(items: T[]): Record<string, T> =>
  Object.fromEntries(items.map((item) => [item.datasetId, item]));

const RESEARCH_REPORT_ENDPOINTS: Record<ResearchReportType, string> = {
  'dataset-profile': '/reports/dataset-profile',
  etl: '/reports/etl',
  'synthmed-generation': '/reports/synthmed/generation',
  'synthmed-comparison': '/reports/synthmed/comparison',
  'synthmed-privacy': '/reports/synthmed/privacy',
  'synthmed-utility': '/reports/synthmed/utility',
  'synthmed-experiment': '/reports/synthmed/experiment',
};

export const api = {
  login: async (email: string, password: string): Promise<CurrentUser> => {
    const response = await request<ApiTokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    tokenStore.set(response.access_token);
    return toCurrentUser(response.user);
  },

  register: async (input: {
    email: string;
    password: string;
    fullName: string;
    phoneNumber?: string;
    organisation: string;
    title: string;
  }): Promise<CurrentUser> => {
    await request<ApiUser>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({
        email: input.email,
        password: input.password,
        full_name: input.fullName,
        phone_number: input.phoneNumber?.trim() || null,
        organisation: input.organisation,
        title: input.title,
      }),
    });
    return api.login(input.email, input.password);
  },

  me: async (): Promise<CurrentUser> => toCurrentUser(await request<ApiUser>('/auth/me')),

  updateProfile: async (input: {
    fullName: string;
    phoneNumber?: string;
    organisation: string;
    title: string;
  }): Promise<CurrentUser> =>
    toCurrentUser(
      await request<ApiUser>('/auth/me', {
        method: 'PATCH',
        body: JSON.stringify({
          full_name: input.fullName,
          phone_number: input.phoneNumber?.trim() || null,
          organisation: input.organisation,
          title: input.title,
        }),
      }),
    ),

  changePassword: async (currentPassword: string, newPassword: string): Promise<void> => {
    await request<void>('/auth/me/password', {
      method: 'POST',
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
  },

  requestPasswordReset: async (email: string): Promise<string> => {
    const response = await request<{ message: string }>('/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email }),
    });
    return response.message;
  },

  verifyPasswordReset: async (email: string, otp: string, newPassword: string): Promise<void> => {
    await request<void>('/auth/forgot-password/verify', {
      method: 'POST',
      body: JSON.stringify({ email, otp, new_password: newPassword }),
    });
  },

  listDatasets: async (): Promise<Dataset[]> =>
    (await request<ApiDataset[]>('/datasets/')).map(toDataset),

  getDataset: async (datasetId: string): Promise<Dataset> =>
    toDataset(await request<ApiDataset>(`/datasets/${encodeURIComponent(datasetId)}`)),

  uploadDataset: async (payload: UploadPayload): Promise<{ dataset: Dataset; jobId: string }> => {
    const form = new FormData();
    if (payload.file) form.append('file', payload.file);
    if (payload.generatedDatasetId) form.append('generated_dataset_id', payload.generatedDatasetId);
    form.append(
      'metadata',
      JSON.stringify({
        title: payload.title,
        description: payload.description,
        domain: payload.domain,
        access: payload.access,
        tags: payload.tags,
        age_range: payload.ageRange,
        geography: payload.geography,
        study_design: payload.studyDesign,
        license: payload.license,
        ethics_approved: payload.ethicsApproved,
        data_dictionary_available: payload.dataDictionaryAvailable,
        intended_tasks: payload.intendedTasks,
        label_column: payload.labelColumn || null,
        research_task: payload.researchTask,
      }),
    );
    const response = await request<ApiUploadResponse>('/datasets/', { method: 'POST', body: form });
    return { dataset: toDataset(response.dataset), jobId: response.jobId };
  },

  approveDataset: async (datasetId: string, reason: string): Promise<Dataset> =>
    toDataset(
      await request<ApiDataset>(`/datasets/${encodeURIComponent(datasetId)}/approve`, {
        method: 'POST',
        body: JSON.stringify({ reason }),
      }),
    ),

  rejectDataset: async (datasetId: string, reason: string): Promise<Dataset> =>
    toDataset(
      await request<ApiDataset>(`/datasets/${encodeURIComponent(datasetId)}/reject`, {
        method: 'POST',
        body: JSON.stringify({ reason }),
      }),
    ),

  listJobs: async (): Promise<EtlJob[]> => request<EtlJob[]>('/etl/jobs'),

  getJob: async (jobId: string): Promise<EtlJob> => request<EtlJob>(`/etl/jobs/${encodeURIComponent(jobId)}`),

  profileJob: async (jobId: string): Promise<EtlJob> =>
    request<EtlJob>(`/etl/jobs/${encodeURIComponent(jobId)}/profile`, { method: 'POST' }),

  recordMappingDecisions: async (jobId: string, decisions: MappingDecisionInput[]): Promise<EtlJob> =>
    request<EtlJob>(`/etl/jobs/${encodeURIComponent(jobId)}/mappings`, {
      method: 'POST',
      body: JSON.stringify(decisions),
    }),

  approveMappings: async (jobId: string, note = ''): Promise<EtlJob> =>
    request<EtlJob>(`/etl/jobs/${encodeURIComponent(jobId)}/approve`, {
      method: 'POST',
      body: JSON.stringify({ note }),
    }),

  runJob: async (jobId: string, task: string): Promise<{ jobId: string; status: string; message: string }> =>
    request<{ jobId: string; status: string; message: string }>(
      `/etl/jobs/${encodeURIComponent(jobId)}/run`,
      { method: 'POST', body: JSON.stringify({ task }) },
    ),

  cancelJob: async (jobId: string): Promise<EtlJob> =>
    request<EtlJob>(`/etl/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' }),

  rejectJob: async (jobId: string, reason: string): Promise<EtlJob> =>
    request<EtlJob>(`/etl/jobs/${encodeURIComponent(jobId)}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),

  getReports: async (datasetId: string): Promise<ApiReportsResponse> =>
    request<ApiReportsResponse>(`/datasets/${encodeURIComponent(datasetId)}/reports`),

  createReadiness: async (datasetId: string, task: string): Promise<ReadinessReport> =>
    request<ReadinessReport>(`/datasets/${encodeURIComponent(datasetId)}/readiness`, {
      method: 'POST',
      body: JSON.stringify({ task }),
    }),

  listAccessRequests: async (): Promise<AccessRequest[]> => request<AccessRequest[]>('/access-requests'),

  requestAccess: async (
    datasetId: string,
    input: { projectTitle: string; purpose: string },
  ): Promise<AccessRequest> =>
    request<AccessRequest>(`/datasets/${encodeURIComponent(datasetId)}/access-requests`, {
      method: 'POST',
      body: JSON.stringify(input),
    }),

  decideAccessRequest: async (
    requestId: string,
    status: 'Approved' | 'Rejected',
    note: string,
  ): Promise<AccessRequest> =>
    request<AccessRequest>(`/access-requests/${encodeURIComponent(requestId)}`, {
      method: 'PATCH',
      body: JSON.stringify({ status, note }),
    }),

  withdrawAccessRequest: async (requestId: string): Promise<AccessRequest> =>
    request<AccessRequest>(`/access-requests/${encodeURIComponent(requestId)}/withdraw`, {
      method: 'POST',
    }),

  downloadDataset: async (dataset: Dataset): Promise<void> =>
    downloadBlob(
      `/datasets/${encodeURIComponent(dataset.id)}/download`,
      `${dataset.title.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}.${dataset.format.toLowerCase()}`,
    ),

  listDatasetVersions: async (datasetId: string): Promise<DatasetVersionsResponse> =>
    request<DatasetVersionsResponse>(`/datasets/${encodeURIComponent(datasetId)}/versions`),

  getDatasetVersion: async (datasetId: string, versionId: string): Promise<DatasetVersionRecord> =>
    request<DatasetVersionRecord>(
      `/datasets/${encodeURIComponent(datasetId)}/versions/${encodeURIComponent(versionId)}`,
    ),

  getDatasetLineage: async (datasetId: string): Promise<DatasetLineageResponse> =>
    request<DatasetLineageResponse>(`/datasets/${encodeURIComponent(datasetId)}/lineage`),

  compareDatasetVersions: async (
    datasetId: string,
    versionAId: string,
    versionBId: string,
  ): Promise<DatasetVersionComparison> =>
    request<DatasetVersionComparison>(`/datasets/${encodeURIComponent(datasetId)}/versions/compare`, {
      method: 'POST',
      body: JSON.stringify({ versionAId, versionBId }),
    }),

  restoreDatasetVersion: async (datasetId: string, versionId: string): Promise<DatasetVersionRecord> =>
    request<DatasetVersionRecord>(
      `/datasets/${encodeURIComponent(datasetId)}/versions/${encodeURIComponent(versionId)}/restore`,
      { method: 'POST' },
    ),

  downloadDatasetVersion: async (datasetId: string, versionId: string, filename: string): Promise<void> =>
    downloadBlob(
      `/datasets/${encodeURIComponent(datasetId)}/versions/${encodeURIComponent(versionId)}/download`,
      filename,
    ),

  createDatasetVersion: async (datasetId: string, note?: string): Promise<DatasetVersionRecord> =>
    request<DatasetVersionRecord>(`/datasets/${encodeURIComponent(datasetId)}/versions`, {
      method: 'POST',
      body: JSON.stringify(note?.trim() ? { note: note.trim() } : {}),
    }),

  uploadSynthMedSource: async (
    payload: SynthMedUploadPayload,
    onProgress: (percent: number) => void,
  ): Promise<SynthMedSourceDataset> => {
    const form = new FormData();
    form.append('file', payload.file);
    form.append('dataset_name', payload.datasetName);
    form.append('description', payload.description);
    const response = await uploadWithProgress<{ dataset: SynthMedSourceDataset; message: string }>(
      '/synthmed/upload',
      form,
      onProgress,
    );
    return response.dataset;
  },

  createSynthMedSourceFromRepository: async (datasetId: string, versionId?: string): Promise<SynthMedSourceDataset> => {
    const suffix = versionId ? `?version_id=${encodeURIComponent(versionId)}` : '';
    const response = await request<{ dataset?: SynthMedSourceDataset } & SynthMedSourceDataset>(
      `/synthmed/sources/from-repository/${encodeURIComponent(datasetId)}${suffix}`,
      { method: 'POST' },
    );
    return response.dataset ?? response;
  },

  registerGeneratedDataset: async (
    generatedId: string,
    payload: SynthMedGeneratedDatasetRegisterPayload,
  ): Promise<SynthMedRegisterResponse> => {
    const response = await request<SynthMedRegisterResponse>(
      `/synthmed/generated/${encodeURIComponent(generatedId)}/register-in-repository`,
      { method: 'POST', body: JSON.stringify(payload) },
    );
    return { ...response, dataset: toDataset(response.dataset as unknown as ApiDataset) };
  },

  listSynthMedSources: async (): Promise<SynthMedSourceDataset[]> => request<SynthMedSourceDataset[]>('/synthmed/sources'),

  listSynthMedModels: async (): Promise<SynthMedModelsResponse> => request<SynthMedModelsResponse>('/synthmed/models'),

  getSynthMedDatasetColumns: async (datasetId: string, model: SynthMedModelName): Promise<SynthMedDatasetColumns> =>
    request<SynthMedDatasetColumns>(
      `/synthmed/datasets/${encodeURIComponent(datasetId)}/columns?model=${encodeURIComponent(model)}`,
    ),

  listSynthMedClinicalReferences: async (): Promise<SynthMedClinicalReferencesResponse> =>
    request<SynthMedClinicalReferencesResponse>('/synthmed/clinical/references'),

  getSynthMedMedicalProfile: async (datasetId: string): Promise<SynthMedMedicalProfileResponse> =>
    request<SynthMedMedicalProfileResponse>(
      `/synthmed/sources/${encodeURIComponent(datasetId)}/medical-profile`,
    ),

  validateSynthMedSourceClinical: async (
    payload: SynthMedSourceClinicalValidationPayload,
  ): Promise<SynthMedSourceClinicalValidationResponse> =>
    request<SynthMedSourceClinicalValidationResponse>(
      `/synthmed/sources/${encodeURIComponent(payload.sourceDatasetId)}/clinical-validation`,
      { method: 'POST', body: JSON.stringify(payload) },
    ),

  getSynthMedSource: async (datasetId: string): Promise<SynthMedSourceDataset> =>
    request<SynthMedSourceDataset>(`/synthmed/sources/${encodeURIComponent(datasetId)}`),

  listSynthMedGenerated: async (): Promise<SynthMedGeneratedDataset[]> =>
    request<SynthMedGeneratedDataset[]>('/synthmed/generated'),

  getSynthMedDownloads: async (): Promise<SynthMedDownloads> => request<SynthMedDownloads>('/synthmed/downloads'),

  downloadSynthMedSource: async (dataset: SynthMedSourceDataset): Promise<void> =>
    downloadBlob(`/synthmed/sources/${encodeURIComponent(dataset.id)}/download`, dataset.originalFilename),

  downloadSynthMedGenerated: async (dataset: SynthMedGeneratedDataset): Promise<void> =>
    downloadBlob(
      `/synthmed/generated/${encodeURIComponent(dataset.id)}/download`,
      dataset.fileName || `${dataset.datasetName.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}.${dataset.fileFormat.toLowerCase()}`,
    ),

  analyseSynthMedGeneration: async (sourceDatasetId: string): Promise<SynthMedGenerationAnalysis> =>
    request<SynthMedGenerationAnalysis>(
      `/synthmed/generation/analyse/${encodeURIComponent(sourceDatasetId)}`,
      { method: 'POST' },
    ),

  validateSynthMedConditions: async (
    payload: SynthMedConditionValidationRequest,
  ): Promise<SynthMedConditionValidationResponse> =>
    request<SynthMedConditionValidationResponse>('/synthmed/generation/validate-conditions', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  startSynthMedGeneration: async (payload: SynthMedGenerationStartPayload): Promise<SynthMedGenerationJob> =>
    request<SynthMedGenerationJob>('/synthmed/generation/start', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  listSynthMedGenerationJobs: async (): Promise<SynthMedGenerationJob[]> =>
    request<SynthMedGenerationJob[]>('/synthmed/generation/jobs'),

  getSynthMedGenerationJob: async (jobId: string): Promise<SynthMedGenerationJob> =>
    request<SynthMedGenerationJob>(`/synthmed/generation/jobs/${encodeURIComponent(jobId)}`),

  getSynthMedGenerationJobConditions: async (jobId: string): Promise<SynthMedEvaluationReport> =>
    request<SynthMedEvaluationReport>(`/synthmed/generation/jobs/${encodeURIComponent(jobId)}/conditions`),

  getSynthMedGeneratedConditions: async (generatedId: string): Promise<SynthMedEvaluationReport> =>
    request<SynthMedEvaluationReport>(`/synthmed/generated/${encodeURIComponent(generatedId)}/conditions`),

  getSynthMedGeneratedEvaluation: async (generatedId: string): Promise<SynthMedGeneratedEvaluationSummary> =>
    request<SynthMedGeneratedEvaluationSummary>(`/synthmed/generated/${encodeURIComponent(generatedId)}/evaluation`),

  getSynthMedGeneratedDetail: async (generatedId: string): Promise<SynthMedGeneratedDatasetDetail> =>
    request<SynthMedGeneratedDatasetDetail>(`/synthmed/generated/${encodeURIComponent(generatedId)}`),

  getSynthMedGeneratedPreview: async (
    generatedId: string,
    page: number,
    pageSize: number,
  ): Promise<SynthMedGeneratedPreview> =>
    request<SynthMedGeneratedPreview>(
      `/synthmed/generated/${encodeURIComponent(generatedId)}/preview?page=${page}&pageSize=${pageSize}`,
    ),

  getSynthMedClinicalReport: async (generatedId: string): Promise<SynthMedEvaluationReport> =>
    request<SynthMedEvaluationReport>(`/synthmed/generated/${encodeURIComponent(generatedId)}/clinical`),

  getSynthMedQualityReport: async (generatedId: string): Promise<SynthMedEvaluationReport> =>
    request<SynthMedEvaluationReport>(`/synthmed/generated/${encodeURIComponent(generatedId)}/quality`),

  getSynthMedPrivacyReport: async (generatedId: string): Promise<SynthMedEvaluationReport> =>
    request<SynthMedEvaluationReport>(`/synthmed/generated/${encodeURIComponent(generatedId)}/privacy`),

  exportSynthMedGenerated: async (generatedId: string, format: FileFormat): Promise<SynthMedExportResponse> =>
    request<SynthMedExportResponse>(`/synthmed/generated/${encodeURIComponent(generatedId)}/export`, {
      method: 'POST',
      body: JSON.stringify({ format }),
    }),

  downloadSynthMedGeneratedFormat: async (generatedId: string, format: FileFormat): Promise<void> =>
    downloadBlob(
      `/synthmed/generated/${encodeURIComponent(generatedId)}/download?file_format=${format}`,
      `synthetic_data.${format.toLowerCase()}`,
    ),

  downloadSynthMedReport: async (generatedId: string, reportType: string): Promise<void> =>
    downloadBlob(
      `/synthmed/generated/${encodeURIComponent(generatedId)}/reports/${encodeURIComponent(reportType)}/download`,
      `${reportType}_report.json`,
    ),

  listSynthMedComparisons: async (): Promise<SynthMedComparisonListItem[]> =>
    request<SynthMedComparisonListItem[]>('/synthmed/comparisons'),

  getSynthMedComparison: async (comparisonId: string): Promise<SynthMedComparisonDetail> =>
    request<SynthMedComparisonDetail>(`/synthmed/comparisons/${encodeURIComponent(comparisonId)}`),

  createSynthMedComparison: async (payload: SynthMedComparisonCreatePayload): Promise<SynthMedComparisonDetail> =>
    request<SynthMedComparisonDetail>('/synthmed/comparisons', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  downloadSynthMedComparisonReport: async (comparisonId: string): Promise<void> =>
    downloadBlob(
      `/synthmed/comparisons/${encodeURIComponent(comparisonId)}/report/download`,
      'comparison_report.json',
    ),

  createSynthMedUtilityEvaluation: async (payload: SynthMedUtilityEvaluationCreatePayload): Promise<SynthMedUtilityEvaluation> =>
    request<SynthMedUtilityEvaluation>('/synthmed/utility-evaluations', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  listSynthMedUtilityEvaluations: async (): Promise<SynthMedUtilityEvaluation[]> =>
    request<SynthMedUtilityEvaluation[]>('/synthmed/utility-evaluations'),

  getSynthMedUtilityEvaluation: async (evaluationId: string): Promise<SynthMedUtilityEvaluation> =>
    request<SynthMedUtilityEvaluation>(`/synthmed/utility-evaluations/${encodeURIComponent(evaluationId)}`),

  getSynthMedUtilityEvaluationReport: async (evaluationId: string): Promise<Record<string, unknown>> =>
    request<Record<string, unknown>>(`/synthmed/utility-evaluations/${encodeURIComponent(evaluationId)}/report`),

  downloadSynthMedUtilityEvaluationReport: async (evaluationId: string, format: 'json' | 'csv' | 'pdf' = 'json'): Promise<void> =>
    downloadBlob(
      `/synthmed/utility-evaluations/${encodeURIComponent(evaluationId)}/download?format=${encodeURIComponent(format)}`,
      `utility_report.${format}`,
    ),

  listSynthMedVersions: async (datasetId: string): Promise<SynthMedVersionResponse[]> =>
    request<SynthMedVersionResponse[]>(`/synthmed/datasets/${encodeURIComponent(datasetId)}/versions`),

  getSynthMedVersion: async (datasetId: string, versionId: string): Promise<SynthMedVersionResponse> =>
    request<SynthMedVersionResponse>(
      `/synthmed/datasets/${encodeURIComponent(datasetId)}/versions/${encodeURIComponent(versionId)}`,
    ),

  getSynthMedDatasetLineage: async (datasetId: string): Promise<SynthMedDatasetLineageResponse> =>
    request<SynthMedDatasetLineageResponse>(`/synthmed/datasets/${encodeURIComponent(datasetId)}/lineage`),

  compareSynthMedVersions: async (
    datasetId: string,
    versionAId: string,
    versionBId: string,
  ): Promise<SynthMedVersionComparison> =>
    request<SynthMedVersionComparison>(`/synthmed/datasets/${encodeURIComponent(datasetId)}/versions/compare`, {
      method: 'POST',
      body: JSON.stringify({ versionAId, versionBId }),
    }),

  restoreSynthMedVersion: async (datasetId: string, versionId: string): Promise<SynthMedVersionResponse> =>
    request<SynthMedVersionResponse>(
      `/synthmed/datasets/${encodeURIComponent(datasetId)}/versions/${encodeURIComponent(versionId)}/restore`,
      { method: 'POST' },
    ),

  downloadSynthMedVersion: async (datasetId: string, versionId: string, filename: string): Promise<void> =>
    downloadBlob(
      `/synthmed/datasets/${encodeURIComponent(datasetId)}/versions/${encodeURIComponent(versionId)}/download`,
      filename,
    ),

  listSynthMedExperiments: async (): Promise<SynthMedExperimentResponse[]> =>
    request<SynthMedExperimentResponse[]>('/synthmed/experiments'),

  createSynthMedExperiment: async (
    payload: SynthMedExperimentCreatePayload,
  ): Promise<SynthMedExperimentResponse> =>
    request<SynthMedExperimentResponse>('/synthmed/experiments', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  getSynthMedExperiment: async (experimentId: string): Promise<SynthMedExperimentResponse> =>
    request<SynthMedExperimentResponse>(`/synthmed/experiments/${encodeURIComponent(experimentId)}`),

  reuseSynthMedExperimentConfiguration: async (
    experimentId: string,
    payload: SynthMedExperimentReusePayload = {},
  ): Promise<SynthMedGenerationJob> =>
    request<SynthMedGenerationJob>(
      `/synthmed/experiments/${encodeURIComponent(experimentId)}/reuse-configuration`,
      { method: 'POST', body: JSON.stringify(payload) },
    ),

  getSynthMedExperimentReport: async (experimentId: string): Promise<SynthMedExperimentReport> =>
    request<SynthMedExperimentReport>(`/synthmed/experiments/${encodeURIComponent(experimentId)}/report`),

  downloadSynthMedExperimentReport: async (experimentId: string): Promise<void> =>
    downloadBlob(
      `/synthmed/experiments/${encodeURIComponent(experimentId)}/report`,
      `experiment_${experimentId.slice(0, 8)}_report.json`,
    ),

  getSynthMedExperimentHistory: async (experimentId: string): Promise<SynthMedExperimentHistory> =>
    request<SynthMedExperimentHistory>(`/synthmed/experiments/${encodeURIComponent(experimentId)}/history`),

  getSynthMedExperimentConfigurations: async (experimentId: string): Promise<SynthMedConfigSnapshot[]> =>
    request<SynthMedConfigSnapshot[]>(`/synthmed/experiments/${encodeURIComponent(experimentId)}/configurations`),

  listResearchReports: async (reportType?: ResearchReportType): Promise<ResearchReportListResponse> =>
    request<ResearchReportListResponse>(`/reports${reportType ? `?reportType=${encodeURIComponent(reportType)}` : ''}`),

  getResearchReport: async (reportId: string): Promise<ResearchReport> =>
    request<ResearchReport>(`/reports/${encodeURIComponent(reportId)}`),

  getResearchReportStatus: async (reportId: string): Promise<ResearchReportStatusResponse> =>
    request<ResearchReportStatusResponse>(`/reports/${encodeURIComponent(reportId)}/status`),

  createResearchReport: async (
    reportType: ResearchReportType,
    payload: ResearchReportGeneratePayload,
  ): Promise<ResearchReport> =>
    request<ResearchReport>(RESEARCH_REPORT_ENDPOINTS[reportType], {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  downloadResearchReport: async (reportId: string): Promise<void> =>
    downloadBlob(`/reports/${encodeURIComponent(reportId)}/download`, `${reportId}.pdf`),
};

export const reportMaps = {
  from: (items: { quality: QualityReport | null; readiness: ReadinessReport | null; representativeness: RepresentativenessReport | null }[]) => ({
    qualityReports: toReportKeyed(
      items.map((item) => item.quality).filter((item): item is QualityReport => item !== null),
    ),
    readinessReports: toReportKeyed(
      items.map((item) => item.readiness).filter((item): item is ReadinessReport => item !== null),
    ),
    representativenessReports: toReportKeyed(
      items
        .map((item) => item.representativeness)
        .filter((item): item is RepresentativenessReport => item !== null),
    ),
  }),
};

export type { ApiReportsResponse };
