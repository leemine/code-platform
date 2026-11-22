import { Plus, Server } from 'lucide-react';
import { useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '../../components/ui/Button/Button';
import { Dialog } from '../../components/ui/Dialog/Dialog';
import { Input } from '../../components/ui/Input/Input';
import { PageToolbar } from '../../components/ui/PageToolbar/PageToolbar';
import { generateUuidV4 } from '../../utils/uuid';
import { refreshCloudRuntime, requestRuntimeDevice, type CloudRuntime, type CloudRuntimeTemplate } from './useProjectRuntime';
import './CloudRuntimePanel.css';

export function CloudRuntimePanel({ runtimes, templates, remote, onUse }: {
  runtimes: CloudRuntime[] | null;
  templates: CloudRuntimeTemplate[];
  remote: boolean;
  onUse: (runtimeId: string) => void;
}) {
  const { t } = useTranslation();
  const template = templates[0];
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const operation = useRef(false);
  const registration = useRef<{ name: string; token: string } | null>(null);

  async function provision(event?: FormEvent, runtimeId?: string) {
    event?.preventDefault();
    const displayName = name.trim();
    if (operation.current || (!runtimeId && (!template?.available || !displayName))) return;
    operation.current = true;
    setBusy(runtimeId ?? 'create');
    setError(null);
    try {
      if (!runtimeId && registration.current?.name !== displayName) {
        registration.current = { name: displayName, token: generateUuidV4().replace(/-/g, '') };
      }
      const result = runtimeId
        ? await requestRuntimeDevice('start', { runtime_id: runtimeId }, remote)
        : await requestRuntimeDevice('create', {
          display_name: displayName, runtime_profile_id: template.runtime_profile_id,
          create_token: registration.current!.token,
        }, remote);
      if (!runtimeId) {
        registration.current = null;
        setOpen(false);
      }
      if (result.start_failed) setError(t('cloudRuntime.startFailed'));
    } catch (reason) {
      setError(t((reason as { code?: string })?.code === 'RUNTIME_DEVICE_NAME_CONFLICT'
        ? 'cloudRuntime.nameConflict' : 'cloudRuntime.requestFailed'));
    } finally {
      operation.current = false;
      setBusy(null);
      refreshCloudRuntime();
    }
  }

  return (
    <section className="cloud-runtime-panel" aria-labelledby="cloud-runtime-title" data-testid="cloud-workspace-runtime-panel">
      <PageToolbar>
        <h1 id="cloud-runtime-title" data-testid="cloud-workspace-runtime-title">{t('nav.runtime')}</h1>
        <div className="cloud-runtime-panel__actions">
          <Button variant="quiet" onClick={refreshCloudRuntime} disabled={runtimes === null} data-testid="cloud-workspace-runtime-refresh">
            {t('codeWorkspace.refresh')}
          </Button>
          {template && <Button onClick={() => { setName(''); setError(null); setOpen(true); }}
            disabled={!template.available || busy !== null} data-testid="cloud-workspace-runtime-create">
            <Plus size={16} aria-hidden />{t('cloudRuntime.createDevice')}
          </Button>}
        </div>
      </PageToolbar>
      {!open && error && <p role="alert" data-testid="cloud-workspace-runtime-error">{error}</p>}
      {runtimes === null ? <p role="status" data-testid="cloud-workspace-runtime-loading">{t('cloudRuntime.loading')}</p>
        : runtimes.length === 0 ? <p data-testid="cloud-workspace-runtime-empty">{t('cloudRuntime.empty')}</p>
        : <ul className="cloud-runtime-panel__list" data-testid="cloud-workspace-runtime-list">
          {runtimes.map(runtime => (
            <li key={runtime.runtime_id ?? runtime.runtime_profile_id} className="cloud-runtime-panel__row" data-testid="cloud-workspace-runtime-item" data-variant={runtime.runtime_id ?? runtime.runtime_profile_id}>
              <Server size={20} aria-hidden />
              <div className="cloud-runtime-panel__identity">
                <strong data-testid="cloud-workspace-runtime-name">{runtime.display_name ?? t('chat.executionProvider.cloudRuntimeName')}</strong>
                <span data-testid="cloud-workspace-runtime-provider">OpenCode</span>
              </div>
              <div className="cloud-runtime-panel__status">
                <span data-testid="cloud-workspace-runtime-state" data-variant={busy === runtime.runtime_id ? 'starting' : runtime.state ?? 'unknown'}>
                  {t(`cloudRuntime.state.${busy === runtime.runtime_id ? 'starting' : runtime.state ?? 'unknown'}`)}
                </span>
                {!runtime.available && <span data-testid="cloud-workspace-runtime-admission">{t('cloudRuntime.admissionClosed')}</span>}
              </div>
              {runtime.runtime_id && (runtime.state === 'ready' ? <Button variant="quiet"
                onClick={() => onUse(runtime.runtime_id!)} data-testid="cloud-workspace-runtime-use">
                {t('cloudRuntime.useInCode')}
              </Button> : <Button variant="quiet"
                onClick={() => void provision(undefined, runtime.runtime_id)} disabled={busy !== null || runtime.state === 'starting'}
                data-testid="cloud-workspace-runtime-start">
                {t('cloudRuntime.start')}
              </Button>)}
            </li>
          ))}
        </ul>}
      <Dialog open={open} titleId="cloud-runtime-create-title" className="cloud-runtime-panel__dialog"
        closeDisabled={busy !== null} onCancel={() => setOpen(false)} onBackdropClick={() => setOpen(false)}>
        <form onSubmit={provision} data-testid="cloud-workspace-runtime-create-form">
          <h2 id="cloud-runtime-create-title" data-testid="cloud-workspace-runtime-create-title">{t('cloudRuntime.createDevice')}</h2>
          <div className="cloud-runtime-panel__template" data-testid="cloud-workspace-runtime-template">
            <span>{t('cloudRuntime.template')}</span>
            <strong>{t('cloudRuntime.openCodeStandard')}</strong>
            {template && <span>{t('cloudRuntime.resources', { cpu: template.cpu / 1000, memory: template.memory })}</span>}
          </div>
          <label htmlFor="cloud-runtime-device-name">{t('cloudRuntime.name')}</label>
          <Input id="cloud-runtime-device-name" value={name} onChange={setName} changeOnBlur={false}
            required autoFocus maxLength={30} disabled={busy !== null} data-testid="cloud-workspace-runtime-device-name" />
          {open && error && <p role="alert" data-testid="cloud-workspace-runtime-create-error">{error}</p>}
          <div className="cloud-runtime-panel__actions">
            <Button type="button" variant="quiet" onClick={() => setOpen(false)} disabled={busy !== null} data-testid="cloud-workspace-runtime-create-cancel">{t('common.cancel')}</Button>
            <Button type="submit" disabled={!name.trim() || busy !== null} data-testid="cloud-workspace-runtime-create-submit">
              {t(busy === 'create' ? 'cloudRuntime.state.starting' : 'cloudRuntime.createAndStart')}
            </Button>
          </div>
        </form>
      </Dialog>
    </section>
  );
}
