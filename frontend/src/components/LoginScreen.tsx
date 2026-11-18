import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Activity, ArrowRight, Database, LockKeyhole, Mail, UserPlus } from 'lucide-react';
import { Alert, Button, Field } from '../components/ui';

interface RegisterPayload {
  email: string;
  password: string;
  fullName: string;
  phoneNumber?: string;
  organisation: string;
  title: string;
}

interface LoginScreenProps {
  apiBase: string;
  onLogin: (email: string, password: string) => Promise<void>;
  onRegister: (input: RegisterPayload) => Promise<void>;
  onRequestPasswordReset: (email: string) => Promise<string>;
  onVerifyPasswordReset: (email: string, otp: string, newPassword: string) => Promise<void>;
}

type AuthMode = 'login' | 'register' | 'forgot';

const AUTH_HASHES: Record<Exclude<AuthMode, 'login'>, string> = {
  register: '#register',
  forgot: '#forgot-password',
};

const modeFromLocation = (): AuthMode => {
  if (window.location.hash === AUTH_HASHES.register) return 'register';
  if (window.location.hash === AUTH_HASHES.forgot) return 'forgot';
  return 'login';
};

export const LoginScreen = ({
  apiBase,
  onLogin,
  onRegister,
  onRequestPasswordReset,
  onVerifyPasswordReset,
}: LoginScreenProps) => {
  const [mode, setMode] = useState<AuthMode>(() => (typeof window === 'undefined' ? 'login' : modeFromLocation()));
  const authEntryActive = useRef(
    typeof window !== 'undefined' && Boolean(window.history.state?.meddatahubAuthMode),
  );
  const [loginForm, setLoginForm] = useState({ email: '', password: '' });
  const [registerForm, setRegisterForm] = useState({
    fullName: '',
    email: '',
    phoneNumber: '',
    organisation: '',
    title: '',
    password: '',
    confirm: '',
  });
  const [resetForm, setResetForm] = useState({ email: '', otp: '', newPassword: '', confirm: '' });
  const [resetStep, setResetStep] = useState<'request' | 'verify'>('request');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const syncFromHistory = () => {
      const next = modeFromLocation();
      authEntryActive.current = next !== 'login';
      setMode(next);
      setError('');
      setNotice('');
      if (next !== 'forgot') setResetStep('request');
    };
    window.addEventListener('popstate', syncFromHistory);
    return () => window.removeEventListener('popstate', syncFromHistory);
  }, []);

  const clearAuthHash = () => {
    if (window.location.hash) {
      window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}`);
    }
  };

  const updateHistory = (next: AuthMode) => {
    if (next === 'login') {
      if (authEntryActive.current) {
        authEntryActive.current = false;
        window.history.back();
      } else {
        clearAuthHash();
      }
      return;
    }
    window.history.pushState({ meddatahubAuthMode: next }, '', AUTH_HASHES[next]);
    authEntryActive.current = true;
  };

  const describeError = (caught: unknown, fallback: string) =>
    caught instanceof Error && caught.message.toLowerCase().includes('failed to fetch')
      ? `Cannot reach backend API at ${apiBase}. Please ensure the FastAPI server is running (e.g. run "npm run dev" or "npm run dev:backend").`
      : caught instanceof Error
        ? caught.message
        : fallback;

  const storeCredential = (email: string, password: string, name?: string) => {
    if (typeof window !== 'undefined' && 'PasswordCredential' in window && navigator.credentials?.store) {
      try {
        const CredentialConstructor = (window as unknown as { PasswordCredential: new (init: Record<string, unknown>) => unknown }).PasswordCredential;
        const cred = new CredentialConstructor({ id: email, password, name });
        void navigator.credentials.store(cred as Credential);
      } catch {
        // Ignore
      }
    }
  };

  const submitLogin = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    setNotice('');
    setBusy(true);
    try {
      const email = loginForm.email.trim();
      const password = loginForm.password;
      await onLogin(email, password);
      clearAuthHash();
      storeCredential(email, password);
    } catch (caught) {
      setError(describeError(caught, 'Sign in failed.'));
    } finally {
      setBusy(false);
    }
  };

  const submitRegister = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    setNotice('');
    if (registerForm.password !== registerForm.confirm) {
      setError('Passwords do not match.');
      return;
    }
    if (registerForm.password.length < 10) {
      setError('Use a password of at least 10 characters.');
      return;
    }
    setBusy(true);
    try {
      const email = registerForm.email.trim();
      const password = registerForm.password;
      const fullName = registerForm.fullName.trim();
      await onRegister({
        email,
        password,
        fullName,
        phoneNumber: registerForm.phoneNumber.trim(),
        organisation: registerForm.organisation.trim() || 'Independent',
        title: registerForm.title.trim() || 'Researcher',
      });
      clearAuthHash();
      storeCredential(email, password, fullName);
    } catch (caught) {
      setError(describeError(caught, 'Registration failed.'));
    } finally {
      setBusy(false);
    }
  };

  const submitResetRequest = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    setNotice('');
    setBusy(true);
    try {
      const message = await onRequestPasswordReset(resetForm.email.trim());
      setResetStep('verify');
      setNotice(message);
    } catch (caught) {
      setError(describeError(caught, 'Could not request a reset code.'));
    } finally {
      setBusy(false);
    }
  };

  const submitResetVerify = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    setNotice('');
    if (resetForm.newPassword.length < 10) {
      setError('Use a password of at least 10 characters.');
      return;
    }
    if (resetForm.newPassword !== resetForm.confirm) {
      setError('Passwords do not match.');
      return;
    }
    setBusy(true);
    try {
      const email = resetForm.email.trim();
      await onVerifyPasswordReset(email, resetForm.otp.trim(), resetForm.newPassword);
      storeCredential(email, resetForm.newPassword);
      setLoginForm((prev) => ({ ...prev, email, password: '' }));
      setResetForm({ email, otp: '', newPassword: '', confirm: '' });
      switchMode('login');
      setNotice('Password updated. Sign in with your new password.');
    } catch (caught) {
      setError(describeError(caught, 'Could not reset the password.'));
    } finally {
      setBusy(false);
    }
  };

  const switchMode = (next: AuthMode) => {
    if (next === mode) return;
    updateHistory(next);
    setMode(next);
    setError('');
    setNotice('');
    if (next === 'register') {
      setRegisterForm({
        fullName: '',
        email: '',
        phoneNumber: '',
        organisation: '',
        title: '',
        password: '',
        confirm: '',
      });
    }
    if (next === 'forgot') {
      setResetForm((prev) => ({ ...prev, email: prev.email || loginForm.email.trim() }));
      setResetStep('request');
    }
  };

  const heading =
    mode === 'login'
      ? 'Sign in to the repository'
      : mode === 'register'
        ? 'Create a contributor account'
        : 'Reset your password';
  const description =
    mode === 'login'
      ? 'Use a seeded or registered account. Access tokens are issued by the FastAPI backend.'
      : mode === 'register'
        ? 'New self-service accounts are created with the Contributor role. An administrator can change roles later.'
        : 'Enter your account email to receive a one-time code, then choose a new password.';

  return (
    <div className="auth-shell">
      <div className="auth-panel">
        <div className="auth-brand">
          <div className="brand-mark"><Activity size={22} /></div>
          <div>
            <div className="brand-name">MedDataHub</div>
            <div className="brand-sub">Research Data Platform</div>
          </div>
        </div>

        <div className="auth-heading">
          <span className="auth-icon"><Database size={22} /></span>
          <h1>{heading}</h1>
          <p>{description}</p>
        </div>

        {error ? <Alert tone="danger" title="Authentication error">{error}</Alert> : null}
        {notice ? <Alert tone="info" title="Password reset">{notice}</Alert> : null}

        {mode === 'login' ? (
          <form key="login-form" className="auth-form" onSubmit={submitLogin} autoComplete="on">
            <Field label="Email" htmlFor="login-email">
              <input
                id="login-email"
                name="username"
                className="input"
                type="email"
                autoComplete="username"
                required
                value={loginForm.email}
                onChange={(event) => setLoginForm((prev) => ({ ...prev, email: event.target.value }))}
              />
            </Field>
            <Field label="Password" htmlFor="login-password">
              <input
                id="login-password"
                name="password"
                className="input"
                type="password"
                autoComplete="current-password"
                required
                value={loginForm.password}
                onChange={(event) => setLoginForm((prev) => ({ ...prev, password: event.target.value }))}
              />
            </Field>
            <Button type="submit" disabled={busy} icon={<LockKeyhole size={16} />}>
              {busy ? 'Signing in...' : 'Sign in'}
            </Button>
            <button type="button" className="button-link inline-link" onClick={() => switchMode('forgot')}>
              Forgot your password?
            </button>
          </form>
        ) : mode === 'register' ? (
          <form key="register-form" className="auth-form" onSubmit={submitRegister} autoComplete="off">
            <div style={{ display: 'none', position: 'absolute', opacity: 0, pointerEvents: 'none' }} aria-hidden="true">
              <input type="text" name="fake_username_prevent_autofill" tabIndex={-1} autoComplete="off" />
              <input type="password" name="fake_password_prevent_autofill" tabIndex={-1} autoComplete="off" />
            </div>

            <Field label="Full name" htmlFor="register-name">
              <input
                id="register-name"
                name="signup_fullname"
                className="input"
                autoComplete="off"
                required
                value={registerForm.fullName}
                onChange={(event) => setRegisterForm((prev) => ({ ...prev, fullName: event.target.value }))}
              />
            </Field>
            <Field label="Email" htmlFor="register-email">
              <input
                id="register-email"
                name="signup_email"
                className="input"
                type="email"
                autoComplete="off"
                required
                value={registerForm.email}
                onChange={(event) => setRegisterForm((prev) => ({ ...prev, email: event.target.value }))}
              />
            </Field>
            <Field
              label="Phone number (optional)"
              hint="E.164 format, for example +15551234567."
              htmlFor="register-phone"
            >
              <input
                id="register-phone"
                name="signup_phone"
                className="input"
                type="tel"
                autoComplete="tel"
                value={registerForm.phoneNumber}
                onChange={(event) => setRegisterForm((prev) => ({ ...prev, phoneNumber: event.target.value }))}
              />
            </Field>
            <div className="form-grid">
              <Field label="Organisation" htmlFor="register-org">
                <input
                  id="register-org"
                  name="signup_organisation"
                  className="input"
                  autoComplete="off"
                  value={registerForm.organisation}
                  onChange={(event) => setRegisterForm((prev) => ({ ...prev, organisation: event.target.value }))}
                />
              </Field>
              <Field label="Job title" htmlFor="register-title">
                <input
                  id="register-title"
                  name="signup_title"
                  className="input"
                  autoComplete="off"
                  value={registerForm.title}
                  onChange={(event) => setRegisterForm((prev) => ({ ...prev, title: event.target.value }))}
                />
              </Field>
            </div>
            <div className="form-grid">
              <Field label="Password" hint="At least 10 characters." htmlFor="register-password">
                <input
                  id="register-password"
                  name="signup_password"
                  className="input"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={registerForm.password}
                  onChange={(event) => setRegisterForm((prev) => ({ ...prev, password: event.target.value }))}
                />
              </Field>
              <Field label="Confirm password" htmlFor="register-confirm">
                <input
                  id="register-confirm"
                  name="signup_confirm_password"
                  className="input"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={registerForm.confirm}
                  onChange={(event) => setRegisterForm((prev) => ({ ...prev, confirm: event.target.value }))}
                />
              </Field>
            </div>
            <Button type="submit" disabled={busy} icon={<UserPlus size={16} />}>
              {busy ? 'Creating account...' : 'Create account'}
            </Button>
          </form>
        ) : resetStep === 'request' ? (
          <form key="reset-request-form" className="auth-form" onSubmit={submitResetRequest} autoComplete="on">
            <Field label="Account email" htmlFor="reset-email">
              <input
                id="reset-email"
                name="username"
                className="input"
                type="email"
                autoComplete="username"
                required
                value={resetForm.email}
                onChange={(event) => setResetForm((prev) => ({ ...prev, email: event.target.value }))}
              />
            </Field>
            <Button type="submit" disabled={busy} icon={<Mail size={16} />}>
              {busy ? 'Sending code...' : 'Send reset code'}
            </Button>
          </form>
        ) : (
          <form key="reset-verify-form" className="auth-form" onSubmit={submitResetVerify} autoComplete="off">
            <Field label="Account email" htmlFor="reset-verify-email">
              <input id="reset-verify-email" className="input" type="email" readOnly value={resetForm.email} />
            </Field>
            <Field label="Six-digit code" hint="Check your inbox for the one-time code." htmlFor="reset-otp">
              <input
                id="reset-otp"
                className="input"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                pattern="\d{6}"
                required
                value={resetForm.otp}
                onChange={(event) => setResetForm((prev) => ({ ...prev, otp: event.target.value }))}
              />
            </Field>
            <Field label="New password" hint="At least 10 characters." htmlFor="reset-password">
              <input
                id="reset-password"
                className="input"
                type="password"
                autoComplete="new-password"
                required
                value={resetForm.newPassword}
                onChange={(event) => setResetForm((prev) => ({ ...prev, newPassword: event.target.value }))}
              />
            </Field>
            <Field label="Confirm new password" htmlFor="reset-confirm">
              <input
                id="reset-confirm"
                className="input"
                type="password"
                autoComplete="new-password"
                required
                value={resetForm.confirm}
                onChange={(event) => setResetForm((prev) => ({ ...prev, confirm: event.target.value }))}
              />
            </Field>
            <Button type="submit" disabled={busy} icon={<LockKeyhole size={16} />}>
              {busy ? 'Resetting password...' : 'Reset password'}
            </Button>
            <button
              type="button"
              className="button-link inline-link"
              onClick={() => {
                setResetStep('request');
                setError('');
                setNotice('');
              }}
            >
              Use a different email
            </button>
          </form>
        )}

        {mode === 'forgot' ? (
          <button className="auth-switch button-link inline-link" onClick={() => switchMode('login')}>
            Back to sign in
            <ArrowRight size={14} />
          </button>
        ) : (
          <button
            className="auth-switch button-link inline-link"
            onClick={() => switchMode(mode === 'login' ? 'register' : 'login')}
          >
            {mode === 'login' ? 'Need an account? Register as a contributor' : 'Already registered? Sign in'}
            <ArrowRight size={14} />
          </button>
        )}
      </div>
    </div>
  );
};
