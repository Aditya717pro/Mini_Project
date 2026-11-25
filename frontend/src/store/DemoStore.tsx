import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useNavigate } from 'react-router-dom';
import { LoginScreen } from '../components/LoginScreen';
import { LoadingState } from '../components/ui';
import {
  ApiError,
  api,
  reportMaps,
  tokenStore,
  type SynthMedSourceClinicalValidationPayload,
  type SynthMedUploadPayload,
} from '../lib/api';
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
  ExtractPreview,
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
  RequestStatus,
  Role,
  SynthMedComparisonCreatePayload,
  SynthMedClinicalReferencesResponse,
  SynthMedComparisonDetail,
  SynthMedComparisonListItem,
  SynthMedConditionValidationRequest,
  SynthMedConditionValidationResponse,
  SynthMedDatasetColumns,
  SynthMedConfigSnapshot,
  SynthMedDatasetLineageResponse,
  SynthMedDownloads,
  SynthMedEvaluationReport,
  SynthMedExperimentCreatePayload,
  SynthMedExperimentHistory,
  SynthMedExperimentReusePayload,
  SynthMedExperimentReport,
  SynthMedExperimentResponse,
  SynthMedExportResponse,
  SynthMedGeneratedDataset,
  SynthMedGeneratedDatasetDetail,
  SynthMedGeneratedDatasetRegisterPayload,
  SynthMedGeneratedEvaluationSummary,
  SynthMedGeneratedPreview,
  SynthMedGenerationAnalysis,
  SynthMedGenerationJob,
  SynthMedGenerationStartPayload,
  SynthMedMedicalProfileResponse,
  SynthMedModelName,
  SynthMedModelsResponse,
  SynthMedRegisterResponse,
  SynthMedSourceClinicalValidationResponse,
  SynthMedSourceDataset,
  SynthMedUtilityEvaluation,
  SynthMedUtilityEvaluationCreatePayload,
  SynthMedVersionComparison,
  SynthMedVersionResponse,
  ThemeMode,
  ToastMessage,
} from '../types';

export interface UploadInput {
  file?: File;
  checksum?: string;
  preview?: ExtractPreview;
  format?: FileFormat;
  generatedDatasetId?: string;
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

export interface AccessRequestInput {
  projectTitle: string;
  purpose: string;
}

interface DemoStore {
  user: CurrentUser;
  role: Role;
  theme: ThemeMode;
  setTheme: (theme: ThemeMode) => void;
  datasets: Dataset[];
  jobs: EtlJob[];
  synthSources: SynthMedSourceDataset[];
  synthGenerated: SynthMedGeneratedDataset[];
  synthJobs: SynthMedGenerationJob[];
  synthComparisons: SynthMedComparisonListItem[];
  datasetVersions: Record<string, DatasetVersionsResponse>;
  datasetLineage: Record<string, DatasetLineageResponse>;
  synthVersions: Record<string, SynthMedVersionResponse[]>;
  synthLineage: Record<string, SynthMedDatasetLineageResponse>;
  synthExperiments: SynthMedExperimentResponse[];
  requests: AccessRequest[];
  qualityReports: Record<string, QualityReport>;
  readinessReports: Record<string, ReadinessReport>;
  representativenessReports: Record<string, RepresentativenessReport>;
  toasts: ToastMessage[];
  notify: (type: ToastMessage['type'], title: string, message?: string) => void;
  dismissToast: (id: string) => void;
  logout: () => void;
  updateProfile: (input: { fullName: string; phoneNumber?: string; organisation: string; title: string }) => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<boolean>;
  requestPasswordReset: (email: string) => Promise<string>;
  verifyPasswordReset: (email: string, otp: string, newPassword: string) => Promise<void>;
  refresh: () => Promise<void>;
  uploadDataset: (input: UploadInput) => Promise<{ datasetId: string; jobId: string }>;
  uploadSynthMedSource: (input: SynthMedUploadPayload, onProgress: (percent: number) => void) => Promise<string>;
  createSynthMedSourceFromRepository: (datasetId: string, versionId?: string) => Promise<SynthMedSourceDataset>;
  registerGeneratedDataset: (generatedId: string, payload: SynthMedGeneratedDatasetRegisterPayload) => Promise<SynthMedRegisterResponse>;
  refreshSynthMed: () => Promise<SynthMedDownloads>;
  getSynthMedSource: (datasetId: string) => Promise<SynthMedSourceDataset>;
  downloadSynthMedSource: (dataset: SynthMedSourceDataset) => Promise<void>;
  downloadSynthMedGenerated: (dataset: SynthMedGeneratedDataset) => Promise<void>;
  analyseSynthMedGeneration: (sourceDatasetId: string) => Promise<SynthMedGenerationAnalysis>;
  listSynthMedModels: () => Promise<SynthMedModelsResponse>;
  getSynthMedDatasetColumns: (
    datasetId: string,
    model: SynthMedModelName,
  ) => Promise<SynthMedDatasetColumns>;
  listSynthMedClinicalReferences: () => Promise<SynthMedClinicalReferencesResponse>;
  getSynthMedMedicalProfile: (datasetId: string) => Promise<SynthMedMedicalProfileResponse>;
  validateSynthMedSourceClinical: (
    payload: SynthMedSourceClinicalValidationPayload,
  ) => Promise<SynthMedSourceClinicalValidationResponse>;
  validateSynthMedConditions: (
    payload: SynthMedConditionValidationRequest,
  ) => Promise<SynthMedConditionValidationResponse>;
  startSynthMedGeneration: (payload: SynthMedGenerationStartPayload) => Promise<SynthMedGenerationJob>;
  listSynthMedGenerationJobs: () => Promise<SynthMedGenerationJob[]>;
  getSynthMedGenerationJob: (jobId: string) => Promise<SynthMedGenerationJob>;
  getSynthMedGenerationJobConditions: (jobId: string) => Promise<SynthMedEvaluationReport>;
  getSynthMedGeneratedConditions: (generatedId: string) => Promise<SynthMedEvaluationReport>;
  getSynthMedGeneratedEvaluation: (generatedId: string) => Promise<SynthMedGeneratedEvaluationSummary>;
  getSynthMedGeneratedDetail: (generatedId: string) => Promise<SynthMedGeneratedDatasetDetail>;
  getSynthMedGeneratedPreview: (
    generatedId: string,
    page: number,
    pageSize: number,
  ) => Promise<SynthMedGeneratedPreview>;
  getSynthMedClinicalReport: (generatedId: string) => Promise<SynthMedEvaluationReport>;
  getSynthMedQualityReport: (generatedId: string) => Promise<SynthMedEvaluationReport>;
  getSynthMedPrivacyReport: (generatedId: string) => Promise<SynthMedEvaluationReport>;
  exportSynthMedGenerated: (generatedId: string, format: FileFormat) => Promise<SynthMedExportResponse>;
  downloadSynthMedGeneratedFormat: (generatedId: string, format: FileFormat) => Promise<void>;
  downloadSynthMedReport: (generatedId: string, reportType: string) => Promise<void>;
  listSynthMedComparisons: () => Promise<SynthMedComparisonListItem[]>;
  getSynthMedComparison: (comparisonId: string) => Promise<SynthMedComparisonDetail>;
  createSynthMedComparison: (payload: SynthMedComparisonCreatePayload) => Promise<SynthMedComparisonDetail>;
  downloadSynthMedComparisonReport: (comparisonId: string) => Promise<void>;
  createSynthMedUtilityEvaluation: (payload: SynthMedUtilityEvaluationCreatePayload) => Promise<string>;
  listSynthMedUtilityEvaluations: () => Promise<SynthMedUtilityEvaluation[]>;
  getSynthMedUtilityEvaluation: (evaluationId: string) => Promise<SynthMedUtilityEvaluation>;
  getSynthMedUtilityEvaluationReport: (evaluationId: string) => Promise<Record<string, unknown>>;
  downloadSynthMedUtilityEvaluationReport: (evaluationId: string, format?: 'json' | 'csv' | 'pdf') => Promise<void>;
  refreshJob: (jobId: string) => Promise<void>;
  profileJob: (jobId: string) => Promise<void>;
  recordMappingDecisions: (jobId: string, decisions: MappingDecisionInput[]) => Promise<void>;
  approveMappings: (jobId: string, note?: string) => Promise<void>;
  publishJob: (jobId: string) => Promise<void>;
  cancelJob: (jobId: string) => Promise<void>;
  rejectJob: (jobId: string, reason: string) => Promise<void>;
  decideRequest: (
    requestId: string,
    status: Exclude<RequestStatus, 'Pending' | 'Withdrawn'>,
    note: string,
  ) => Promise<void>;
  withdrawRequest: (requestId: string) => Promise<void>;
  requestAccess: (datasetId: string, input: AccessRequestInput) => Promise<boolean>;
  approveDataset: (datasetId: string, reason: string) => Promise<void>;
  rejectDataset: (datasetId: string, reason: string) => Promise<void>;
  downloadDataset: (dataset: Dataset) => Promise<void>;
  listDatasetVersions: (datasetId: string) => Promise<DatasetVersionsResponse>;
  getDatasetVersion: (datasetId: string, versionId: string) => Promise<DatasetVersionRecord>;
  getDatasetLineage: (datasetId: string) => Promise<DatasetLineageResponse>;
  compareDatasetVersions: (
    datasetId: string,
    versionAId: string,
    versionBId: string,
  ) => Promise<DatasetVersionComparison>;
  restoreDatasetVersion: (datasetId: string, versionId: string) => Promise<DatasetVersionRecord>;
  downloadDatasetVersion: (datasetId: string, versionId: string, filename: string) => Promise<void>;
  createDatasetVersion: (datasetId: string, note?: string) => Promise<DatasetVersionRecord>;
  listSynthMedVersions: (datasetId: string) => Promise<SynthMedVersionResponse[]>;
  getSynthMedVersion: (datasetId: string, versionId: string) => Promise<SynthMedVersionResponse>;
  getSynthMedDatasetLineage: (datasetId: string) => Promise<SynthMedDatasetLineageResponse>;
  compareSynthMedVersions: (
    datasetId: string,
    versionAId: string,
    versionBId: string,
  ) => Promise<SynthMedVersionComparison>;
  restoreSynthMedVersion: (datasetId: string, versionId: string) => Promise<SynthMedVersionResponse>;
  downloadSynthMedVersion: (datasetId: string, versionId: string, filename: string) => Promise<void>;
  listSynthMedExperiments: () => Promise<SynthMedExperimentResponse[]>;
  getSynthMedExperiment: (experimentId: string) => Promise<SynthMedExperimentResponse>;
  createSynthMedExperiment: (payload: SynthMedExperimentCreatePayload) => Promise<SynthMedExperimentResponse>;
  reuseSynthMedExperimentConfiguration: (
    experimentId: string,
    payload?: SynthMedExperimentReusePayload,
  ) => Promise<SynthMedGenerationJob>;
  getSynthMedExperimentReport: (experimentId: string) => Promise<SynthMedExperimentReport>;
  downloadSynthMedExperimentReport: (experimentId: string) => Promise<void>;
  getSynthMedExperimentHistory: (experimentId: string) => Promise<SynthMedExperimentHistory>;
  getSynthMedExperimentConfigurations: (experimentId: string) => Promise<SynthMedConfigSnapshot[]>;
  listResearchReports: (reportType?: ResearchReportType) => Promise<ResearchReportListResponse>;
  getResearchReport: (reportId: string) => Promise<ResearchReport>;
  getResearchReportStatus: (reportId: string) => Promise<ResearchReportStatusResponse>;
  createResearchReport: (
    reportType: ResearchReportType,
    payload: ResearchReportGeneratePayload,
  ) => Promise<ResearchReport>;
  downloadResearchReport: (reportId: string) => Promise<void>;
}

const DemoContext = createContext<DemoStore | null>(null);

const THEME_STORAGE_KEY = 'meddatahub.theme';

const errorMessage = (error: unknown) => (error instanceof Error ? error.message : 'Unexpected API error');

const initialTheme = (): ThemeMode => {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === 'default' || stored === 'light' || stored === 'dark') return stored;
  } catch {
    return 'default';
  }
  return 'light';
};

export const DemoProvider = ({ children }: { children: ReactNode }) => {
  const navigate = useNavigate();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [theme, setThemeState] = useState<ThemeMode>(initialTheme);
  const [booting, setBooting] = useState(true);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [jobs, setJobs] = useState<EtlJob[]>([]);
  const [synthSources, setSynthSources] = useState<SynthMedSourceDataset[]>([]);
  const [synthGenerated, setSynthGenerated] = useState<SynthMedGeneratedDataset[]>([]);
  const [synthJobs, setSynthJobs] = useState<SynthMedGenerationJob[]>([]);
  const [synthComparisons, setSynthComparisons] = useState<SynthMedComparisonListItem[]>([]);
  const [datasetVersions, setDatasetVersions] = useState<Record<string, DatasetVersionsResponse>>({});
  const [datasetLineage, setDatasetLineage] = useState<Record<string, DatasetLineageResponse>>({});
  const [synthVersions, setSynthVersions] = useState<Record<string, SynthMedVersionResponse[]>>({});
  const [synthLineage, setSynthLineage] = useState<Record<string, SynthMedDatasetLineageResponse>>({});
  const [synthExperiments, setSynthExperiments] = useState<SynthMedExperimentResponse[]>([]);
  const [requests, setRequests] = useState<AccessRequest[]>([]);
  const [qualityReports, setQualityReports] = useState<Record<string, QualityReport>>({});
  const [readinessReports, setReadinessReports] = useState<Record<string, ReadinessReport>>({});
  const [representativenessReports, setRepresentativenessReports] =
    useState<Record<string, RepresentativenessReport>>({});
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const toastTimersRef = useRef<number[]>([]);

  useEffect(() => {
    return () => {
      toastTimersRef.current.forEach((timer) => window.clearTimeout(timer));
    };
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const notify = useCallback(
    (type: ToastMessage['type'], title: string, message?: string) => {
      const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
      setToasts((prev) => [...prev, { id, type, title, message }]);
      const timer = window.setTimeout(() => {
        setToasts((prev) => prev.filter((toast) => toast.id !== id));
      }, 3000);
      toastTimersRef.current.push(timer);
    },
    [],
  );

  useEffect(() => {
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      // Storage unavailable or disabled
    }

    const applyTheme = () => {
      let resolved: 'light' | 'dark' = 'light';
      if (theme === 'default') {
        const prefersDark =
          typeof window !== 'undefined' &&
          window.matchMedia &&
          window.matchMedia('(prefers-color-scheme: dark)').matches;
        resolved = prefersDark ? 'dark' : 'light';
      } else {
        resolved = theme;
      }
      document.documentElement.dataset.theme = resolved;
      document.documentElement.dataset.themePreference = theme;
      document.documentElement.style.colorScheme = resolved;
    };

    applyTheme();

    if (theme === 'default' && typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
      const handleSystemThemeChange = () => {
        applyTheme();
      };
      if (mediaQuery.addEventListener) {
        mediaQuery.addEventListener('change', handleSystemThemeChange);
        return () => mediaQuery.removeEventListener('change', handleSystemThemeChange);
      } else if ('addListener' in mediaQuery) {
        (mediaQuery as { addListener: (cb: () => void) => void }).addListener(handleSystemThemeChange);
        return () =>
          (mediaQuery as { removeListener: (cb: () => void) => void }).removeListener(handleSystemThemeChange);
      }
    }
  }, [theme]);

  const setTheme = useCallback(
    (next: ThemeMode) => {
      setThemeState(next);
      if (next === 'default') {
        const prefersDark =
          typeof window !== 'undefined' &&
          window.matchMedia &&
          window.matchMedia('(prefers-color-scheme: dark)').matches;
        notify('info', 'Theme: System', prefersDark ? 'Dark mode' : 'Light mode');
      } else {
        notify('info', `Theme: ${next === 'dark' ? 'Dark' : 'Light'}`);
      }
    },
    [notify],
  );

  const resetWorkspace = useCallback(() => {
    setDatasets([]);
    setJobs([]);
    setSynthSources([]);
    setSynthGenerated([]);
    setSynthJobs([]);
    setSynthComparisons([]);
    setDatasetVersions({});
    setDatasetLineage({});
    setSynthVersions({});
    setSynthLineage({});
    setSynthExperiments([]);
    setRequests([]);
    setQualityReports({});
    setReadinessReports({});
    setRepresentativenessReports({});
  }, []);

  const loadWorkspace = useCallback(async () => {
    try {
      const [datasetList, jobList, requestList, synthDownloads, generationJobs, comparisons] = await Promise.all([
        api.listDatasets().catch((err) => {
          console.error('Failed to list datasets:', err);
          return [];
        }),
        api.listJobs().catch((err) => {
          console.error('Failed to list jobs:', err);
          return [];
        }),
        api.listAccessRequests().catch((err) => {
          console.error('Failed to list access requests:', err);
          return [];
        }),
        api.getSynthMedDownloads().catch((err) => {
          console.error('Failed to list SynthMed datasets:', err);
          return { sources: [], generated: [] } as SynthMedDownloads;
        }),
        api.listSynthMedGenerationJobs().catch((err) => {
          console.error('Failed to list SynthMed generation jobs:', err);
          return [] as SynthMedGenerationJob[];
        }),
        api.listSynthMedComparisons().catch((err) => {
          console.error('Failed to list SynthMed comparisons:', err);
          return [] as SynthMedComparisonListItem[];
        }),
      ]);
      const reportBundles = await Promise.all(
        datasetList.map(async (dataset) => {
          try {
            return await api.getReports(dataset.id);
          } catch {
            return { quality: null, readiness: null, representativeness: null };
          }
        }),
      );
      const maps = reportMaps.from(reportBundles);
      setDatasets(datasetList);
      setJobs(jobList);
      setSynthSources(synthDownloads.sources);
      setSynthGenerated(synthDownloads.generated);
      setSynthJobs(generationJobs);
      setSynthComparisons(comparisons);
      setRequests(requestList);
      setQualityReports(maps.qualityReports);
      setReadinessReports(maps.readinessReports);
      setRepresentativenessReports(maps.representativenessReports);
    } catch (error) {
      console.error('Failed to load workspace:', error);
    }
  }, []);

  const logout = useCallback(() => {
    tokenStore.clear();
    setUser(null);
    resetWorkspace();
    navigate('/', { replace: true });
  }, [resetWorkspace, navigate]);

  useEffect(() => {
    const handleUnauthorized = () => logout();
    window.addEventListener('meddatahub:unauthorized', handleUnauthorized);
    return () => window.removeEventListener('meddatahub:unauthorized', handleUnauthorized);
  }, [logout]);

  useEffect(() => {
    let cancelled = false;
    const boot = async () => {
      if (!tokenStore.get()) {
        setBooting(false);
        return;
      }
      try {
        const current = await api.me();
        if (cancelled) return;
        setUser(current);
        await loadWorkspace();
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          tokenStore.clear();
          setUser(null);
        }
      } finally {
        if (!cancelled) setBooting(false);
      }
    };
    void boot();
    return () => {
      cancelled = true;
    };
  }, [loadWorkspace]);

  const login = useCallback(
    async (email: string, password: string) => {
      const current = await api.login(email, password);
      if (typeof window !== 'undefined' && 'PasswordCredential' in window && navigator.credentials?.store) {
        try {
          const CredentialConstructor = (window as unknown as { PasswordCredential: new (init: Record<string, unknown>) => unknown }).PasswordCredential;
          const cred = new CredentialConstructor({
            id: email,
            password: password,
            name: current.name || email,
          });
          void navigator.credentials.store(cred as Credential);
        } catch {
          // ignore
        }
      }
      setUser(current);
      navigate('/', { replace: true });
      await loadWorkspace();
    },
    [loadWorkspace, navigate],
  );

  const register = useCallback(
    async (input: {
      email: string;
      password: string;
      fullName: string;
      phoneNumber?: string;
      organisation: string;
      title: string;
    }) => {
      const current = await api.register(input);
      if (typeof window !== 'undefined' && 'PasswordCredential' in window && navigator.credentials?.store) {
        try {
          const CredentialConstructor = (window as unknown as { PasswordCredential: new (init: Record<string, unknown>) => unknown }).PasswordCredential;
          const cred = new CredentialConstructor({
            id: input.email,
            password: input.password,
            name: input.fullName,
          });
          void navigator.credentials.store(cred as Credential);
        } catch {
          // ignore
        }
      }
      setUser(current);
      navigate('/', { replace: true });
      await loadWorkspace();
    },
    [loadWorkspace, navigate],
  );

  const updateProfile = useCallback(
    async (input: { fullName: string; phoneNumber?: string; organisation: string; title: string }) => {
      const updated = await api.updateProfile(input);
      setUser(updated);
      notify('success', 'Profile updated', 'Your account details were saved by the backend.');
    },
    [notify],
  );

  const changePassword = useCallback(
    async (currentPassword: string, newPassword: string) => {
      try {
        await api.changePassword(currentPassword, newPassword);
        notify('success', 'Password updated', 'Use the new password for your next sign-in.');
        return true;
      } catch (error) {
        notify('error', 'Password not updated', errorMessage(error));
        return false;
      }
    },
    [notify],
  );

  const requestPasswordReset = useCallback(async (email: string) => api.requestPasswordReset(email), []);

  const verifyPasswordReset = useCallback(
    async (email: string, otp: string, newPassword: string) => {
      await api.verifyPasswordReset(email, otp, newPassword);
    },
    [],
  );

  const refresh = useCallback(async () => {
    try {
      await loadWorkspace();
    } catch (error) {
      notify('error', 'Could not refresh workspace', errorMessage(error));
    }
  }, [loadWorkspace, notify]);

  const refreshDataset = useCallback(async (datasetId: string) => {
    const [dataset, reports] = await Promise.all([api.getDataset(datasetId), api.getReports(datasetId)]);
    const { quality, readiness, representativeness } = reports;
    setDatasets((prev) => prev.map((item) => (item.id === dataset.id ? dataset : item)));
    if (quality) setQualityReports((prev) => ({ ...prev, [quality.datasetId]: quality }));
    if (readiness) setReadinessReports((prev) => ({ ...prev, [readiness.datasetId]: readiness }));
    if (representativeness) {
      setRepresentativenessReports((prev) => ({ ...prev, [representativeness.datasetId]: representativeness }));
    }
    return dataset;
  }, []);

  const uploadDataset = useCallback(
    async (input: UploadInput) => {
      try {
        const result = await api.uploadDataset({
          file: input.file,
          format: input.format,
          generatedDatasetId: input.generatedDatasetId,
          title: input.title,
          description: input.description,
          domain: input.domain,
          access: input.access,
          tags: input.tags,
          ageRange: input.ageRange,
          geography: input.geography
            .split(',')
            .map((item) => item.trim())
            .filter(Boolean),
          studyDesign: input.studyDesign,
          license: input.license,
          ethicsApproved: input.ethicsApproved,
          dataDictionaryAvailable: input.dataDictionaryAvailable,
          intendedTasks: input.intendedTasks,
          labelColumn: input.labelColumn,
          researchTask: input.intendedTasks[0] ?? 'General clinical research',
        });
        setDatasets((prev) => [result.dataset, ...prev.filter((item) => item.id !== result.dataset.id)]);
        const job = await api.getJob(result.jobId);
        setJobs((prev) => [job, ...prev.filter((item) => item.id !== job.id)]);
        return { datasetId: result.dataset.id, jobId: result.jobId };
      } catch (error) {
        notify('error', 'Upload failed', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const uploadSynthMedSource = useCallback(
    async (input: SynthMedUploadPayload, onProgress: (percent: number) => void) => {
      try {
        const dataset = await api.uploadSynthMedSource(input, onProgress);
        setSynthSources((prev) => [dataset, ...prev.filter((item) => item.id !== dataset.id)]);
        return dataset.id;
      } catch (error) {
        notify('error', 'SynthMed upload failed', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const createSynthMedSourceFromRepository = useCallback(
    async (datasetId: string, versionId?: string) => {
      try {
        const dataset = await api.createSynthMedSourceFromRepository(datasetId, versionId);
        setSynthSources((prev) => [dataset, ...prev.filter((item) => item.id !== dataset.id)]);
        return dataset;
      } catch (error) {
        notify('error', 'Could not prepare repository dataset', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const registerGeneratedDataset = useCallback(
    async (generatedId: string, payload: SynthMedGeneratedDatasetRegisterPayload) => {
      try {
        const response = await api.registerGeneratedDataset(generatedId, payload);
        setDatasets((prev) => [response.dataset, ...prev.filter((item) => item.id !== response.dataset.id)]);
        await refresh();
        notify('success', 'Synthetic dataset added to repository', response.message || response.dataset.title);
        return response;
      } catch (error) {
        notify('error', 'Could not add generated dataset to repository', errorMessage(error));
        throw error;
      }
    },
    [notify, refresh],
  );

  const refreshSynthMed = useCallback(async () => {
    try {
      const [downloads, jobs] = await Promise.all([
        api.getSynthMedDownloads(),
        api.listSynthMedGenerationJobs(),
      ]);
      setSynthSources(downloads.sources);
      setSynthGenerated(downloads.generated);
      setSynthJobs(jobs);
      return downloads;
    } catch (error) {
      notify('error', 'Could not refresh SynthMed datasets', errorMessage(error));
      throw error;
    }
  }, [notify]);

  const getSynthMedSource = useCallback(async (datasetId: string) => {
    const dataset = await api.getSynthMedSource(datasetId);
    setSynthSources((prev) => prev.map((item) => (item.id === dataset.id ? dataset : item)));
    return dataset;
  }, []);

  const downloadSynthMedSource = useCallback(
    async (dataset: SynthMedSourceDataset) => {
      try {
        await api.downloadSynthMedSource(dataset);
      } catch (error) {
        notify('error', 'Source download failed', errorMessage(error));
      }
    },
    [notify],
  );

  const downloadSynthMedGenerated = useCallback(
    async (dataset: SynthMedGeneratedDataset) => {
      try {
        await api.downloadSynthMedGenerated(dataset);
      } catch (error) {
        notify('error', 'Generated dataset download failed', errorMessage(error));
      }
    },
    [notify],
  );

  const analyseSynthMedGeneration = useCallback(async (sourceDatasetId: string) => {
    try {
      return await api.analyseSynthMedGeneration(sourceDatasetId);
    } catch (error) {
      notify('error', 'Source analysis failed', errorMessage(error));
      throw error;
    }
  }, [notify]);

  const listSynthMedModels = useCallback(async () => {
    try {
      return await api.listSynthMedModels();
    } catch (error) {
      notify('error', 'Could not load synthesis models', errorMessage(error));
      throw error;
    }
  }, [notify]);

  const getSynthMedDatasetColumns = useCallback(
    async (datasetId: string, model: SynthMedModelName) => {
      try {
        return await api.getSynthMedDatasetColumns(datasetId, model);
      } catch (error) {
        notify('error', 'Could not load condition columns', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const listSynthMedClinicalReferences = useCallback(async () => {
    try {
      return await api.listSynthMedClinicalReferences();
    } catch (error) {
      notify('error', 'Could not load clinical references', errorMessage(error));
      throw error;
    }
  }, [notify]);

  const getSynthMedMedicalProfile = useCallback(
    async (datasetId: string) => {
      try {
        return await api.getSynthMedMedicalProfile(datasetId);
      } catch (error) {
        notify('error', 'Could not load medical profile', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const validateSynthMedSourceClinical = useCallback(
    async (payload: SynthMedSourceClinicalValidationPayload) => {
      try {
        const response = await api.validateSynthMedSourceClinical(payload);
        notify(
          response.report.limitations?.length ? 'info' : 'success',
          'Clinical validation complete',
          `${response.generationProfile} profile returned.`,
        );
        return response;
      } catch (error) {
        notify('error', 'Clinical validation failed', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const validateSynthMedConditions = useCallback(
    async (payload: SynthMedConditionValidationRequest) => {
      try {
        const result = await api.validateSynthMedConditions(payload);
        if (result.valid) {
          notify('success', 'Configuration validated', `${result.normalizedConditions.length} condition(s) accepted.`);
        } else {
          notify('error', 'Configuration is invalid', `${result.errors.length} error(s) returned by the server.`);
        }
        return result;
      } catch (error) {
        notify('error', 'Validation failed', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const startSynthMedGeneration = useCallback(
    async (payload: SynthMedGenerationStartPayload) => {
      try {
        const job = await api.startSynthMedGeneration(payload);
        setSynthJobs((prev) => [job, ...prev.filter((item) => item.id !== job.id)]);
        notify('info', 'Generation job started', `${job.modelName} is ${job.status.toLowerCase()}.`);
        return job;
      } catch (error) {
        notify('error', 'Generation could not start', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const listSynthMedGenerationJobs = useCallback(async () => {
    try {
      const jobs = await api.listSynthMedGenerationJobs();
      setSynthJobs(jobs);
      return jobs;
    } catch (error) {
      notify('error', 'Could not load generation jobs', errorMessage(error));
      throw error;
    }
  }, [notify]);

  const getSynthMedGenerationJob = useCallback(async (jobId: string) => {
    const job = await api.getSynthMedGenerationJob(jobId);
    setSynthJobs((prev) => prev.map((item) => (item.id === job.id ? job : item)));
    return job;
  }, []);

  const getSynthMedGenerationJobConditions = useCallback(
    async (jobId: string) => {
      try {
        return await api.getSynthMedGenerationJobConditions(jobId);
      } catch (error) {
        notify('error', 'Could not load condition report', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const getSynthMedGeneratedConditions = useCallback(
    async (generatedId: string) => {
      try {
        return await api.getSynthMedGeneratedConditions(generatedId);
      } catch (error) {
        notify('error', 'Could not load condition report', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const getSynthMedGeneratedEvaluation = useCallback(
    async (generatedId: string) => {
      try {
        return await api.getSynthMedGeneratedEvaluation(generatedId);
      } catch (error) {
        notify('error', 'Could not load evaluation summary', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const getSynthMedGeneratedDetail = useCallback(
    async (generatedId: string) => api.getSynthMedGeneratedDetail(generatedId),
    [],
  );

  const getSynthMedGeneratedPreview = useCallback(
    async (generatedId: string, page: number, pageSize: number) =>
      api.getSynthMedGeneratedPreview(generatedId, page, pageSize),
    [],
  );

  const getSynthMedClinicalReport = useCallback(
    async (generatedId: string) => api.getSynthMedClinicalReport(generatedId),
    [],
  );

  const getSynthMedQualityReport = useCallback(
    async (generatedId: string) => api.getSynthMedQualityReport(generatedId),
    [],
  );

  const getSynthMedPrivacyReport = useCallback(
    async (generatedId: string) => api.getSynthMedPrivacyReport(generatedId),
    [],
  );

  const exportSynthMedGenerated = useCallback(
    async (generatedId: string, format: FileFormat) => {
      try {
        const response = await api.exportSynthMedGenerated(generatedId, format);
        notify('success', 'Export ready', `${format} output is available for download.`);
        await refreshSynthMed();
        return response;
      } catch (error) {
        notify('error', 'Export failed', errorMessage(error));
        throw error;
      }
    },
    [notify, refreshSynthMed],
  );

  const downloadSynthMedGeneratedFormat = useCallback(
    async (generatedId: string, format: FileFormat) => {
      try {
        await api.downloadSynthMedGeneratedFormat(generatedId, format);
      } catch (error) {
        notify('error', `${format} download failed`, errorMessage(error));
      }
    },
    [notify],
  );

  const downloadSynthMedReport = useCallback(
    async (generatedId: string, reportType: string) => {
      try {
        await api.downloadSynthMedReport(generatedId, reportType);
      } catch (error) {
        notify('error', 'Report download failed', errorMessage(error));
      }
    },
    [notify],
  );

  const listSynthMedComparisons = useCallback(async () => {
    try {
      const items = await api.listSynthMedComparisons();
      setSynthComparisons(items);
      return items;
    } catch (error) {
      notify('error', 'Could not load comparisons', errorMessage(error));
      throw error;
    }
  }, [notify]);

  const getSynthMedComparison = useCallback(
    async (comparisonId: string) => {
      try {
        const detail = await api.getSynthMedComparison(comparisonId);
        const item: SynthMedComparisonListItem = {
          id: detail.id,
          name: detail.name,
          sourceDatasetId: detail.sourceDatasetId,
          sourceDatasetName: detail.sourceDatasetName,
          generatedDatasetId: detail.generatedDatasetId,
          generatedDatasetName: detail.generatedDatasetName,
          summary: detail.summary,
          createdAt: detail.createdAt,
          createdBy: detail.createdBy,
          reportAvailable: detail.reportAvailable,
          generatedMetadata: detail.generatedMetadata,
        };
        setSynthComparisons((prev) =>
          prev.some((entry) => entry.id === item.id)
            ? prev.map((entry) => (entry.id === item.id ? item : entry))
            : [item, ...prev],
        );
        return detail;
      } catch (error) {
        notify('error', 'Could not load comparison', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const createSynthMedComparison = useCallback(
    async (payload: SynthMedComparisonCreatePayload) => {
      try {
        const detail = await api.createSynthMedComparison(payload);
        const item: SynthMedComparisonListItem = {
          id: detail.id,
          name: detail.name,
          sourceDatasetId: detail.sourceDatasetId,
          sourceDatasetName: detail.sourceDatasetName,
          generatedDatasetId: detail.generatedDatasetId,
          generatedDatasetName: detail.generatedDatasetName,
          summary: detail.summary,
          createdAt: detail.createdAt,
          createdBy: detail.createdBy,
          reportAvailable: detail.reportAvailable,
          generatedMetadata: detail.generatedMetadata,
        };
        setSynthComparisons((prev) => [item, ...prev.filter((entry) => entry.id !== item.id)]);
        notify('success', 'Comparison ready', `${detail.name} was calculated from the stored datasets.`);
        return detail;
      } catch (error) {
        notify('error', 'Comparison failed', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const downloadSynthMedComparisonReport = useCallback(
    async (comparisonId: string) => {
      try {
        await api.downloadSynthMedComparisonReport(comparisonId);
      } catch (error) {
        notify('error', 'Comparison report download failed', errorMessage(error));
      }
    },
    [notify],
  );

  const createSynthMedUtilityEvaluation = useCallback(async (payload: SynthMedUtilityEvaluationCreatePayload) => { try { const row = await api.createSynthMedUtilityEvaluation(payload); notify('success','ML utility evaluation started',row.evaluationName||'Utility evaluation'); return row.id; } catch (error) { notify('error','ML utility evaluation failed to start',errorMessage(error)); throw error; } }, [notify]);
  const listSynthMedUtilityEvaluations = useCallback(async () => api.listSynthMedUtilityEvaluations(), []);
  const getSynthMedUtilityEvaluation = useCallback(async (id: string) => api.getSynthMedUtilityEvaluation(id), []);
  const getSynthMedUtilityEvaluationReport = useCallback(async (id: string) => api.getSynthMedUtilityEvaluationReport(id), []);
  const downloadSynthMedUtilityEvaluationReport = useCallback(async (id: string, format: 'json'|'csv'|'pdf'='json') => { try { await api.downloadSynthMedUtilityEvaluationReport(id, format); } catch (error) { notify('error','Utility report download failed',errorMessage(error)); } }, [notify]);

  const replaceJob = useCallback((updated: EtlJob) => {
    setJobs((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
  }, []);

  const refreshJob = useCallback(
    async (jobId: string) => {
      try {
        replaceJob(await api.getJob(jobId));
      } catch (error) {
        notify('error', 'Could not refresh job', errorMessage(error));
      }
    },
    [notify, replaceJob],
  );

  const profileJob = useCallback(
    async (jobId: string) => {
      try {
        replaceJob(await api.profileJob(jobId));
        notify('info', 'Profiling complete', 'Review every column mapping before approving the set.');
      } catch (error) {
        notify('error', 'Profiling failed', errorMessage(error));
      }
    },
    [notify, replaceJob],
  );

  const recordMappingDecisions = useCallback(
    async (jobId: string, decisions: MappingDecisionInput[]) => {
      try {
        replaceJob(await api.recordMappingDecisions(jobId, decisions));
        notify('success', 'Mapping decisions saved', 'Decisions are attributed to the signed-in reviewer.');
      } catch (error) {
        notify('error', 'Mapping decisions not saved', errorMessage(error));
      }
    },
    [notify, replaceJob],
  );

  const approveMappings = useCallback(
    async (jobId: string, note = '') => {
      try {
        replaceJob(await api.approveMappings(jobId, note));
        notify('success', 'Mappings approved', 'The job is ready to run.');
      } catch (error) {
        notify('error', 'Mappings not approved', errorMessage(error));
      }
    },
    [notify, replaceJob],
  );

  const publishJob = useCallback(
    async (jobId: string) => {
      const job = jobs.find((item) => item.id === jobId);
      if (!job) return;
      const dataset = datasets.find((item) => item.id === job.datasetId);
      const task = dataset?.intendedTasks[0] ?? 'General clinical research';
      try {
        await api.runJob(jobId, task);
        const [updatedJob, updatedDataset, reports] = await Promise.all([
          api.getJob(jobId),
          api.getDataset(job.datasetId),
          api.getReports(job.datasetId),
        ]);
        const { quality, readiness, representativeness } = reports;
        replaceJob(updatedJob);
        setDatasets((prev) => prev.map((item) => (item.id === updatedDataset.id ? updatedDataset : item)));
        if (quality) setQualityReports((prev) => ({ ...prev, [updatedDataset.id]: quality }));
        if (readiness) setReadinessReports((prev) => ({ ...prev, [updatedDataset.id]: readiness }));
        if (representativeness) {
          setRepresentativenessReports((prev) => ({ ...prev, [updatedDataset.id]: representativeness }));
        }
        notify(
          'success',
          'ETL completed',
          `${updatedDataset.title} is pending governance review. Quality, readiness and representativeness reports were generated.`,
        );
      } catch (error) {
        notify('error', 'ETL failed', errorMessage(error));
        await Promise.allSettled([refreshJob(jobId), refreshDataset(job.datasetId)]);
      }
    },
    [datasets, jobs, notify, refreshDataset, refreshJob, replaceJob],
  );

  const cancelJob = useCallback(
    async (jobId: string) => {
      try {
        replaceJob(await api.cancelJob(jobId));
        notify('info', 'Job cancelled', 'No processed output was written.');
      } catch (error) {
        notify('error', 'Job not cancelled', errorMessage(error));
      }
    },
    [notify, replaceJob],
  );

  const rejectJob = useCallback(
    async (jobId: string, reason: string) => {
      try {
        replaceJob(await api.rejectJob(jobId, reason));
        notify('info', 'Job rejected', 'The rejection was recorded in the audit log.');
      } catch (error) {
        notify('error', 'Job not rejected', errorMessage(error));
      }
    },
    [notify, replaceJob],
  );

  const decideRequest = useCallback(
    async (requestId: string, status: Exclude<RequestStatus, 'Pending' | 'Withdrawn'>, note: string) => {
      try {
        const updated = await api.decideAccessRequest(requestId, status, note);
        setRequests((prev) => prev.map((item) => (item.id === requestId ? updated : item)));
        notify(status === 'Approved' ? 'success' : 'info', `Request ${status.toLowerCase()}`);
      } catch (error) {
        notify('error', 'Decision not saved', errorMessage(error));
      }
    },
    [notify],
  );

  const withdrawRequest = useCallback(
    async (requestId: string) => {
      try {
        const updated = await api.withdrawAccessRequest(requestId);
        setRequests((prev) => prev.map((item) => (item.id === requestId ? updated : item)));
        notify('info', 'Request withdrawn');
      } catch (error) {
        notify('error', 'Request not withdrawn', errorMessage(error));
      }
    },
    [notify],
  );

  const requestAccess = useCallback(
    async (datasetId: string, input: AccessRequestInput) => {
      try {
        const created = await api.requestAccess(datasetId, input);
        setRequests((prev) => [created, ...prev]);
        notify('success', 'Access request submitted', `${created.datasetTitle} is awaiting review.`);
        return true;
      } catch (error) {
        notify('error', 'Access request failed', errorMessage(error));
        return false;
      }
    },
    [notify],
  );

  const approveDataset = useCallback(
    async (datasetId: string, reason: string) => {
      try {
        const updated = await api.approveDataset(datasetId, reason);
        setDatasets((prev) => prev.map((item) => (item.id === datasetId ? updated : item)));
        notify('success', 'Dataset approved', `${updated.title} is now available.`);
      } catch (error) {
        notify('error', 'Approval failed', errorMessage(error));
      }
    },
    [notify],
  );

  const rejectDataset = useCallback(
    async (datasetId: string, reason: string) => {
      try {
        const updated = await api.rejectDataset(datasetId, reason);
        setDatasets((prev) => prev.map((item) => (item.id === datasetId ? updated : item)));
        notify('info', 'Changes requested', `${updated.title} was returned to the contributor.`);
      } catch (error) {
        notify('error', 'Decision failed', errorMessage(error));
      }
    },
    [notify],
  );

  const downloadDataset = useCallback(
    async (dataset: Dataset) => {
      try {
        await api.downloadDataset(dataset);
      } catch (error) {
        notify('error', 'Download failed', errorMessage(error));
      }
    },
    [notify],
  );

  const listDatasetVersions = useCallback(
    async (datasetId: string) => {
      try {
        const result = await api.listDatasetVersions(datasetId);
        setDatasetVersions((prev) => ({ ...prev, [datasetId]: result }));
        return result;
      } catch (error) {
        notify('error', 'Could not load dataset versions', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const getDatasetVersion = useCallback(
    async (datasetId: string, versionId: string) => {
      try {
        const version = await api.getDatasetVersion(datasetId, versionId);
        setDatasetVersions((prev) => {
          const current = prev[datasetId];
          if (!current) return prev;
          const versions = current.versions.some((item) => item.id === version.id)
            ? current.versions.map((item) => (item.id === version.id ? version : item))
            : [version, ...current.versions];
          return { ...prev, [datasetId]: { ...current, versions } };
        });
        return version;
      } catch (error) {
        notify('error', 'Could not load dataset version', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const getDatasetLineage = useCallback(
    async (datasetId: string) => {
      try {
        const lineage = await api.getDatasetLineage(datasetId);
        setDatasetLineage((prev) => ({ ...prev, [datasetId]: lineage }));
        return lineage;
      } catch (error) {
        notify('error', 'Could not load dataset lineage', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const compareDatasetVersions = useCallback(
    async (datasetId: string, versionAId: string, versionBId: string) => {
      try {
        return await api.compareDatasetVersions(datasetId, versionAId, versionBId);
      } catch (error) {
        notify('error', 'Version comparison failed', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const restoreDatasetVersion = useCallback(
    async (datasetId: string, versionId: string) => {
      try {
        const version = await api.restoreDatasetVersion(datasetId, versionId);
        const refreshed = await api.listDatasetVersions(datasetId);
        setDatasetVersions((prev) => ({ ...prev, [datasetId]: refreshed }));
        notify('success', 'Version restored', `${version.versionLabel} is now the current version.`);
        return version;
      } catch (error) {
        notify('error', 'Version restore failed', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const downloadDatasetVersion = useCallback(
    async (datasetId: string, versionId: string, filename: string) => {
      try {
        await api.downloadDatasetVersion(datasetId, versionId, filename);
      } catch (error) {
        notify('error', 'Version download failed', errorMessage(error));
      }
    },
    [notify],
  );

  const createDatasetVersion = useCallback(
    async (datasetId: string, note?: string) => {
      try {
        const version = await api.createDatasetVersion(datasetId, note);
        const refreshed = await api.listDatasetVersions(datasetId);
        setDatasetVersions((prev) => ({ ...prev, [datasetId]: refreshed }));
        notify('success', 'Version created', `${version.versionLabel} was stored by the backend.`);
        return version;
      } catch (error) {
        notify('error', 'Version creation failed', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const listSynthMedVersions = useCallback(
    async (datasetId: string) => {
      try {
        const versions = await api.listSynthMedVersions(datasetId);
        setSynthVersions((prev) => ({ ...prev, [datasetId]: versions }));
        return versions;
      } catch (error) {
        notify('error', 'Could not load SynthMed versions', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const getSynthMedVersion = useCallback(
    async (datasetId: string, versionId: string) => {
      try {
        const version = await api.getSynthMedVersion(datasetId, versionId);
        setSynthVersions((prev) => {
          const current = prev[datasetId] ?? [];
          const versions = current.some((item) => item.id === version.id)
            ? current.map((item) => (item.id === version.id ? version : item))
            : [version, ...current];
          return { ...prev, [datasetId]: versions };
        });
        return version;
      } catch (error) {
        notify('error', 'Could not load SynthMed version', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const getSynthMedDatasetLineage = useCallback(
    async (datasetId: string) => {
      try {
        const lineage = await api.getSynthMedDatasetLineage(datasetId);
        setSynthLineage((prev) => ({ ...prev, [datasetId]: lineage }));
        return lineage;
      } catch (error) {
        notify('error', 'Could not load SynthMed lineage', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const compareSynthMedVersions = useCallback(
    async (datasetId: string, versionAId: string, versionBId: string) => {
      try {
        return await api.compareSynthMedVersions(datasetId, versionAId, versionBId);
      } catch (error) {
        notify('error', 'SynthMed version comparison failed', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const restoreSynthMedVersion = useCallback(
    async (datasetId: string, versionId: string) => {
      try {
        const version = await api.restoreSynthMedVersion(datasetId, versionId);
        const refreshed = await api.listSynthMedVersions(datasetId);
        setSynthVersions((prev) => ({ ...prev, [datasetId]: refreshed }));
        notify('success', 'SynthMed version restored', `${version.versionLabel} is now the active version.`);
        return version;
      } catch (error) {
        notify('error', 'SynthMed version restore failed', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const downloadSynthMedVersion = useCallback(
    async (datasetId: string, versionId: string, filename: string) => {
      try {
        await api.downloadSynthMedVersion(datasetId, versionId, filename);
      } catch (error) {
        notify('error', 'SynthMed version download failed', errorMessage(error));
      }
    },
    [notify],
  );

  const listSynthMedExperiments = useCallback(async () => {
    try {
      const experiments = await api.listSynthMedExperiments();
      setSynthExperiments(experiments);
      return experiments;
    } catch (error) {
      notify('error', 'Could not load experiments', errorMessage(error));
      throw error;
    }
  }, [notify]);

  const getSynthMedExperiment = useCallback(
    async (experimentId: string) => {
      try {
        const experiment = await api.getSynthMedExperiment(experimentId);
        setSynthExperiments((prev) =>
          prev.some((item) => item.id === experiment.id)
            ? prev.map((item) => (item.id === experiment.id ? experiment : item))
            : [experiment, ...prev],
        );
        return experiment;
      } catch (error) {
        notify('error', 'Could not load experiment', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const createSynthMedExperiment = useCallback(
    async (payload: SynthMedExperimentCreatePayload) => {
      try {
        const experiment = await api.createSynthMedExperiment(payload);
        setSynthExperiments((prev) => [experiment, ...prev.filter((item) => item.id !== experiment.id)]);
        notify('success', 'Experiment created', experiment.name);
        return experiment;
      } catch (error) {
        notify('error', 'Experiment could not be created', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const reuseSynthMedExperimentConfiguration = useCallback(
    async (experimentId: string, payload: SynthMedExperimentReusePayload = {}) => {
      try {
        const job = await api.reuseSynthMedExperimentConfiguration(experimentId, payload);
        setSynthJobs((prev) => [job, ...prev.filter((item) => item.id !== job.id)]);
        const warnings = (job.config as { reuseWarnings?: unknown }).reuseWarnings;
        notify(
          Array.isArray(warnings) && warnings.length > 0 ? 'info' : 'success',
          'Generation job started from snapshot',
          `${job.id} · ${job.status.toLowerCase()}`,
        );
        return job;
      } catch (error) {
        notify('error', 'Configuration could not be reused', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const getSynthMedExperimentReport = useCallback(
    async (experimentId: string) => {
      try {
        return await api.getSynthMedExperimentReport(experimentId);
      } catch (error) {
        notify('error', 'Could not load experiment report', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const downloadSynthMedExperimentReport = useCallback(
    async (experimentId: string) => {
      try {
        await api.downloadSynthMedExperimentReport(experimentId);
      } catch (error) {
        notify('error', 'Experiment report download failed', errorMessage(error));
      }
    },
    [notify],
  );

  const getSynthMedExperimentHistory = useCallback(
    async (experimentId: string) => {
      try {
        return await api.getSynthMedExperimentHistory(experimentId);
      } catch (error) {
        notify('error', 'Could not load experiment history', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const getSynthMedExperimentConfigurations = useCallback(
    async (experimentId: string) => {
      try {
        return await api.getSynthMedExperimentConfigurations(experimentId);
      } catch (error) {
        notify('error', 'Could not load configuration snapshots', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const listResearchReports = useCallback(
    async (reportType?: ResearchReportType) => {
      try {
        return await api.listResearchReports(reportType);
      } catch (error) {
        notify('error', 'Could not load research reports', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const getResearchReport = useCallback(
    async (reportId: string) => {
      try {
        return await api.getResearchReport(reportId);
      } catch (error) {
        notify('error', 'Could not load research report', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const getResearchReportStatus = useCallback(
    async (reportId: string) => {
      try {
        return await api.getResearchReportStatus(reportId);
      } catch (error) {
        notify('error', 'Could not load report status', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const createResearchReport = useCallback(
    async (reportType: ResearchReportType, payload: ResearchReportGeneratePayload) => {
      try {
        const report = await api.createResearchReport(reportType, payload);
        notify('success', 'Research report queued', report.reportId);
        return report;
      } catch (error) {
        notify('error', 'Research report could not be generated', errorMessage(error));
        throw error;
      }
    },
    [notify],
  );

  const downloadResearchReport = useCallback(
    async (reportId: string) => {
      try {
        await api.downloadResearchReport(reportId);
      } catch (error) {
        notify('error', 'Research report download failed', errorMessage(error));
      }
    },
    [notify],
  );

  const value = useMemo<DemoStore | null>(() => {
    if (!user) return null;
    return {
      user,
      role: user.role,
      theme,
      setTheme,
      datasets,
      jobs,
      synthSources,
      synthGenerated,
      synthJobs,
      synthComparisons,
      datasetVersions,
      datasetLineage,
      synthVersions,
      synthLineage,
      synthExperiments,
      requests,
      qualityReports,
      readinessReports,
      representativenessReports,
      toasts,
      notify,
      dismissToast,
      logout,
      updateProfile,
      changePassword,
      requestPasswordReset,
      verifyPasswordReset,
      refresh,
      uploadDataset,
      uploadSynthMedSource,
      createSynthMedSourceFromRepository,
      registerGeneratedDataset,
      refreshSynthMed,
      getSynthMedSource,
      downloadSynthMedSource,
      downloadSynthMedGenerated,
      analyseSynthMedGeneration,
      listSynthMedModels,
      getSynthMedDatasetColumns,
      listSynthMedClinicalReferences,
      getSynthMedMedicalProfile,
      validateSynthMedSourceClinical,
      validateSynthMedConditions,
      startSynthMedGeneration,
      listSynthMedGenerationJobs,
      getSynthMedGenerationJob,
      getSynthMedGenerationJobConditions,
      getSynthMedGeneratedConditions,
      getSynthMedGeneratedEvaluation,
      getSynthMedGeneratedDetail,
      getSynthMedGeneratedPreview,
      getSynthMedClinicalReport,
      getSynthMedQualityReport,
      getSynthMedPrivacyReport,
      exportSynthMedGenerated,
      downloadSynthMedGeneratedFormat,
      downloadSynthMedReport,
      listSynthMedComparisons,
      getSynthMedComparison,
      createSynthMedComparison,
      downloadSynthMedComparisonReport,
      createSynthMedUtilityEvaluation,
      listSynthMedUtilityEvaluations,
      getSynthMedUtilityEvaluation,
      getSynthMedUtilityEvaluationReport,
      downloadSynthMedUtilityEvaluationReport,
      refreshJob,
      profileJob,
      recordMappingDecisions,
      approveMappings,
      publishJob,
      cancelJob,
      rejectJob,
      decideRequest,
      withdrawRequest,
      requestAccess,
      approveDataset,
      rejectDataset,
      downloadDataset,
      listDatasetVersions,
      getDatasetVersion,
      getDatasetLineage,
      compareDatasetVersions,
      restoreDatasetVersion,
      downloadDatasetVersion,
      createDatasetVersion,
      listSynthMedVersions,
      getSynthMedVersion,
      getSynthMedDatasetLineage,
      compareSynthMedVersions,
      restoreSynthMedVersion,
      downloadSynthMedVersion,
      listSynthMedExperiments,
      getSynthMedExperiment,
      createSynthMedExperiment,
      reuseSynthMedExperimentConfiguration,
      getSynthMedExperimentReport,
      downloadSynthMedExperimentReport,
      getSynthMedExperimentHistory,
      getSynthMedExperimentConfigurations,
      listResearchReports,
      getResearchReport,
      getResearchReportStatus,
      createResearchReport,
      downloadResearchReport,
    };
  }, [
    user,
    theme,
    setTheme,
    datasets,
    jobs,
    synthSources,
    synthGenerated,
    synthJobs,
    synthComparisons,
    datasetVersions,
    datasetLineage,
    synthVersions,
    synthLineage,
    synthExperiments,
    requests,
    qualityReports,
    readinessReports,
    representativenessReports,
    toasts,
    notify,
    dismissToast,
    logout,
    updateProfile,
    changePassword,
    requestPasswordReset,
    verifyPasswordReset,
    refresh,
    uploadDataset,
    uploadSynthMedSource,
    createSynthMedSourceFromRepository,
    registerGeneratedDataset,
    refreshSynthMed,
    getSynthMedSource,
    downloadSynthMedSource,
    downloadSynthMedGenerated,
    analyseSynthMedGeneration,
    listSynthMedModels,
    getSynthMedDatasetColumns,
    listSynthMedClinicalReferences,
    getSynthMedMedicalProfile,
    validateSynthMedSourceClinical,
    validateSynthMedConditions,
    startSynthMedGeneration,
    listSynthMedGenerationJobs,
    getSynthMedGenerationJob,
    getSynthMedGenerationJobConditions,
    getSynthMedGeneratedConditions,
    getSynthMedGeneratedEvaluation,
    getSynthMedGeneratedDetail,
    getSynthMedGeneratedPreview,
    getSynthMedClinicalReport,
    getSynthMedQualityReport,
    getSynthMedPrivacyReport,
    exportSynthMedGenerated,
    downloadSynthMedGeneratedFormat,
    downloadSynthMedReport,
    listSynthMedComparisons,
    getSynthMedComparison,
    createSynthMedComparison,
    downloadSynthMedComparisonReport,
    createSynthMedUtilityEvaluation,
    listSynthMedUtilityEvaluations,
    getSynthMedUtilityEvaluation,
    getSynthMedUtilityEvaluationReport,
    downloadSynthMedUtilityEvaluationReport,
    refreshJob,
    profileJob,
    recordMappingDecisions,
    approveMappings,
    publishJob,
    cancelJob,
    rejectJob,
    decideRequest,
    withdrawRequest,
    requestAccess,
    approveDataset,
    rejectDataset,
    downloadDataset,
    listDatasetVersions,
    getDatasetVersion,
    getDatasetLineage,
    compareDatasetVersions,
    restoreDatasetVersion,
    downloadDatasetVersion,
    createDatasetVersion,
    listSynthMedVersions,
    getSynthMedVersion,
    getSynthMedDatasetLineage,
    compareSynthMedVersions,
    restoreSynthMedVersion,
    downloadSynthMedVersion,
    listSynthMedExperiments,
    getSynthMedExperiment,
    createSynthMedExperiment,
    reuseSynthMedExperimentConfiguration,
    getSynthMedExperimentReport,
    downloadSynthMedExperimentReport,
    getSynthMedExperimentHistory,
    getSynthMedExperimentConfigurations,
    listResearchReports,
    getResearchReport,
    getResearchReportStatus,
    createResearchReport,
    downloadResearchReport,
  ]);

  if (booting) {
    return (
      <div className="page-loading auth-loading">
        <LoadingState label="Connecting to MedDataHub API..." />
      </div>
    );
  }

  if (!value) {
    return (
      <LoginScreen
        apiBase={import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'}
        onLogin={login}
        onRegister={register}
        onRequestPasswordReset={requestPasswordReset}
        onVerifyPasswordReset={verifyPasswordReset}
      />
    );
  }

  return <DemoContext.Provider value={value}>{children}</DemoContext.Provider>;
};

export const useDemo = () => {
  const context = useContext(DemoContext);
  if (!context) throw new Error('useDemo must be used inside DemoProvider');
  return context;
};
