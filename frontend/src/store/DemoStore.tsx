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
import { ApiError, api, reportMaps, tokenStore } from '../lib/api';
import type {
  AccessLevel,
  AccessRequest,
  CurrentUser,
  Dataset,
  Domain,
  EtlJob,
  ExtractPreview,
  FileFormat,
  QualityReport,
  ReadinessReport,
  RepresentativenessReport,
  RequestStatus,
  Role,
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
  datasets: Dataset[];
  jobs: EtlJob[];
  requests: AccessRequest[];
  qualityReports: Record<string, QualityReport>;
  readinessReports: Record<string, ReadinessReport>;
  representativenessReports: Record<string, RepresentativenessReport>;
  toasts: ToastMessage[];
  notify: (type: ToastMessage['type'], title: string, message?: string) => void;
  dismissToast: (id: string) => void;
  logout: () => void;
  updateProfile: (input: { fullName: string; organisation: string; title: string }) => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<boolean>;
  refresh: () => Promise<void>;
  uploadDataset: (input: UploadInput) => Promise<string>;
  resolveMapping: (jobId: string, source: string, decision: 'Approved' | 'Unmapped') => Promise<void>;
  publishJob: (jobId: string) => Promise<void>;
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

const errorMessage = (error: unknown) => (error instanceof Error ? error.message : 'Unexpected API error');

export const DemoProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [booting, setBooting] = useState(true);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [jobs, setJobs] = useState<EtlJob[]>([]);
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
      }, 6000);
      toastTimersRef.current.push(timer);
    },
    [],
  );

  const resetWorkspace = useCallback(() => {
    setDatasets([]);
    setJobs([]);
    setRequests([]);
    setQualityReports({});
    setReadinessReports({});
    setRepresentativenessReports({});
  }, []);

  const loadWorkspace = useCallback(async () => {
    const [datasetList, jobList, requestList] = await Promise.all([
      api.listDatasets(),
      api.listJobs(),
      api.listAccessRequests(),
    ]);
    const reportBundles = await Promise.all(
      datasetList.map(async (dataset) => {
        try {
          return await api.getReports(dataset.id);
        } catch (error) {
          if (error instanceof ApiError && error.status === 404) {
            return { quality: null, readiness: null, representativeness: null };
          }
          throw error;
        }
      }),
    );
    const maps = reportMaps.from(reportBundles);
    setDatasets(datasetList);
    setJobs(jobList);
    setRequests(requestList);
    setQualityReports(maps.qualityReports);
    setReadinessReports(maps.readinessReports);
    setRepresentativenessReports(maps.representativenessReports);
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
      } catch {
        tokenStore.clear();
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
      setUser(current);
      try {
        await loadWorkspace();
      } catch (error) {
        logout();
        throw error;
      }
    },
    [loadWorkspace, logout],
  );

  const register = useCallback(
    async (input: {
      email: string;
      password: string;
      fullName: string;
      organisation: string;
      title: string;
    }) => {
      const current = await api.register(input);
      setUser(current);
      try {
        await loadWorkspace();
      } catch (error) {
        logout();
        throw error;
      }
    },
    [loadWorkspace, logout],
  );

  const updateProfile = useCallback(
    async (input: { fullName: string; organisation: string; title: string }) => {
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

  const resolveMapping = useCallback(
    async (jobId: string, source: string, decision: 'Approved' | 'Unmapped') => {
      const job = jobs.find((item) => item.id === jobId);
      if (!job) return;
      const mapping: Record<string, string | null> = {};
      for (const item of job.mappings) {
        if (item.status === 'Approved' && item.target) mapping[item.source] = item.target;
        if (item.status === 'Unmapped') mapping[item.source] = null;
      }
      mapping[source] = decision === 'Approved' ? job.mappings.find((item) => item.source === source)?.target ?? null : null;
      try {
        const updated = await api.saveMappings(jobId, mapping);
        setJobs((prev) => prev.map((item) => (item.id === jobId ? updated : item)));
        notify(
          decision === 'Approved' ? 'success' : 'info',
          `Mapping ${decision.toLowerCase()}`,
          'The decision was saved to the ETL job.',
        );
      } catch (error) {
        notify('error', 'Mapping not saved', errorMessage(error));
      }
    },
    [jobs, notify],
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
        setJobs((prev) => prev.map((item) => (item.id === jobId ? updatedJob : item)));
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
        await Promise.allSettled([
          api.getJob(jobId).then((updated) => setJobs((prev) => prev.map((item) => (item.id === jobId ? updated : item)))),
          refreshDataset(job.datasetId),
        ]);
      }
    },
    [datasets, jobs, notify, refreshDataset],
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
      datasets,
      jobs,
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
      refresh,
      uploadDataset,
      resolveMapping,
      publishJob,
      decideRequest,
      withdrawRequest,
      requestAccess,
      approveDataset,
      rejectDataset,
      downloadDataset,
    };
  }, [
    user,
    datasets,
    jobs,
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
    refresh,
    uploadDataset,
    resolveMapping,
    publishJob,
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
