import { useState, type FormEvent } from 'react';
import {
  Bell,
  CheckCircle2,
  Database,
  Download,
  KeyRound,
  Lock,
  LogOut,
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
  DemoNotice,
  Field,
  PageHeader,
  SectionTitle,
} from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { roleDescriptions } from '../data/mockData';

export const SettingsPage = () => {
  const { user, role, notify, datasets, requests, jobs, logout, updateProfile, changePassword } = useDemo();

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

  const saveProfile = async (event: FormEvent) => {
    event.preventDefault();
    if (!profile.name.trim() || !profile.email.includes('@')) {
      notify('error', 'Profile not saved', 'Provide a name and a valid email address.');
      return;
    }
    try {
      await updateProfile({
        fullName: profile.name.trim(),
        organisation: profile.organisation.trim(),
        title: profile.title.trim(),
      });
      setProfileSaved(true);
      window.setTimeout(() => setProfileSaved(false), 4000);
    } catch (error) {
      notify('error', 'Profile not saved', error instanceof Error ? error.message : 'Unexpected API error');
    }
  };

  const submitPassword = async (event: FormEvent) => {
    event.preventDefault();
    const next: Record<string, string> = {};
    if (!password.current) next.current = 'Enter your current password.';
    if (password.next.length < 10) next.next = 'Use at least 10 characters.';
    if (password.next !== password.confirm) next.confirm = 'Passwords do not match.';
    setPasswordErrors(next);
    if (Object.keys(next).length > 0) return;
    const changed = await changePassword(password.current, password.next);
    if (changed) setPassword({ current: '', next: '', confirm: '' });
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
        description="Manage your profile, review authenticated role permissions, update security settings and inspect the API connection."
      />

      <DemoNotice text="Profile and password changes are sent to the FastAPI backend and recorded in the audit log. Notification preferences remain local to this browser." />

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
              <Field label="Email" hint="Managed by an administrator; contact support to change it." htmlFor="profile-email">
                <input id="profile-email" className="input" type="email" readOnly value={profile.email} />
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
                  <span className="saved-note"><CheckCircle2 size={15} /> Saved to backend</span>
                ) : null}
              </div>
            </form>
          </Card>

          <Card>
            <CardHeader title="Authenticated role" subtitle="Assigned by the backend" action={<Badge tone="purple">{role}</Badge>} />
            <div className="role-grid single">
              <div className="role-option selected">
                <div className="role-head">
                  <strong>{role}</strong>
                  <Badge tone="success">Active session</Badge>
                </div>
                <p>{roleDescriptions[role]}</p>
              </div>
            </div>
            <Alert tone="info" title="Role changes require an administrator">
              Permissions are enforced server-side from signed JWT claims and the current database role. Signing in with
              a different seeded account is the only way to exercise another role.
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
              <Field label="New password" error={passwordErrors.next} hint="Minimum 10 characters. Stored as a PBKDF2 hash." htmlFor="new-password">
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
                <span>Not implemented. TOTP enrolment must be designed and verified server-side before production use.</span>
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
                <strong>{user.email}</strong>
                <span>Authenticated with a bearer token. Sign out to clear the token from this browser.</span>
              </div>
              <Badge tone="success">Authenticated</Badge>
            </div>
            <div className="form-actions">
              <Button variant="ghost" icon={<LogOut size={16} />} onClick={logout}>Sign out</Button>
            </div>
          </Card>
        </div>

        <div className="stack">
          <Card>
            <CardHeader title="Notifications" subtitle="Stored in this browser only" action={<Bell size={18} className="muted-icon" />} />
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
              <span className="status-dot" />
              <div>
                <strong>Backend connected</strong>
                <span>All data reads and mutations use the FastAPI API.</span>
              </div>
            </div>
            <div className="info-grid single">
              <div className="info-row">
                <span className="info-label">API base URL</span>
                <span className="info-value"><code className="code small">{apiBase}</code></span>
              </div>
              <div className="info-row">
                <span className="info-label">API prefix</span>
                <span className="info-value"><code className="code small">/api/v1</code></span>
              </div>
              <div className="info-row">
                <span className="info-label">Data source</span>
                <span className="info-value">SQLAlchemy-backed dataset repository</span>
              </div>
              <div className="info-row">
                <span className="info-label">Persistence</span>
                <span className="info-value">MySQL in production; SQLite for local tests</span>
              </div>
            </div>
            <Alert tone="info">
              The API connection status reflects the latest authenticated requests. A 401 response clears the local
              token and returns to the sign-in screen.
            </Alert>
          </Card>

          <Card>
            <CardHeader title="Data & privacy" subtitle="Synthetic data only" action={<Database size={18} className="muted-icon" />} />
            <ul className="bullet-list">
              <li>Seed datasets are synthetic and contain no real patient information.</li>
              <li>Uploaded files are validated in-browser, then transmitted to the backend and stored with a SHA-256 checksum.</li>
              <li>Record-level data is served only through authorised downloads and is never embedded in API metadata.</li>
              <li>No regulatory compliance or clinical safety is claimed.</li>
            </ul>
            <div className="form-actions">
              <Button variant="secondary" icon={<Download size={16} />} onClick={exportMetadata}>
                Export repository metadata
              </Button>
            </div>
          </Card>
        </div>
      </div>
    </>
  );
};
