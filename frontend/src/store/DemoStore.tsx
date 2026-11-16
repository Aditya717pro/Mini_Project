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
import {
  accessRequests as seedAccessRequests,
  buildQualityReport,
  buildReadinessReport,
  buildRepresentativenessReport,
  currentUser,
  datasets as seedDatasets,
  etlJobs as seedJobs,
  qualityReports as seedQualityReports,
  readinessReports as seedReadinessReports,
  representativenessReports as seedRepresentativenessReports,
} from '../data/mockData';
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
  setRole: (role: Role) => void;
  datasets: Dataset[];
  jobs: EtlJob[];
  requests: AccessRequest[];
  qualityReports: Record<string, QualityReport>;
  readinessReports: Record<string, ReadinessReport>;
  representativenessReports: Record<string, RepresentativenessReport>;
  toasts: ToastMessage[];
  notify: (type: ToastMessage['type'], title: string, message?: string) => void;
  dismissToast: (id: string) => void;
  uploadDataset: (input: UploadInput) => string;
  resolveMapping: (jobId: string, source: string, decision: 'Approved' | 'Unmapped') => void;
  publishJob: (jobId: string) => void;
  decideRequest: (requestId: string, status: Exclude<RequestStatus, 'Pending' | 'Withdrawn'>, note: string) => void;
  withdrawRequest: (requestId: string) => void;
  requestAccess: (datasetId: string, input: AccessRequestInput) => boolean;
}

const DemoContext = createContext<DemoStore | null>(null);

const clamp = (value: number, min = 0, max = 100) => Math.min(max, Math.max(min, value));

const nowIso = () => new Date().toISOString();

const makeId = (prefix: string) =>
  `${prefix}-${new Date().getFullYear()}-${String(Math.floor(1000 + Math.random() * 9000))}`;

export const DemoProvider = ({ children }: { children: ReactNode }) => {
  const [role, setRoleState] = useState<Role>(currentUser.role);
  const [datasets, setDatasets] = useState<Dataset[]>(seedDatasets);
  const [jobs, setJobs] = useState<EtlJob[]>(seedJobs);
  const [requests, setRequests] = useState<AccessRequest[]>(seedAccessRequests);
  const [qualityReports, setQualityReports] = useState<Record<string, QualityReport>>(seedQualityReports);
  const [readinessReports, setReadinessReports] = useState<Record<string, ReadinessReport>>(seedReadinessReports);
  const [representativenessReports, setRepresentativenessReports] =
    useState<Record<string, RepresentativenessReport>>(seedRepresentativenessReports);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const timersRef = useRef<number[]>([]);
  const toastTimersRef = useRef<number[]>([]);

  useEffect(() => {
    return () => {
      timersRef.current.forEach((timer) => window.clearInterval(timer));
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

  const setRole = useCallback(
    (nextRole: Role) => {
      setRoleState(nextRole);
      notify('info', `Demo role switched to ${nextRole}`, 'Role switching is a UI demonstration only. It is not authentication.');
    },
    [notify],
  );

  const uploadDataset = useCallback(
    (input: UploadInput) => {
      const datasetId = makeId('DS');
      const jobId = makeId('JOB');
      const timestamp = nowIso();
      const recordCount = input.preview.rowCount;
      const columnCount = input.preview.columnCount;
      const geoList = input.geography
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean);
      const scoreSeed = recordCount % 7;

      const qualityScore = clamp(
        Math.round(100 - input.preview.missingPct * 0.8 - input.preview.duplicatePct * 1.5) - (columnCount > 40 ? 2 : 0),
        45,
        98,
      );

      let readiness = 48;
      if (input.dataDictionaryAvailable) readiness += 10;
      if (input.ethicsApproved) readiness += 8;
      if (input.labelColumn.trim()) readiness += 12;
      if (input.intendedTasks.length > 0) readiness += 5;
      if (input.description.trim().length > 80) readiness += 5;
      if (geoList.length > 0) readiness += 4;
      readiness += Math.max(0, Math.round((100 - Math.min(100, input.preview.missingPct * 4)) * 0.1));
      const readinessScore = clamp(readiness, 40, 95);

      const representativenessScore = clamp(
        54 + (input.ageRange.trim() ? 6 : 0) + (geoList.length > 1 ? 9 : 0) + (scoreSeed % 6),
        35,
        88,
      );

      const baseDataset: Dataset = {
        id: datasetId,
        title: input.title.trim(),
        description: input.description.trim(),
        domain: input.domain,
        access: input.access,
        status: 'Processing',
        owner: currentUser.name,
        ownerOrganisation: currentUser.organisation,
        format: input.format,
        records: recordCount,
        columns: columnCount,
        sizeMb: Math.round((input.file.size / 1024 / 1024) * 10) / 10,
        createdAt: timestamp,
        updatedAt: timestamp,
        version: 'v1.0',
        qualityScore: null,
        readinessScore: null,
        representativenessScore: null,
        tags: input.tags,
        ageRange: input.ageRange.trim() || 'Not specified',
        geography: geoList.length > 0 ? geoList : ['Not recorded'],
        ethicsApproved: input.ethicsApproved,
        license: input.license.trim() || 'Not specified',
        studyDesign: input.studyDesign.trim() || 'Not specified',
        collectionPeriod: 'Not specified',
        dataDictionaryAvailable: input.dataDictionaryAvailable,
        consentScope: input.ethicsApproved ? 'Declared by contributor (demo)' : 'Not declared',
        checksum: input.checksum,
        missingRate: input.preview.missingPct,
        duplicateRate: input.preview.duplicatePct,
        intendedTasks: input.intendedTasks,
        labelColumn: input.labelColumn.trim() || null,
        versions: [
          {
            version: 'v1.0',
            date: timestamp,
            note: 'Initial upload. File profiled in the browser demo; original retained locally.',
            records: recordCount,
            checksum: input.checksum,
            status: 'Current',
          },
        ],
        isLocalPreview: true,
      };

      const finalDataset: Dataset = {
        ...baseDataset,
        status: 'Pending review',
        qualityScore,
        readinessScore,
        representativenessScore,
        updatedAt: nowIso(),
      };

      const finalQuality = buildQualityReport(finalDataset);
      const finalReadiness = buildReadinessReport(finalDataset);
      const finalRepresentativeness = buildRepresentativenessReport(finalDataset);

      setDatasets((prev) => [baseDataset, ...prev]);

      const initialJob: EtlJob = {
        id: jobId,
        datasetId,
        datasetTitle: baseDataset.title,
        status: 'Queued',
        progress: 0,
        stages: [
          { key: 'extract', label: 'Extract', state: 'Queued', detail: 'Waiting to start' },
          { key: 'transform', label: 'Transform', state: 'Queued', detail: 'Waiting for extract' },
          { key: 'load', label: 'Load', state: 'Queued', detail: 'Waiting for transform' },
        ],
        logs: [
          {
            time: timestamp,
            level: 'INFO',
            stage: 'extract',
            message: `Upload accepted in the browser demo. SHA-256 ${input.checksum.slice(0, 16)}…`,
          },
        ],
        startedAt: timestamp,
        finishedAt: null,
        rowsIn: recordCount,
        rowsOut: recordCount,
        mappings: input.preview.columns.slice(0, 4).map((column, index) => ({
          source: column.name,
          target: column.name
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '_')
            .replace(/^_+|_+$/g, ''),
          confidence: index === 0 ? 0.72 : 0.94 - index * 0.05,
          status: index === 0 ? 'Suggested' : 'Approved',
          note:
            index === 0
              ? 'Generated by name similarity only; requires contributor confirmation.'
              : 'Name-based suggestion for demo purposes; verify against the data dictionary.',
        })),
      };

      setJobs((prev) => [initialJob, ...prev]);

      const extractionDetail = `${recordCount.toLocaleString()} rows · ${columnCount} columns · ${input.preview.missingPct}% missing cells`;
      const logs: EtlJob['logs'] = [
        {
          time: nowIso(),
          level: 'INFO',
          stage: 'extract',
          message: `Extract started. ${extractionDetail}. File size ${baseDataset.sizeMb} MB.`,
        },
        {
          time: nowIso(),
          level: 'INFO',
          stage: 'extract',
          message: `Column types inferred across ${columnCount} fields. ${input.preview.duplicateRows} duplicate row(s) flagged.`,
        },
        {
          time: nowIso(),
          level: 'WARN',
          stage: 'transform',
          message: 'Column mapping requires review. Name similarity alone is not treated as equivalence.',
        },
        {
          time: nowIso(),
          level: 'INFO',
          stage: 'transform',
          message: 'Original values retained. No records removed, imputed or overwritten.',
        },
        {
          time: nowIso(),
          level: 'INFO',
          stage: 'load',
          message: 'Processed artefact staged. Dataset submitted for governance review; download remains disabled.',
        },
      ];

      let step = 0;
      const timer = window.setInterval(() => {
        step += 1;
        const progressByStep = [8, 22, 41, 63, 82, 100];
        const progress = progressByStep[Math.min(step - 1, 5)];

        setJobs((prev) =>
          prev.map((job) => {
            if (job.id !== jobId) return job;
            const stages = job.stages.map((stage) => ({ ...stage }));
            if (step === 1) {
              stages[0] = { ...stages[0], state: 'Running', detail: 'Parsing uploaded file structure' };
            }
            if (step === 2) {
              stages[0] = { ...stages[0], state: 'Completed', detail: extractionDetail };
              stages[1] = { ...stages[1], state: 'Running', detail: 'Normalising names and profiling types' };
            }
            if (step === 3) {
              stages[1] = { ...stages[1], state: 'Running', detail: 'Mapping to common schema (demo rules)' };
            }
            if (step === 4) {
              stages[1] = { ...stages[1], state: 'Completed', detail: 'Mapping suggestions generated for review' };
              stages[2] = { ...stages[2], state: 'Running', detail: 'Staging processed artefact' };
            }
            if (step >= 5) {
              stages[2] = { ...stages[2], state: 'Completed', detail: 'Staged · awaiting governance review' };
            }
            return {
              ...job,
              progress,
              status: step >= 6 ? 'Completed' : 'Running',
              stages,
              logs: step === 5 ? [...job.logs, ...logs.slice(0, 3)] : job.logs,
              finishedAt: step >= 6 ? nowIso() : job.finishedAt,
            };
          }),
        );

        if (step >= 6) {
          window.clearInterval(timer);
          setDatasets((prev) => prev.map((dataset) => (dataset.id === datasetId ? finalDataset : dataset)));
          if (finalQuality) {
            setQualityReports((prev) => ({ ...prev, [datasetId]: finalQuality }));
          }
          if (finalReadiness) {
            setReadinessReports((prev) => ({ ...prev, [datasetId]: finalReadiness }));
          }
          if (finalRepresentativeness) {
            setRepresentativenessReports((prev) => ({ ...prev, [datasetId]: finalRepresentativeness }));
          }
          notify(
            'success',
            'Processing preview complete',
            'Quality, readiness and representativeness previews were generated locally. Dataset is pending governance review.',
          );
        }
      }, 1100);
      timersRef.current.push(timer);

      return datasetId;
    },
    [notify],
  );

  const resolveMapping = useCallback(
    (jobId: string, source: string, decision: 'Approved' | 'Unmapped') => {
      setJobs((prev) =>
        prev.map((job) => {
          if (job.id !== jobId) return job;
          const mappings = job.mappings.map((mapping) =>
            mapping.source === source ? { ...mapping, status: decision } : mapping,
          );
          return {
            ...job,
            mappings,
            logs: [
              ...job.logs,
              {
                time: nowIso(),
                level: decision === 'Approved' ? 'INFO' : 'WARN',
                stage: 'transform',
                message:
                  decision === 'Approved'
                    ? `Contributor approved mapping “${source}”. Original values retained.`
                    : `Mapping “${source}” marked unmapped. The field will not be loaded into the common schema.`,
              },
            ],
          };
        }),
      );
      notify('info', `Mapping ${decision.toLowerCase()}`, 'This mapping change is held in the browser demo only.');
    },
    [notify],
  );

  const publishJob = useCallback(
    (jobId: string) => {
      const job = jobs.find((item) => item.id === jobId);
      if (!job) return;
      setJobs((prev) =>
        prev.map((item) =>
          item.id === jobId
            ? {
                ...item,
                status: 'Completed',
                progress: 100,
                finishedAt: nowIso(),
                stages: item.stages.map((stage) =>
                  stage.key === 'load'
                    ? { ...stage, state: 'Completed', detail: 'Staged · submitted for governance review' }
                    : stage,
                ),
                logs: [
                  ...item.logs,
                  {
                    time: nowIso(),
                    level: 'INFO',
                    stage: 'load',
                    message: 'Mapping review complete. Processed artefact staged and submitted for governance review.',
                  },
                ],
              }
            : item,
        ),
      );
      setDatasets((prev) =>
        prev.map((dataset) =>
          dataset.id === job.datasetId
            ? { ...dataset, status: 'Pending review', updatedAt: nowIso() }
            : dataset,
        ),
      );
      notify('success', 'Load staged', `${job.datasetTitle} is pending governance review. It is not publicly available.`);
    },
    [jobs, notify],
  );

  const decideRequest = useCallback(
    (requestId: string, status: Exclude<RequestStatus, 'Pending' | 'Withdrawn'>, note: string) => {
      const request = requests.find((item) => item.id === requestId);
      setRequests((prev) =>
        prev.map((item) =>
          item.id === requestId
            ? {
                ...item,
                status,
                decidedAt: nowIso(),
                reviewer: currentUser.name,
                decisionNote: note.trim() || (status === 'Approved' ? 'Approved under the data-use agreement.' : 'Rejected.'),
              }
            : item,
        ),
      );
      notify(
        status === 'Approved' ? 'success' : 'info',
        `Request ${status.toLowerCase()}`,
        request ? `${request.id} · ${request.datasetTitle}` : undefined,
      );
    },
    [notify, requests],
  );

  const withdrawRequest = useCallback(
    (requestId: string) => {
      setRequests((prev) =>
        prev.map((item) =>
          item.id === requestId
            ? { ...item, status: 'Withdrawn', decidedAt: nowIso(), reviewer: currentUser.name }
            : item,
        ),
      );
      notify('info', 'Request withdrawn');
    },
    [notify],
  );

  const requestAccess = useCallback(
    (datasetId: string, input: AccessRequestInput) => {
      const dataset = datasets.find((item) => item.id === datasetId);
      if (!dataset) {
        notify('error', 'Dataset not found');
        return false;
      }
      const duplicate = requests.some(
        (request) =>
          request.datasetId === datasetId &&
          request.direction === 'Outgoing' &&
          request.status === 'Pending',
      );
      if (duplicate) {
        notify('error', 'Request already pending', 'You already have a pending request for this dataset.');
        return false;
      }
      const request: AccessRequest = {
        id: makeId('AR'),
        datasetId: dataset.id,
        datasetTitle: dataset.title,
        requester: currentUser.name,
        role,
        organisation: currentUser.organisation,
        purpose: input.purpose.trim(),
        projectTitle: input.projectTitle.trim(),
        requestedAt: nowIso(),
        status: 'Pending',
        decidedAt: null,
        reviewer: null,
        decisionNote: null,
        direction: 'Outgoing',
      };
      setRequests((prev) => [request, ...prev]);
      notify('success', 'Access request submitted', `${dataset.title} · awaiting review`);
      return true;
    },
    [datasets, notify, requests, role],
  );

  const value = useMemo<DemoStore>(
    () => ({
      user: currentUser,
      role,
      setRole,
      datasets,
      jobs,
      requests,
      qualityReports,
      readinessReports,
      representativenessReports,
      toasts,
      notify,
      dismissToast,
      uploadDataset,
      resolveMapping,
      publishJob,
      decideRequest,
      withdrawRequest,
      requestAccess,
    }),
    [
      role,
      setRole,
      datasets,
      jobs,
      requests,
      qualityReports,
      readinessReports,
      representativenessReports,
      toasts,
      notify,
      dismissToast,
      uploadDataset,
      resolveMapping,
      publishJob,
      decideRequest,
      withdrawRequest,
      requestAccess,
    ],
  );

  return <DemoContext.Provider value={value}>{children}</DemoContext.Provider>;
};

export const useDemo = () => {
  const context = useContext(DemoContext);
  if (!context) throw new Error('useDemo must be used inside DemoProvider');
  return context;
};
