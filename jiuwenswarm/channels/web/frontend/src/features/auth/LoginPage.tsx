import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '../../components/ui/Button/Button';
import { Input } from '../../components/ui/Input/Input';
import { clearAccountCaches, notifyOrganizationCredentialChange } from '../../services/organizationCredentialEvents';
import { cloudRequest, CloudRequestError } from '../cloudWorkspace/client';
import '../cloudWorkspace/cloudWorkspace.css';

/** Extracted from codeswarm's builtin account login. The server owns the cookie. */
export function LoginPage({ registrationEnabled }: { registrationEnabled: boolean }) {
  const { t } = useTranslation();
  const [registering, setRegistering] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError('');
    setNotice('');
    try {
      await cloudRequest(registering ? 'register' : 'login', { username, password });
      if (registering) {
        setRegistering(false);
        setPassword('');
        setNotice(t('auth.registered'));
      } else {
        clearAccountCaches();
        notifyOrganizationCredentialChange();
        window.location.replace(window.location.origin + '/');
      }
    } catch (failure) {
      const status = failure instanceof CloudRequestError ? failure.status : 0;
      setError(t(status === 409 ? 'auth.usernameExists' : status === 401 ? 'auth.invalidCredentials' : status === 503 ? 'auth.accountServiceUnavailable' : 'auth.loginFailed'));
    } finally {
      setSubmitting(false);
    }
  }
  return <main className="cloud-workspace-page" data-testid="auth-login-page">
    <section className="cloud-workspace-card">
      <h1 data-testid="auth-login-title">{t(registering ? 'auth.register' : 'auth.title')}</h1>
      <p>{t('auth.accountSubtitle')}</p>
      <form onSubmit={submit} data-testid="auth-login-form">
        <label htmlFor="cloud-username">{t('auth.username')}</label>
        <Input id="cloud-username" data-testid="auth-login-username-input" autoComplete="username" required
          value={username} onChange={setUsername} changeOnBlur={false} disabled={submitting} />
        <label htmlFor="cloud-password">{t('auth.password')}</label>
        <Input id="cloud-password" data-testid="auth-login-password-input" type="password" required
          autoComplete={registering ? 'new-password' : 'current-password'} value={password}
          onChange={setPassword} changeOnBlur={false} disabled={submitting} />
        {error && <p role="alert" className="text-warn" data-testid="auth-login-error">{error}</p>}
        {notice && <p role="status" data-testid="auth-registration-notice">{notice}</p>}
        <Button type="submit" variant="primary" loading={submitting} data-testid="auth-login-submit-button">
          {t(submitting ? 'auth.loggingIn' : registering ? 'auth.register' : 'auth.login')}
        </Button>
        {registrationEnabled && <Button variant="quiet" disabled={submitting} data-testid="auth-registration-toggle"
          onClick={() => { setRegistering(!registering); setError(''); setNotice(''); }}>
          {t(registering ? 'auth.backToLogin' : 'auth.createAccount')}
        </Button>}
      </form>
      <p className="text-text-muted">{t('auth.accountHint')}</p>
    </section>
  </main>;
}
