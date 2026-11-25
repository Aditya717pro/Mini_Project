import { lazy } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { DemoProvider } from './store/DemoStore';
import { AppLayout } from './layouts/AppLayout';

const Dashboard = lazy(() => import('./pages/Dashboard').then((module) => ({ default: module.Dashboard })));
const UploadDataset = lazy(() => import('./pages/UploadDataset').then((module) => ({ default: module.UploadDataset })));
const DatasetDetail = lazy(() => import('./pages/DatasetDetail').then((module) => ({ default: module.DatasetDetail })));
const DatasetVersionHistory = lazy(() =>
  import('./pages/DatasetVersionHistory').then((module) => ({ default: module.DatasetVersionHistory })),
);
const DatasetVersionDetail = lazy(() =>
  import('./pages/DatasetVersionDetail').then((module) => ({ default: module.DatasetVersionDetail })),
);
const EtlProcessing = lazy(() => import('./pages/EtlProcessing').then((module) => ({ default: module.EtlProcessing })));
const DataQuality = lazy(() => import('./pages/DataQuality').then((module) => ({ default: module.DataQuality })));
const AiReadiness = lazy(() => import('./pages/AiReadiness').then((module) => ({ default: module.AiReadiness })));
const Representativeness = lazy(() =>
  import('./pages/Representativeness').then((module) => ({ default: module.Representativeness })),
);
const Repository = lazy(() => import('./pages/Repository').then((module) => ({ default: module.Repository })));
const AddGeneratedDataset = lazy(() =>
  import('./pages/AddGeneratedDataset').then((module) => ({ default: module.AddGeneratedDataset })),
);
const AccessRequests = lazy(() => import('./pages/AccessRequests').then((module) => ({ default: module.AccessRequests })));
const SettingsPage = lazy(() => import('./pages/Settings').then((module) => ({ default: module.SettingsPage })));
const Profile = lazy(() => import('./pages/Profile').then((module) => ({ default: module.Profile })));
const ResearchReports = lazy(() =>
  import('./pages/ResearchReports').then((module) => ({ default: module.ResearchReports })),
);
const ResearchReportDetail = lazy(() =>
  import('./pages/ResearchReportDetail').then((module) => ({ default: module.ResearchReportDetail })),
);
const SynthMed = lazy(() => import('./pages/SynthMed').then((module) => ({ default: module.SynthMed })));
const SynthMedUpload = lazy(() =>
  import('./pages/SynthMedUpload').then((module) => ({ default: module.SynthMedUpload })),
);
const SynthMedGenerate = lazy(() =>
  import('./pages/SynthMedGenerate').then((module) => ({ default: module.SynthMedGenerate })),
);
const SynthMedGenerated = lazy(() =>
  import('./pages/SynthMedGenerated').then((module) => ({ default: module.SynthMedGenerated })),
);
const SynthMedGeneratedDetail = lazy(() =>
  import('./pages/SynthMedGeneratedDetail').then((module) => ({ default: module.SynthMedGeneratedDetail })),
);
const SynthMedEvaluation = lazy(() =>
  import('./pages/SynthMedEvaluation').then((module) => ({ default: module.SynthMedEvaluation })),
);
const SynthMedComparison = lazy(() =>
  import('./pages/SynthMedComparison').then((module) => ({ default: module.SynthMedComparison })),
);
const SynthMedVersionHistory = lazy(() =>
  import('./pages/SynthMedVersionHistory').then((module) => ({ default: module.SynthMedVersionHistory })),
);
const SynthMedLineage = lazy(() =>
  import('./pages/SynthMedLineage').then((module) => ({ default: module.SynthMedLineage })),
);
const SynthMedExperiments = lazy(() =>
  import('./pages/SynthMedExperiments').then((module) => ({ default: module.SynthMedExperiments })),
);
const SynthMedExperimentDetail = lazy(() =>
  import('./pages/SynthMedExperimentDetail').then((module) => ({ default: module.SynthMedExperimentDetail })),
);
const NotFound = lazy(() => import('./pages/NotFound').then((module) => ({ default: module.NotFound })));

export const App = () => (
  <BrowserRouter>
    <DemoProvider>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="upload" element={<UploadDataset />} />
          <Route path="datasets/:datasetId/versions/:versionId" element={<DatasetVersionDetail />} />
          <Route path="datasets/:datasetId/versions" element={<DatasetVersionHistory />} />
          <Route path="datasets/:datasetId" element={<DatasetDetail />} />
          <Route path="etl" element={<EtlProcessing />} />
          <Route path="quality" element={<DataQuality />} />
          <Route path="readiness" element={<AiReadiness />} />
          <Route path="representativeness" element={<Representativeness />} />
          <Route path="repository/add-generated/:generatedId" element={<AddGeneratedDataset />} />
          <Route path="repository" element={<Repository />} />
          <Route path="reports/:reportId" element={<ResearchReportDetail />} />
          <Route path="reports" element={<ResearchReports />} />
          <Route path="access-requests" element={<AccessRequests />} />
          <Route path="profile" element={<Profile />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="synthmed" element={<SynthMed />} />
          <Route path="synthmed/upload" element={<SynthMedUpload />} />
          <Route path="synthmed/generate" element={<SynthMedGenerate />} />
          <Route path="synthmed/generated/:generatedId" element={<SynthMedGeneratedDetail />} />
          <Route path="synthmed/generated" element={<SynthMedGenerated />} />
          <Route path="synthmed/evaluation" element={<SynthMedEvaluation />} />
          <Route path="synthmed/downloads" element={<Navigate to="/synthmed/generated" replace />} />
          <Route path="synthmed/comparison" element={<SynthMedComparison />} />
          <Route path="synthmed/comparison/:comparisonId" element={<SynthMedComparison />} />
          <Route path="synthmed/datasets/:datasetId/versions/:versionId" element={<DatasetVersionDetail />} />
          <Route path="synthmed/datasets/:datasetId/versions" element={<SynthMedVersionHistory />} />
          <Route path="synthmed/datasets/:datasetId/lineage" element={<SynthMedLineage />} />
          <Route path="synthmed/experiments/:experimentId" element={<SynthMedExperimentDetail />} />
          <Route path="synthmed/experiments" element={<SynthMedExperiments />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </DemoProvider>
  </BrowserRouter>
);
