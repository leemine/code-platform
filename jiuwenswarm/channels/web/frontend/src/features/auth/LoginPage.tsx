import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '../../components/ui/Button/Button';
import { AccountLoginForm } from './AccountLoginForm';
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
      <AccountLoginForm username={username} password={password} onUsername={setUsername} onPassword={setPassword}
        onSubmit={submit} busy={submitting} registering={registering}
        submitLabel={t(submitting ? 'auth.loggingIn' : registering ? 'auth.register' : 'auth.login')}
        footer={registrationEnabled && <Button variant="quiet" disabled={submitting} data-testid="auth-registration-toggle"
          onClick={() => { setRegistering(!registering); setError(''); setNotice(''); }}>
          {t(registering ? 'auth.backToLogin' : 'auth.createAccount')}
        </Button>}
        ids={{ form: 'auth-login-form', username: 'auth-login-username-input', password: 'auth-login-password-input', submit: 'auth-login-submit-button' }}>
        {error && <p role="alert" className="text-warn" data-testid="auth-login-error">{error}</p>}
        {notice && <p role="status" data-testid="auth-registration-notice">{notice}</p>}

      </AccountLoginForm>
      <p className="text-text-muted">{t('auth.accountHint')}</p>
    </section>
  </main>;
}
