import { lazy } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { DemoProvider } from './store/DemoStore';
import { AppLayout } from './layouts/AppLayout';

const Dashboard = lazy(() => import('./pages/Dashboard').then((module) => ({ default: module.Dashboard })));
const UploadDataset = lazy(() => import('./pages/UploadDataset').then((module) => ({ default: module.UploadDataset })));
const MyDatasets = lazy(() => import('./pages/MyDatasets').then((module) => ({ default: module.MyDatasets })));
const DatasetDetail = lazy(() => import('./pages/DatasetDetail').then((module) => ({ default: module.DatasetDetail })));
const EtlProcessing = lazy(() => import('./pages/EtlProcessing').then((module) => ({ default: module.EtlProcessing })));
const DataQuality = lazy(() => import('./pages/DataQuality').then((module) => ({ default: module.DataQuality })));
const AiReadiness = lazy(() => import('./pages/AiReadiness').then((module) => ({ default: module.AiReadiness })));
const Representativeness = lazy(() =>
  import('./pages/Representativeness').then((module) => ({ default: module.Representativeness })),
);
const Repository = lazy(() => import('./pages/Repository').then((module) => ({ default: module.Repository })));
const AccessRequests = lazy(() => import('./pages/AccessRequests').then((module) => ({ default: module.AccessRequests })));
const SettingsPage = lazy(() => import('./pages/Settings').then((module) => ({ default: module.SettingsPage })));
const NotFound = lazy(() => import('./pages/NotFound').then((module) => ({ default: module.NotFound })));

export const App = () => (
  <BrowserRouter>
    <DemoProvider>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="upload" element={<UploadDataset />} />
          <Route path="datasets" element={<MyDatasets />} />
          <Route path="datasets/:datasetId" element={<DatasetDetail />} />
          <Route path="etl" element={<EtlProcessing />} />
          <Route path="quality" element={<DataQuality />} />
          <Route path="readiness" element={<AiReadiness />} />
          <Route path="representativeness" element={<Representativeness />} />
          <Route path="repository" element={<Repository />} />
          <Route path="access-requests" element={<AccessRequests />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </DemoProvider>
  </BrowserRouter>
);
