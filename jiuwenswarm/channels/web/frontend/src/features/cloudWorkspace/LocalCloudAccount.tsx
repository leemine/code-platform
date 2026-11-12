import { useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '../../components/ui/Button/Button';
import { Dialog } from '../../components/ui/Dialog/Dialog';
import { localCloudAccountRequest, notifyLocalCloudAccountChange, onLocalCloudAccountChange, type LocalCloudIdentity } from './localCloudAccountClient';
import './LocalCloudAccount.css';

export function LocalCloudAccount() {
  const { t } = useTranslation();
  const title = useId(), generation = useRef(0), working = useRef(false);
  const [status, setStatus] = useState<LocalCloudIdentity | null>(null);
  const [open, setOpen] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [username, setUsername] = useState(''), [password, setPassword] = useState('');
  const errorText = (reason: unknown) => t((reason as { code?: string })?.code === 'UNAUTHORIZED' ? 'localCloudAccount.loginRequired' : 'localCloudAccount.unavailable');

  async function load(epoch: number) {
    const value = await localCloudAccountRequest('status');
    if (epoch === generation.current) { setStatus(value); setError(''); }
  }
  async function run(action: (epoch: number) => Promise<void>) {
    if (working.current) return;
    const epoch = generation.current;
    working.current = true; setBusy(true); setError('');
    try { await action(epoch); }
    catch (reason) {
      if (epoch === generation.current) {
        setError(errorText(reason));
        if ((reason as { code?: string })?.code === 'UNAUTHORIZED') setStatus({ enabled: true, kind: 'local', authenticated: false });
      }
    } finally { if (epoch === generation.current) { working.current = false; setBusy(false); } }
  }
  useEffect(() => {
    const reload = () => {
      generation.current++; working.current = false; setBusy(false); setPassword('');
      void run(load);
    };
    reload(); const off = onLocalCloudAccountChange(reload);
    window.addEventListener('focus', reload);
    return () => { generation.current++; off(); window.removeEventListener('focus', reload); };
  }, []);
  if (status?.enabled === false || status?.kind === 'cloud' || (!status && !error)) return null;
  return <>
    <Button variant="quiet" onClick={() => setOpen(true)} data-testid="cloud-workspace-local-account-trigger">{status?.authenticated ? status.username : t('localCloudAccount.login')}</Button>
    <Dialog open={open} titleId={title} onCancel={() => { if (!busy) { setOpen(false); setPassword(''); } }} closeDisabled={busy} className="local-cloud-account-dialog">
      <section data-testid="cloud-workspace-local-account-dialog">
        <h2 id={title} data-testid="cloud-workspace-local-account-title">{t('localCloudAccount.title')}</h2>
        {status?.cloud_origin && <p data-testid="cloud-workspace-local-account-destination">{t('localCloudAccount.destination', { origin: status.cloud_origin })}</p>}
        {status?.authenticated ? <>
          <p data-testid="cloud-workspace-local-account-identity">{status.username} · {t('localCloudAccount.signedIn')}</p>
          <Button disabled={busy} onClick={() => void run(async epoch => {
            await localCloudAccountRequest('logout', {});
            if (epoch === generation.current) notifyLocalCloudAccountChange();
          })} data-testid="cloud-workspace-local-account-logout">{t('localCloudAccount.logout')}</Button>
        </> : status?.enabled && <form onSubmit={event => { event.preventDefault(); void run(async epoch => {
          const secret = password; setPassword('');
          await localCloudAccountRequest('login', { username, password: secret });
          if (epoch === generation.current) notifyLocalCloudAccountChange();
        }); }} data-testid="cloud-workspace-local-account-form">
          <label data-testid="cloud-workspace-local-account-username-label">{t('localCloudAccount.username')}<input autoComplete="username" value={username} disabled={busy} onChange={event => setUsername(event.target.value)} data-testid="cloud-workspace-local-account-username" /></label>
          <label data-testid="cloud-workspace-local-account-password-label">{t('localCloudAccount.password')}<input type="password" autoComplete="current-password" value={password} disabled={busy} onChange={event => setPassword(event.target.value)} data-testid="cloud-workspace-local-account-password" /></label>
          <Button type="submit" disabled={busy || !username || !password} data-testid="cloud-workspace-local-account-login">{t('localCloudAccount.login')}</Button>
        </form>}
        {error && <><p role="alert" data-testid="cloud-workspace-local-account-error">{error}</p><Button disabled={busy} onClick={() => void run(load)} data-testid="cloud-workspace-local-account-retry">{t('localCloudAccount.retry')}</Button></>}
        <Button variant="quiet" disabled={busy} onClick={() => { setOpen(false); setPassword(''); }} data-testid="cloud-workspace-local-account-close">{t('codeWorkspace.cancel')}</Button>
      </section>
    </Dialog>
  </>;
}
