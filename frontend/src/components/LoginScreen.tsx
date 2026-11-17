import { useState, type FormEvent } from 'react';
import { Activity, ArrowRight, Database, LockKeyhole, UserPlus } from 'lucide-react';
import { Alert, Button, Field } from '../components/ui';

interface RegisterPayload {
  email: string;
  password: string;
  fullName: string;
  organisation: string;
  title: string;
}

interface LoginScreenProps {
  apiBase: string;
  onLogin: (email: string, password: string) => Promise<void>;
  onRegister: (input: RegisterPayload) => Promise<void>;
}

export const LoginScreen = ({ apiBase, onLogin, onRegister }: LoginScreenProps) => {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [loginForm, setLoginForm] = useState({ email: '', password: '' });
  const [registerForm, setRegisterForm] = useState({
    fullName: '',
    email: '',
    organisation: '',
    title: '',
    password: '',
    confirm: '',
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submitLogin = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    setBusy(true);
    try {
      const email = loginForm.email.trim();
      const password = loginForm.password;
      await onLogin(email, password);

      if (typeof window !== 'undefined' && 'PasswordCredential' in window && navigator.credentials?.store) {
        try {
          const CredentialConstructor = (window as unknown as { PasswordCredential: new (init: Record<string, unknown>) => unknown }).PasswordCredential;
          const cred = new CredentialConstructor({
            id: email,
            password: password,
          });
          void navigator.credentials.store(cred as Credential);
        } catch {
          // Ignore
        }
      }
    } catch (caught) {
      setError(
        caught instanceof Error && caught.message.toLowerCase().includes('failed to fetch')
          ? `Cannot reach backend API at ${apiBase}. Please ensure the FastAPI server is running (e.g. run "npm run dev" or "npm run dev:backend").`
          : caught instanceof Error
            ? caught.message
            : 'Sign in failed.',
      );
    } finally {
      setBusy(false);
    }
  };

  const submitRegister = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
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
        organisation: registerForm.organisation.trim() || 'Independent',
        title: registerForm.title.trim() || 'Researcher',
      });

      if (typeof window !== 'undefined' && 'PasswordCredential' in window && navigator.credentials?.store) {
        try {
          const CredentialConstructor = (window as unknown as { PasswordCredential: new (init: Record<string, unknown>) => unknown }).PasswordCredential;
          const cred = new CredentialConstructor({
            id: email,
            password: password,
            name: fullName,
          });
          void navigator.credentials.store(cred as Credential);
        } catch {
          // Ignore
        }
      }
    } catch (caught) {
      setError(
        caught instanceof Error && caught.message.toLowerCase().includes('failed to fetch')
          ? `Cannot reach backend API at ${apiBase}. Please ensure the FastAPI server is running (e.g. run "npm run dev" or "npm run dev:backend").`
          : caught instanceof Error
            ? caught.message
            : 'Registration failed.',
      );
    } finally {
      setBusy(false);
    }
  };

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
          <h1>{mode === 'login' ? 'Sign in to the repository' : 'Create a contributor account'}</h1>
          <p>
            {mode === 'login'
              ? 'Use a seeded or registered account. Access tokens are issued by the FastAPI backend.'
              : 'New self-service accounts are created with the Contributor role. An administrator can change roles later.'}
          </p>
        </div>

        {error ? <Alert tone="danger" title="Authentication error">{error}</Alert> : null}

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
          </form>
        ) : (
          <form key="register-form" className="auth-form" onSubmit={submitRegister} autoComplete="off">
            {/* Decoy hidden inputs to prevent browser autofill heuristics from targeting registration fields */}
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
        )}

        <button
          className="auth-switch button-link inline-link"
          onClick={() => {
            setMode((current) => {
              const next = current === 'login' ? 'register' : 'login';
              if (next === 'register') {
                setRegisterForm({
                  fullName: '',
                  email: '',
                  organisation: '',
                  title: '',
                  password: '',
                  confirm: '',
                });
              }
              return next;
            });
            setError('');
          }}
        >
          {mode === 'login' ? 'Need an account? Register as a contributor' : 'Already registered? Sign in'}
          <ArrowRight size={14} />
        </button>
      </div>
    </div>
  );
};
