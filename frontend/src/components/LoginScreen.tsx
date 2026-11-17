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
      await onLogin(loginForm.email.trim(), loginForm.password);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Sign in failed.');
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
      await onRegister({
        email: registerForm.email.trim(),
        password: registerForm.password,
        fullName: registerForm.fullName.trim(),
        organisation: registerForm.organisation.trim() || 'Independent',
        title: registerForm.title.trim() || 'Researcher',
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Registration failed.');
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
          <form className="auth-form" onSubmit={submitLogin}>
            <Field label="Email" htmlFor="login-email">
              <input
                id="login-email"
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
          <form className="auth-form" onSubmit={submitRegister}>
            <Field label="Full name" htmlFor="register-name">
              <input
                id="register-name"
                className="input"
                required
                value={registerForm.fullName}
                onChange={(event) => setRegisterForm((prev) => ({ ...prev, fullName: event.target.value }))}
              />
            </Field>
            <Field label="Email" htmlFor="register-email">
              <input
                id="register-email"
                className="input"
                type="email"
                autoComplete="username"
                required
                value={registerForm.email}
                onChange={(event) => setRegisterForm((prev) => ({ ...prev, email: event.target.value }))}
              />
            </Field>
            <div className="form-grid">
              <Field label="Organisation" htmlFor="register-org">
                <input
                  id="register-org"
                  className="input"
                  value={registerForm.organisation}
                  onChange={(event) => setRegisterForm((prev) => ({ ...prev, organisation: event.target.value }))}
                />
              </Field>
              <Field label="Job title" htmlFor="register-title">
                <input
                  id="register-title"
                  className="input"
                  value={registerForm.title}
                  onChange={(event) => setRegisterForm((prev) => ({ ...prev, title: event.target.value }))}
                />
              </Field>
            </div>
            <div className="form-grid">
              <Field label="Password" hint="At least 10 characters." htmlFor="register-password">
                <input
                  id="register-password"
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
            setMode((current) => (current === 'login' ? 'register' : 'login'));
            setError('');
          }}
        >
          {mode === 'login' ? 'Need an account? Register as a contributor' : 'Already registered? Sign in'}
          <ArrowRight size={14} />
        </button>

        <p className="auth-footnote">
          API: <code>{apiBase}</code>. Synthetic data only. Do not upload identifiable patient records.
        </p>
      </div>
    </div>
  );
};
