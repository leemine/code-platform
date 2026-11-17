import { useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '../../components/ui/Button/Button';
import { Dialog } from '../../components/ui/Dialog/Dialog';
import { AccountLoginForm } from '../auth/AccountLoginForm';
import { webClient } from '../../services/webClient';
import { AccountControl } from './AccountControl';
import { localCloudAccountRequest, notifyLocalCloudAccountChange, onLocalCloudAccountChange, type LocalCloudIdentity } from './localCloudAccountClient';
import './LocalCloudAccount.css';

export function LocalCloudAccount({ waitForGateway = false }: { waitForGateway?: boolean }) {
  const { t } = useTranslation();
  const title = useId(), generation = useRef(0), working = useRef(false);
  const [status, setStatus] = useState<LocalCloudIdentity | null>(null);
  const [open, setOpen] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [registering, setRegistering] = useState(false);
  const [notice, setNotice] = useState('');
  const loginCompletion = useRef<((authenticated: boolean) => void) | null>(null);
  function finishLogin(authenticated: boolean) {
    const callback = loginCompletion.current; loginCompletion.current = null; callback?.(authenticated);
  }
  function close() {
    setOpen(false); setPassword(''); setRegistering(false); setNotice('');
    finishLogin(false);
  }
  const [username, setUsername] = useState(''), [password, setPassword] = useState('');
  const errorText = (reason: unknown) => t((reason as { code?: string })?.code === 'UNAUTHORIZED' ? 'localCloudAccount.loginRequired' : 'localCloudAccount.unavailable');

  async function load(epoch: number) {
    const value = await localCloudAccountRequest('status');
    if (epoch === generation.current) {
      setStatus(value); setError('');
      if (value.authenticated && loginCompletion.current) { setOpen(false); finishLogin(true); }
    }
  }
  async function run(action: (epoch: number) => Promise<void>, showFailure = false) {
    if (working.current) return;
    const epoch = generation.current;
    working.current = true; setBusy(true); setError('');
    try { await action(epoch); }
    catch (reason) {
      if (epoch === generation.current) {
        setError(errorText(reason));
        if (showFailure) setOpen(true);
        if ((reason as { code?: string })?.code === 'UNAUTHORIZED') setStatus({ enabled: true, kind: 'local', authenticated: false });
      }
    } finally { if (epoch === generation.current) { working.current = false; setBusy(false); } }
  }
  function logout() {
    void run(async epoch => {
      await localCloudAccountRequest('logout', {});
      if (epoch === generation.current) notifyLocalCloudAccountChange();
    }, true);
  }
  async function register(epoch: number, password: string) {
    try {
      await localCloudAccountRequest('register', { username, password });
      if (epoch === generation.current) {
        setRegistering(false);
        setNotice(t('auth.registered'));
      }
    } catch (reason) {
      if (epoch !== generation.current) return;
      const code = (reason as { code?: string })?.code;
      if (code === 'REGISTRATION_DISABLED') {
        setRegistering(false);
        setNotice(t('localCloudAccount.registrationDisabled'));
        return;
      }
      const messages: Record<string, string> = {
        USERNAME_EXISTS: 'auth.usernameExists',
        INVALID_USERNAME: 'localCloudAccount.invalidRegistrationUsername',
        INVALID_PASSWORD: 'localCloudAccount.invalidRegistrationPassword',
      };
      setError(t((code && messages[code]) || 'localCloudAccount.registrationFailed'));
    }
  }
  useEffect(() => {
    const reload = () => {
      generation.current++; working.current = false; setBusy(false); setPassword('');
      void run(load);
    };
    const requestLogin = (event: Event) => {
      finishLogin(false);
      loginCompletion.current = (event as CustomEvent<(authenticated: boolean) => void>).detail;
      setOpen(true); reload();
    };
    window.addEventListener('jiuwenswarm-cloud-login-request', requestLogin);
    let offGateway: (() => void) | undefined;
    if (waitForGateway && webClient.getState() !== 'ready') {
      offGateway = webClient.onStateChange(state => {
        if (state === 'ready') {
          offGateway?.();
          reload();
        }
      });
    } else {
      reload();
    }
    const off = onLocalCloudAccountChange(reload);
    const focus = () => { if (!working.current) reload(); };
    window.addEventListener('focus', focus);
    return () => { generation.current++; finishLogin(false); window.removeEventListener('jiuwenswarm-cloud-login-request', requestLogin); off(); offGateway?.(); window.removeEventListener('focus', focus); };
  }, [waitForGateway]);
  if (status?.enabled === false || status?.kind === 'cloud' || (!status && !error && !open)) return null;
  return <>
    <AccountControl authenticated={status?.authenticated === true} username={status?.username}
      loginLabel={t('auth.login')} logoutLabel={t('cloudWorkspace.logout')}
      onLogin={() => { setOpen(true); if (!status) void run(load); }} onLogout={logout} actionsDisabled={busy}
      prefix="cloud-workspace-local-account" triggerTestId="cloud-workspace-local-account-trigger" logoutTestId="cloud-workspace-local-account-menu-logout" />
    <Dialog open={open} titleId={title} onCancel={() => { if (!busy) { close(); } }} closeDisabled={busy} className="local-cloud-account-dialog">
      <section data-testid="cloud-workspace-local-account-dialog">
        <h2 id={title} data-testid="cloud-workspace-local-account-title">{t(registering ? 'auth.register' : 'auth.title')}</h2>
        {status?.cloud_origin && <p data-testid="cloud-workspace-local-account-destination">{t('localCloudAccount.destination', { origin: status.cloud_origin })}</p>}
        {status?.authenticated ? <>
          <p data-testid="cloud-workspace-local-account-identity">{status.username} · {t('localCloudAccount.signedIn')}</p>
          <Button disabled={busy} onClick={logout} data-testid="cloud-workspace-local-account-logout">{t('localCloudAccount.logout')}</Button>
        </> : status?.enabled && <AccountLoginForm username={username} password={password} onUsername={setUsername} onPassword={setPassword} busy={busy}
          registering={registering} submitLabel={registering ? t('auth.register') : undefined}
          footer={<Button variant="quiet" disabled={busy} data-testid="cloud-workspace-local-account-registration-toggle"
            onClick={() => { setRegistering(!registering); setPassword(''); setError(''); setNotice(''); }}>
            {t(registering ? 'auth.backToLogin' : 'auth.createAccount')}
          </Button>}
          ids={{ form: 'cloud-workspace-local-account-form', username: 'cloud-workspace-local-account-username', password: 'cloud-workspace-local-account-password', submit: 'cloud-workspace-local-account-login' }} onSubmit={event => { event.preventDefault(); void run(async epoch => {
          const secret = password; setPassword(''); setNotice('');
          if (registering) {
            await register(epoch, secret);
            return;
          }
          await localCloudAccountRequest('login', { username, password: secret });
          if (epoch === generation.current) {
            notifyLocalCloudAccountChange(); setOpen(false); finishLogin(true);
          }
        }); }}>
          {registering && <p data-testid="cloud-workspace-local-account-registration-hint">{t('auth.accountHint')}</p>}
          {notice && <p role="status" data-testid="cloud-workspace-local-account-registration-notice">{notice}</p>}
        </AccountLoginForm>}
        {error && <p role="alert" data-testid="cloud-workspace-local-account-error">{error}</p>}
        <Button variant="quiet" disabled={busy} onClick={() => { close(); }} data-testid="cloud-workspace-local-account-close">{t('codeWorkspace.cancel')}</Button>
      </section>
    </Dialog>
  </>;
}
