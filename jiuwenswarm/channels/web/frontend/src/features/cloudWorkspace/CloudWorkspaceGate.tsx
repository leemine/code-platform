import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '../../components/ui/Button/Button';
import { AccountControl } from './AccountControl';
import { webClient } from '../../services/webClient';
import {
  clearAccountCaches, notifyOrganizationCredentialChange, onOrganizationCredentialChange,
  organizationCredentialReloadUrl, readOrganizationStatus, type OrganizationStatus,
} from '../../services/organizationCredentialEvents';
import { LoginPage } from '../auth/LoginPage';
import { cloudRequest, environmentState } from './client';
import { LocalCloudAccount } from './LocalCloudAccount';
import './cloudWorkspace.css';

type Phase = 'checking' | 'local' | 'login' | 'entry' | 'preparing' | 'ready' | 'unavailable' | 'environmentError' | 'logoutFailed';

/** UI composition only: the original environment service and Runtime retain ownership. */
export function CloudWorkspaceGate({ children }: { children: (footer?: ReactNode, options?: { shareExportDisabledReason: string }) => ReactNode }) {
  const { t } = useTranslation();
  const [phase, setPhase] = useState<Phase>('checking');
  const [identity, setIdentity] = useState<OrganizationStatus | null>(null);
  const epoch = useRef(0);
  const entering = useRef(false);
  const recoveryPhase = useRef<Phase>('entry');
  const identityRef = useRef<OrganizationStatus | null>(null);

  const discard = useCallback((current?: OrganizationStatus) => {
    epoch.current += 1;
    setPhase('checking');
    void webClient.disconnect('account changed');
    clearAccountCaches();
    window.location.replace(current
      ? organizationCredentialReloadUrl(identityRef.current, current, window.location.href)
      : window.location.origin + '/');
  }, []);

  const enter = useCallback(async () => {
    if (entering.current) return;
    entering.current = true;
    const generation = epoch.current;
    setPhase('preparing');
    try {
      // A persisted ALLOCATED row is not application readiness. Always use the
      // existing ensure path and its readiness probe before mounting App/WS.
      const result = await cloudRequest('environment/ensure', {}, 150000);
      if (environmentState(result) !== 'READY') throw new Error('Environment not ready');
      let current: OrganizationStatus;
      try {
        current = await readOrganizationStatus();
        if (!current.enabled) throw new Error('Account endpoint unavailable');
      } catch {
        // Account recovery is distinct from retrying a failed allocation.
        if (generation === epoch.current) {
          recoveryPhase.current = 'ready';
          setPhase('unavailable');
        }
        return;
      }
      if (generation !== epoch.current) return;
      if (!sameIdentity(identityRef.current, current)) { discard(current); return; }
      setPhase('ready');
    } catch {
      if (generation === epoch.current) setPhase('environmentError');
    } finally {
      entering.current = false;
    }
  }, [discard]);

  useEffect(() => {
    let disposed = false;
    const generation = epoch.current;
    void (async () => {
      try {
        const status = await readOrganizationStatus();
        if (disposed || generation !== epoch.current) return;
        identityRef.current = status;
        setIdentity(status);
        if (!status.enabled) { setPhase('local'); return; }
        if (!status.authenticated) { setPhase('login'); return; }
        if (status.auth_backend !== 'builtin' || status.execution_mode !== 'user_instance') throw new Error('Unsupported identity');
        const row = await cloudRequest('environment');
        if (disposed || generation !== epoch.current) return;
        // Reconnect an existing binding through the original chain. First-time
        // allocation stays behind the explicit cloud entry button.
        if (environmentState(row) === 'ALLOCATED') void enter();
        else setPhase('entry');
      } catch {
        if (!disposed && generation === epoch.current) setPhase(identityRef.current?.authenticated ? 'environmentError' : 'unavailable');
      }
    })();
    return () => { disposed = true; epoch.current += 1; };
  }, [enter]);

  useEffect(() => {
    if (!identity?.enabled || identity.auth_backend !== 'builtin' || ['unavailable', 'logoutFailed', 'checking'].includes(phase)) return;
    let disposed = false;
    let checking = false;
    const check = async () => {
      // ensure already performs a fresh identity check before exposing the App.
      if (disposed || checking || phase === 'preparing' || document.visibilityState === 'hidden') return;
      checking = true;
      try {
        const current = await readOrganizationStatus();
        if (!current.enabled) throw new Error('Account endpoint unavailable');
        if (!disposed && ((current.authenticated || identityRef.current?.authenticated) && !sameIdentity(identityRef.current, current))) discard(current);
      } catch {
        if (!disposed) {
          recoveryPhase.current = phase;
          epoch.current += 1;
          void webClient.disconnect('account service unavailable');
          setPhase('unavailable');
        }
      } finally { checking = false; }
    };
    const off = onOrganizationCredentialChange(() => discard());
    const timer = window.setInterval(check, 2000);
    window.addEventListener('focus', check);
    document.addEventListener('visibilitychange', check);
    return () => {
      disposed = true;
      off();
      window.clearInterval(timer);
      window.removeEventListener('focus', check);
      document.removeEventListener('visibilitychange', check);
    };
  }, [identity, phase, discard]);

  const retryIdentity = useCallback(async () => {
    const generation = epoch.current;
    setPhase('checking');
    try {
      const current = await readOrganizationStatus();
      if (generation !== epoch.current) return;
      if (identityRef.current?.enabled && !current.enabled) throw new Error('Account endpoint unavailable');
      // Retain the previous verified principal across an outage until the fresh
      // probe decides whether the current route still belongs to that account.
      if (sameIdentity(identityRef.current, current)) {
        // An outage is not an account change. Remount through the original App
        // connection/history path without clearing preferences or allocating again.
        identityRef.current = current;
        setIdentity(current);
        setPhase(recoveryPhase.current);
      } else if (current.enabled) discard(current);
      else window.location.reload();
    } catch {
      if (generation === epoch.current) setPhase('unavailable');
    }
  }, [discard]);

  useEffect(() => {
    if (phase !== 'unavailable') return;
    // Extracted from codeswarm: schedule only after the preceding probe settles.
    // Do not periodically invalidate a slow successful authentication response.
    const timer = window.setTimeout(() => void retryIdentity(), 2000);
    return () => window.clearTimeout(timer);
  }, [phase, retryIdentity]);

  async function logout() {
    epoch.current += 1;
    setPhase('checking');
    await webClient.disconnect('account logout');
    try {
      await cloudRequest('logout', {});
      clearAccountCaches();
      notifyOrganizationCredentialChange();
      window.location.replace(window.location.origin + '/');
    } catch { setPhase('logoutFailed'); }
  }
  const logoutButton = <Button variant="quiet" onClick={() => void logout()} data-testid="auth-logout-button">
    {t('cloudWorkspace.logout')}
  </Button>;
  const footer = <AccountControl authenticated username={identity?.username}
    loginLabel={t('auth.login')} logoutLabel={t('cloudWorkspace.logout')} onLogout={() => void logout()}
    prefix="cloud-workspace-account" triggerTestId="cloud-workspace-identity" logoutTestId="auth-logout-button" />;
  if (phase === 'local') return children(<LocalCloudAccount />);
  if (phase === 'login') return <LoginPage registrationEnabled={identity?.registration_enabled === true} />;
  if (phase === 'ready') return children(footer, { shareExportDisabledReason: t('cloudWorkspace.shareExportUnavailable') });
  const retry = ['unavailable', 'environmentError', 'logoutFailed'].includes(phase);
  return <main className="cloud-workspace-page" data-testid="cloud-workspace-gate" data-phase={phase}>
    <section className="cloud-workspace-card">
      <h1>{t('cloudWorkspace.title')}</h1>
      <p role={retry ? 'alert' : 'status'} data-testid="cloud-workspace-status">{t(`cloudWorkspace.${phase}`)}</p>
      {identity?.authenticated && <p data-testid="cloud-workspace-identity">{identity.username}</p>}
      {phase === 'entry' && <Button variant="primary" onClick={() => void enter()} data-testid="cloud-workspace-enter">{t('cloudWorkspace.enter')}</Button>}
      {retry && <Button onClick={() => phase === 'environmentError' ? void enter() : phase === 'logoutFailed' ? void logout() : void retryIdentity()}
        data-testid="cloud-workspace-retry">{t('cloudWorkspace.retry')}</Button>}
      {identity?.authenticated && !['checking', 'logoutFailed'].includes(phase) && logoutButton}
    </section>
  </main>;
}

function sameIdentity(previous: OrganizationStatus | null, current: OrganizationStatus): boolean {
  return !!previous?.authenticated && current.enabled && current.authenticated === true &&
    ['actor_id', 'authority', 'subject_id', 'session_revision'].every(
      key => !!previous[key as keyof OrganizationStatus] && previous[key as keyof OrganizationStatus] === current[key as keyof OrganizationStatus],
    );
}
