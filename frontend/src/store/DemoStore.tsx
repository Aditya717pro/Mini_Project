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
import { LoginScreen } from '../components/LoginScreen';
import { LoadingState } from '../components/ui';
import { ApiError, api, reportMaps, tokenStore, type SynthMedUploadPayload } from '../lib/api';
import type {
  AccessLevel,
  AccessRequest,
  CurrentUser,
  Dataset,
  Domain,
  EtlJob,
  ExtractPreview,
  FileFormat,
  MappingDecisionInput,
  QualityReport,
  ReadinessReport,
  RepresentativenessReport,
  RequestStatus,
  Role,
  SynthMedDownloads,
  SynthMedEvaluationReport,
  SynthMedExportResponse,
  SynthMedGeneratedDataset,
  SynthMedGeneratedDatasetDetail,
  SynthMedGeneratedPreview,
  SynthMedGenerationAnalysis,
  SynthMedGenerationJob,
  SynthMedGenerationStartPayload,
  SynthMedSourceDataset,
  ThemeMode,
  ToastMessage,
} from '../types';

export interface UploadInput {
  file: File;
  checksum: string;
  preview: ExtractPreview;
  format: FileFormat;
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
  uploadDataset: (input: UploadInput) => Promise<string>;
  uploadSynthMedSource: (input: SynthMedUploadPayload, onProgress: (percent: number) => void) => Promise<string>;
  refreshSynthMed: () => Promise<SynthMedDownloads>;
  getSynthMedSource: (datasetId: string) => Promise<SynthMedSourceDataset>;
  downloadSynthMedSource: (dataset: SynthMedSourceDataset) => Promise<void>;
  downloadSynthMedGenerated: (dataset: SynthMedGeneratedDataset) => Promise<void>;
  analyseSynthMedGeneration: (sourceDatasetId: string) => Promise<SynthMedGenerationAnalysis>;
  startSynthMedGeneration: (payload: SynthMedGenerationStartPayload) => Promise<SynthMedGenerationJob>;
  listSynthMedGenerationJobs: () => Promise<SynthMedGenerationJob[]>;
  getSynthMedGenerationJob: (jobId: string) => Promise<SynthMedGenerationJob>;
  getSynthMedGeneratedDetail: (generatedId: string) => Promise<SynthMedGeneratedDatasetDetail>;
  getSynthMedGeneratedPreview: (
    generatedId: string,
    page: number,
    pageSize: number,
  ) => Promise<SynthMedGeneratedPreview>;
  getSynthMedQualityReport: (generatedId: string) => Promise<SynthMedEvaluationReport>;
  getSynthMedPrivacyReport: (generatedId: string) => Promise<SynthMedEvaluationReport>;
  exportSynthMedGenerated: (generatedId: string, format: FileFormat) => Promise<SynthMedExportResponse>;
  downloadSynthMedGeneratedFormat: (generatedId: string, format: FileFormat) => Promise<void>;
  downloadSynthMedReport: (generatedId: string, reportType: string) => Promise<void>;
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
  return 'default';
};

export const DemoProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [theme, setThemeState] = useState<ThemeMode>(initialTheme);
  const [booting, setBooting] = useState(true);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [jobs, setJobs] = useState<EtlJob[]>([]);
  const [synthSources, setSynthSources] = useState<SynthMedSourceDataset[]>([]);
  const [synthGenerated, setSynthGenerated] = useState<SynthMedGeneratedDataset[]>([]);
  const [synthJobs, setSynthJobs] = useState<SynthMedGenerationJob[]>([]);
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
    setRequests([]);
    setQualityReports({});
    setReadinessReports({});
    setRepresentativenessReports({});
  }, []);

  const loadWorkspace = useCallback(async () => {
    try {
      const [datasetList, jobList, requestList, synthDownloads, generationJobs] = await Promise.all([
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
  }, [resetWorkspace]);

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
      await loadWorkspace();
    },
    [loadWorkspace],
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
      await loadWorkspace();
    },
    [loadWorkspace],
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
        return result.dataset.id;
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

  const getSynthMedGeneratedDetail = useCallback(
    async (generatedId: string) => api.getSynthMedGeneratedDetail(generatedId),
    [],
  );

  const getSynthMedGeneratedPreview = useCallback(
    async (generatedId: string, page: number, pageSize: number) =>
      api.getSynthMedGeneratedPreview(generatedId, page, pageSize),
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
      refreshSynthMed,
      getSynthMedSource,
      downloadSynthMedSource,
      downloadSynthMedGenerated,
      analyseSynthMedGeneration,
      startSynthMedGeneration,
      listSynthMedGenerationJobs,
      getSynthMedGenerationJob,
      getSynthMedGeneratedDetail,
      getSynthMedGeneratedPreview,
      getSynthMedQualityReport,
      getSynthMedPrivacyReport,
      exportSynthMedGenerated,
      downloadSynthMedGeneratedFormat,
      downloadSynthMedReport,
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
    refreshSynthMed,
    getSynthMedSource,
    downloadSynthMedSource,
    downloadSynthMedGenerated,
    analyseSynthMedGeneration,
    startSynthMedGeneration,
    listSynthMedGenerationJobs,
    getSynthMedGenerationJob,
    getSynthMedGeneratedDetail,
    getSynthMedGeneratedPreview,
    getSynthMedQualityReport,
    getSynthMedPrivacyReport,
    exportSynthMedGenerated,
    downloadSynthMedGeneratedFormat,
    downloadSynthMedReport,
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
