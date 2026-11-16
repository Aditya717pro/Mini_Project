import { useState, type FormEvent } from 'react';
import {
  Bell,
  CheckCircle2,
  Database,
  Download,
  KeyRound,
  Lock,
  Save,
  Server,
  ShieldCheck,
  UserCog,
} from 'lucide-react';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  DemoBadge,
  DemoNotice,
  Field,
  PageHeader,
  SectionTitle,
} from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { roleDescriptions } from '../data/mockData';
import { formatDateTime } from '../lib/format';
import type { Role } from '../types';

const ROLES: Role[] = ['Contributor', 'Researcher', 'Administrator'];

export const SettingsPage = () => {
  const { user, role, setRole, notify, datasets, requests, jobs } = useDemo();

  const [profile, setProfile] = useState({
    name: user.name,
    email: user.email,
    organisation: user.organisation,
    title: user.title,
  });
  const [profileSaved, setProfileSaved] = useState(false);

  const [password, setPassword] = useState({ current: '', next: '', confirm: '' });
  const [passwordErrors, setPasswordErrors] = useState<Record<string, string>>({});
  const [twoFactor, setTwoFactor] = useState(false);

  const [notifications, setNotifications] = useState({
    accessRequests: true,
    pipelineFailures: true,
    qualityReports: true,
    weeklyDigest: false,
    productUpdates: false,
  });

  const apiBase = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

  const saveProfile = (event: FormEvent) => {
    event.preventDefault();
    if (!profile.name.trim() || !profile.email.includes('@')) {
      notify('error', 'Profile not saved', 'Provide a name and a valid email address.');
      return;
    }
    setProfileSaved(true);
    notify('success', 'Profile updated locally', 'The demo does not persist profile changes to a backend.');
    window.setTimeout(() => setProfileSaved(false), 4000);
  };

  const submitPassword = (event: FormEvent) => {
    event.preventDefault();
    const next: Record<string, string> = {};
    if (!password.current) next.current = 'Enter your current password.';
    if (password.next.length < 12) next.next = 'Use at least 12 characters.';
    if (password.next !== password.confirm) next.confirm = 'Passwords do not match.';
    setPasswordErrors(next);
    if (Object.keys(next).length > 0) return;
    setPassword({ current: '', next: '', confirm: '' });
    notify(
      'info',
      'Password change requires the backend',
      'Client-side validation passed, but no credentials are stored or transmitted in this demo.',
    );
  };

  const exportMetadata = () => {
    const payload = {
      exportedAt: new Date().toISOString(),
      note: 'Synthetic demo metadata only. No record-level data is included.',
      datasets: datasets.map((dataset) => ({
        id: dataset.id,
        title: dataset.title,
        domain: dataset.domain,
        access: dataset.access,
        status: dataset.status,
        records: dataset.records,
        qualityScore: dataset.qualityScore,
        readinessScore: dataset.readinessScore,
      })),
      accessRequests: requests,
      etlJobs: jobs.map((job) => ({ id: job.id, datasetId: job.datasetId, status: job.status, progress: job.progress })),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'meddatahub-demo-metadata.json';
    anchor.click();
    URL.revokeObjectURL(url);
    notify('success', 'Metadata exported', 'Synthetic metadata JSON downloaded to your device.');
  };

  const toggleNotification = (key: keyof typeof notifications) => {
    setNotifications((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <>
      <PageHeader
        eyebrow="Account"
        title="Settings"
        description="Manage your demo profile, review role-based access, security preferences and API connection status."
      />

      <DemoNotice text="Settings are local to this browser session. Authentication, password storage, session management and audit logging are not implemented in the frontend demo." />

      <div className="settings-layout">
        <div className="stack">
          <Card>
            <CardHeader title="Profile" subtitle="Displayed on datasets and access requests" action={<UserCog size={18} className="muted-icon" />} />
            <form onSubmit={saveProfile} className="form-grid">
              <Field label="Full name" htmlFor="profile-name">
                <input
                  id="profile-name"
                  className="input"
                  value={profile.name}
                  onChange={(event) => setProfile((prev) => ({ ...prev, name: event.target.value }))}
                />
              </Field>
              <Field label="Email" htmlFor="profile-email">
                <input
                  id="profile-email"
                  className="input"
                  type="email"
                  value={profile.email}
                  onChange={(event) => setProfile((prev) => ({ ...prev, email: event.target.value }))}
                />
              </Field>
              <Field label="Organisation" htmlFor="profile-org">
                <input
                  id="profile-org"
                  className="input"
                  value={profile.organisation}
                  onChange={(event) => setProfile((prev) => ({ ...prev, organisation: event.target.value }))}
                />
              </Field>
              <Field label="Job title" htmlFor="profile-title">
                <input
                  id="profile-title"
                  className="input"
                  value={profile.title}
                  onChange={(event) => setProfile((prev) => ({ ...prev, title: event.target.value }))}
                />
              </Field>
              <div className="span-2 form-actions">
                <Button type="submit" icon={<Save size={16} />}>Save profile</Button>
                {profileSaved ? (
                  <span className="saved-note"><CheckCircle2 size={15} /> Saved locally</span>
                ) : null}
              </div>
            </form>
          </Card>

          <Card>
            <CardHeader title="Demo role" subtitle="Inspect role-aware UI states" action={<Badge tone="purple">{role}</Badge>} />
            <div className="role-grid">
              {ROLES.map((option) => (
                <button
                  key={option}
                  className={`role-option ${role === option ? 'selected' : ''}`}
                  onClick={() => setRole(option)}
                  aria-pressed={role === option}
                >
                  <div className="role-head">
                    <strong>{option}</strong>
                    {role === option ? <Badge tone="success">Active</Badge> : null}
                  </div>
                  <p>{roleDescriptions[option]}</p>
                </button>
              ))}
            </div>
            <Alert tone="warning" title="Role switching is not authentication">
              This control only changes which demo controls are shown. It does not grant real permissions, and it must
              not be carried into production. Backend RBAC will use signed tokens and server-side authorisation.
            </Alert>
          </Card>

          <Card>
            <CardHeader title="Security" subtitle="Password and multi-factor preferences" action={<ShieldCheck size={18} className="muted-icon" />} />
            <form onSubmit={submitPassword} className="form-grid">
              <Field label="Current password" error={passwordErrors.current} htmlFor="current-password">
                <input
                  id="current-password"
                  className="input"
                  type="password"
                  autoComplete="current-password"
                  value={password.current}
                  onChange={(event) => setPassword((prev) => ({ ...prev, current: event.target.value }))}
                />
              </Field>
              <div className="span-2" />
              <Field label="New password" error={passwordErrors.next} hint="Minimum 12 characters. Validated locally only." htmlFor="new-password">
                <input
                  id="new-password"
                  className="input"
                  type="password"
                  autoComplete="new-password"
                  value={password.next}
                  onChange={(event) => setPassword((prev) => ({ ...prev, next: event.target.value }))}
                />
              </Field>
              <Field label="Confirm new password" error={passwordErrors.confirm} htmlFor="confirm-password">
                <input
                  id="confirm-password"
                  className="input"
                  type="password"
                  autoComplete="new-password"
                  value={password.confirm}
                  onChange={(event) => setPassword((prev) => ({ ...prev, confirm: event.target.value }))}
                />
              </Field>
              <div className="span-2 form-actions">
                <Button type="submit" variant="secondary" icon={<Lock size={16} />}>Update password</Button>
              </div>
            </form>

            <SectionTitle>Multi-factor authentication</SectionTitle>
            <label className="toggle-row">
              <div>
                <strong>Require an authenticator code</strong>
                <span>Demo toggle only. TOTP enrolment must be implemented and verified server-side.</span>
              </div>
              <input
                type="checkbox"
                className="toggle-input"
                checked={twoFactor}
                onChange={(event) => setTwoFactor(event.target.checked)}
              />
            </label>

            <SectionTitle>Active session</SectionTitle>
            <div className="session-row">
              <KeyRound size={16} />
              <div>
                <strong>This browser</strong>
                <span>Windows · demo session · started {formatDateTime(new Date().toISOString())}</span>
              </div>
              <DemoBadge label="Not authenticated" />
            </div>
          </Card>
        </div>

        <div className="stack">
          <Card>
            <CardHeader title="Notifications" subtitle="Applies to the current demo session" action={<Bell size={18} className="muted-icon" />} />
            <div className="toggle-list">
              {([
                ['accessRequests', 'Access request decisions', 'Notify me when an access request is approved or rejected.'],
                ['pipelineFailures', 'ETL failures', 'Alert me when an extract, transform or load stage fails.'],
                ['qualityReports', 'Quality report updates', 'Notify me when a new quality or readiness report is generated.'],
                ['weeklyDigest', 'Weekly repository digest', 'Summary of new datasets and governance activity.'],
                ['productUpdates', 'Platform updates', 'Occasional product and documentation updates.'],
              ] as const).map(([key, title, description]) => (
                <label key={key} className="toggle-row">
                  <div>
                    <strong>{title}</strong>
                    <span>{description}</span>
                  </div>
                  <input
                    type="checkbox"
                    className="toggle-input"
                    checked={notifications[key]}
                    onChange={() => toggleNotification(key)}
                  />
                </label>
              ))}
            </div>
            <p className="field-hint">Notification delivery is not implemented. Preferences reset on page reload.</p>
          </Card>

          <Card>
            <CardHeader title="API connection" subtitle="Frontend/backend integration status" action={<Server size={18} className="muted-icon" />} />
            <div className="api-status">
              <span className="status-dot offline" />
              <div>
                <strong>Demo mode active</strong>
                <span>No FastAPI backend is connected in this phase.</span>
              </div>
            </div>
            <div className="info-grid single">
              <div className="info-row">
                <span className="info-label">API base URL</span>
                <span className="info-value"><code className="code small">{apiBase}</code></span>
              </div>
              <div className="info-row">
                <span className="info-label">Environment</span>
                <span className="info-value"><code className="code small">VITE_DEMO_MODE</code></span>
              </div>
              <div className="info-row">
                <span className="info-label">Data source</span>
                <span className="info-value">Local mock + browser extraction</span>
              </div>
              <div className="info-row">
                <span className="info-label">Persistence</span>
                <span className="info-value">None (in-memory)</span>
              </div>
            </div>
            <Alert tone="info">
              PHASE 13 will replace mock reads with typed API calls and add loading, empty, success and error handling
              per endpoint. Until then, no request is sent to {apiBase}.
            </Alert>
          </Card>

          <Card>
            <CardHeader title="Data & privacy" subtitle="Synthetic data only" action={<Database size={18} className="muted-icon" />} />
            <ul className="bullet-list">
              <li>All datasets shown are synthetic and contain no real patient information.</li>
              <li>Uploaded files are parsed in-browser and are not transmitted in this demo.</li>
              <li>Record-level data is never included in repository metadata.</li>
              <li>No regulatory compliance or clinical safety is claimed.</li>
            </ul>
            <div className="form-actions">
              <Button variant="secondary" icon={<Download size={16} />} onClick={exportMetadata}>
                Export demo metadata
              </Button>
              <Button
                variant="ghost"
                onClick={() => {
                  window.location.reload();
                }}
              >
                Reset demo session
              </Button>
            </div>
          </Card>
        </div>
      </div>
    </>
  );
};
