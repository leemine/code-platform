import { useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '../../components/ui/Button/Button';
import { Dialog } from '../../components/ui/Dialog/Dialog';
import { AccountLoginForm } from '../auth/AccountLoginForm';
import { AccountControl } from './AccountControl';
import { localCloudAccountRequest, notifyLocalCloudAccountChange, onLocalCloudAccountChange, type LocalCloudIdentity } from './localCloudAccountClient';
import './LocalCloudAccount.css';

export function LocalCloudAccount() {
  const { t } = useTranslation();
  const title = useId(), generation = useRef(0), working = useRef(false);
  const [status, setStatus] = useState<LocalCloudIdentity | null>(null);
  const [open, setOpen] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const loginCompletion = useRef<((authenticated: boolean) => void) | null>(null);
  function finishLogin(authenticated: boolean) {
    const callback = loginCompletion.current; loginCompletion.current = null; callback?.(authenticated);
  }
  function close() { setOpen(false); setPassword(''); finishLogin(false); }
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
    reload(); const off = onLocalCloudAccountChange(reload);
    window.addEventListener('focus', reload);
    return () => { generation.current++; finishLogin(false); window.removeEventListener('jiuwenswarm-cloud-login-request', requestLogin); off(); window.removeEventListener('focus', reload); };
  }, []);
  if (status?.enabled === false || status?.kind === 'cloud' || (!status && !error)) return null;
  return <>
    <AccountControl authenticated={status?.authenticated === true} username={status?.username}
      loginLabel={t('auth.login')} logoutLabel={t('cloudWorkspace.logout')}
      onLogin={() => setOpen(true)} onLogout={logout} actionsDisabled={busy}
      prefix="cloud-workspace-local-account" triggerTestId="cloud-workspace-local-account-trigger" logoutTestId="cloud-workspace-local-account-menu-logout" />
    <Dialog open={open} titleId={title} onCancel={() => { if (!busy) { close(); } }} closeDisabled={busy} className="local-cloud-account-dialog">
      <section data-testid="cloud-workspace-local-account-dialog">
        <h2 id={title} data-testid="cloud-workspace-local-account-title">{t('auth.title')}</h2>
        {status?.cloud_origin && <p data-testid="cloud-workspace-local-account-destination">{t('localCloudAccount.destination', { origin: status.cloud_origin })}</p>}
        {status?.authenticated ? <>
          <p data-testid="cloud-workspace-local-account-identity">{status.username} · {t('localCloudAccount.signedIn')}</p>
          <Button disabled={busy} onClick={logout} data-testid="cloud-workspace-local-account-logout">{t('localCloudAccount.logout')}</Button>
        </> : status?.enabled && <AccountLoginForm username={username} password={password} onUsername={setUsername} onPassword={setPassword} busy={busy}
          ids={{ form: 'cloud-workspace-local-account-form', username: 'cloud-workspace-local-account-username', password: 'cloud-workspace-local-account-password', submit: 'cloud-workspace-local-account-login' }} onSubmit={event => { event.preventDefault(); void run(async epoch => {
          const secret = password; setPassword('');
          await localCloudAccountRequest('login', { username, password: secret });
          if (epoch === generation.current) {
            notifyLocalCloudAccountChange(); setOpen(false); finishLogin(true);
          }
        }); }} />}
        {error && <><p role="alert" data-testid="cloud-workspace-local-account-error">{error}</p><Button disabled={busy} onClick={() => void run(load)} data-testid="cloud-workspace-local-account-retry">{t('localCloudAccount.retry')}</Button></>}
        <Button variant="quiet" disabled={busy} onClick={() => { close(); }} data-testid="cloud-workspace-local-account-close">{t('codeWorkspace.cancel')}</Button>
      </section>
    </Dialog>
  </>;
}
