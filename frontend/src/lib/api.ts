import type {
  AccessLevel,
  AccessRequest,
  CurrentUser,
  Dataset,
  Domain,
  EtlJob,
  FileFormat,
  MappingDecisionInput,
  QualityReport,
  ReadinessReport,
  RepresentativenessReport,
  Role,
} from '../types';

const RAW_BASE = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '');
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

interface ApiUser {
  id: string;
  email: string;
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

export interface UploadPayload {
  file: File;
  format: FileFormat;
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
  role: user.role,
  organisation: user.organisation,
  title: user.title,
});

const toDataset = (dataset: ApiDataset): Dataset => ({ ...dataset, domain: dataset.domain as Domain });

const toReportKeyed = <T extends { datasetId: string }>(items: T[]): Record<string, T> =>
  Object.fromEntries(items.map((item) => [item.datasetId, item]));

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
    organisation: string;
    title: string;
  }): Promise<CurrentUser> => {
    await request<ApiUser>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({
        email: input.email,
        password: input.password,
        full_name: input.fullName,
        organisation: input.organisation,
        title: input.title,
      }),
    });
    return api.login(input.email, input.password);
  },

  me: async (): Promise<CurrentUser> => toCurrentUser(await request<ApiUser>('/auth/me')),

  updateProfile: async (input: {
    fullName: string;
    organisation: string;
    title: string;
  }): Promise<CurrentUser> =>
    toCurrentUser(
      await request<ApiUser>('/auth/me', {
        method: 'PATCH',
        body: JSON.stringify({
          full_name: input.fullName,
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

  listDatasets: async (): Promise<Dataset[]> =>
    (await request<ApiDataset[]>('/datasets/')).map(toDataset),

  getDataset: async (datasetId: string): Promise<Dataset> =>
    toDataset(await request<ApiDataset>(`/datasets/${encodeURIComponent(datasetId)}`)),

  uploadDataset: async (payload: UploadPayload): Promise<{ dataset: Dataset; jobId: string }> => {
    const form = new FormData();
    form.append('file', payload.file);
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

  downloadDataset: async (dataset: Dataset): Promise<void> => {
    const token = tokenStore.get();
    const response = await fetch(`${API_ROOT}/datasets/${encodeURIComponent(dataset.id)}/download`, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
    if (!response.ok) {
      throw new ApiError(response.status, await errorDetail(response));
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${dataset.title.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}.${dataset.format.toLowerCase()}`;
    anchor.click();
    URL.revokeObjectURL(url);
  },
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
