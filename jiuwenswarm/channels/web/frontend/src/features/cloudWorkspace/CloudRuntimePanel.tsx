import { Plus, Server } from 'lucide-react';
import { useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import ModelPicker from '../../components/ModelPicker';
import { Button } from '../../components/ui/Button/Button';
import { Dialog } from '../../components/ui/Dialog/Dialog';
import { Input } from '../../components/ui/Input/Input';
import { Select } from '../../components/ui/Select/Select';
import { PageToolbar } from '../../components/ui/PageToolbar/PageToolbar';
import { generateUuidV4 } from '../../utils/uuid';
import { refreshCloudRuntime, requestRuntimeDevice, useRuntimeDeviceModels, type CloudRuntime, type CloudRuntimeTemplate } from './useProjectRuntime';
import './CloudRuntimePanel.css';

export function CloudRuntimePanel({ runtimes, templates, remote, onUse }: {
  runtimes: CloudRuntime[] | null;
  templates: CloudRuntimeTemplate[];
  remote: boolean;
  onUse: (runtime: CloudRuntime) => void;
}) {
  const { t } = useTranslation();
  const [profile, setProfile] = useState<string | null>(null);
  const availableTemplate = templates.find(item => item.available);
  const template = templates.find(item => item.runtime_profile_id === profile) ?? availableTemplate;
  const templateLabel = (id: string) => t(id === 'codex-cloud' ? 'cloudRuntime.codexStandard' : 'cloudRuntime.openCodeStandard');
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [chosenModelId, setChosenModelId] = useState<string | null>(null);
  const needsModel = template?.runtime_profile_id === 'codex-cloud' && template.supports_model_selection === true;
  const deviceModels = useRuntimeDeviceModels(open && needsModel && template.available, remote);
  const modelId = chosenModelId ?? deviceModels.catalog?.defaultModelId;
  const selectedModel = deviceModels.catalog?.models.find(model => modelId && model.model_id === modelId);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const operation = useRef(false);
  const registration = useRef<{ name: string; profile: string; modelId?: string; token: string } | null>(null);

  async function provision(event?: FormEvent, runtimeId?: string) {
    event?.preventDefault();
    const displayName = name.trim();
    const requestedModelId = needsModel ? selectedModel?.model_id : undefined;
    if (operation.current || (!runtimeId && (!template?.available || !displayName || needsModel && !requestedModelId))) return;
    operation.current = true;
    setBusy(runtimeId ?? 'create');
    setError(null);
    try {
      if (!runtimeId && template && (registration.current?.name !== displayName
        || registration.current.profile !== template.runtime_profile_id || registration.current.modelId !== requestedModelId)) {
        registration.current = {
          name: displayName, profile: template.runtime_profile_id, modelId: requestedModelId,
          token: generateUuidV4().replace(/-/g, ''),
        };
      }
      const result = runtimeId
        ? await requestRuntimeDevice('start', { runtime_id: runtimeId }, remote)
        : await requestRuntimeDevice('create', {
          display_name: displayName, runtime_profile_id: template!.runtime_profile_id,
          create_token: registration.current!.token,
          ...(requestedModelId ? { model_id: requestedModelId } : {}),
        }, remote);
      if (!runtimeId) {
        registration.current = null;
        setOpen(false);
      }
      if (result.start_failed) setError(t(result.start_error === 'RUNTIME_DEVICE_MODEL_UNAVAILABLE'
        ? 'cloudRuntime.codexModelUnavailable' : 'cloudRuntime.startFailed'));
    } catch (reason) {
      const code = (reason as { code?: string })?.code;
      setError(t(code === 'RUNTIME_DEVICE_NAME_CONFLICT' ? 'cloudRuntime.nameConflict'
        : code === 'RUNTIME_DEVICE_MODEL_UNAVAILABLE' ? 'cloudRuntime.codexModelUnavailable' : 'cloudRuntime.requestFailed'));
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
          {templates.length > 0 && <Button onClick={() => { setProfile(null); setChosenModelId(null); setName(''); setError(null); setOpen(true); }}
            disabled={!availableTemplate || busy !== null} data-testid="cloud-workspace-runtime-create">
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
                <span data-testid="cloud-workspace-runtime-provider">{runtime.provider_id === 'codex-direct' ? 'Codex' : 'OpenCode'}</span>
              </div>
              <div className="cloud-runtime-panel__status">
                <span data-testid="cloud-workspace-runtime-state" data-variant={busy === runtime.runtime_id ? 'starting' : runtime.state ?? 'unknown'}>
                  {t(`cloudRuntime.state.${busy === runtime.runtime_id ? 'starting' : runtime.state ?? 'unknown'}`)}
                </span>
                {!runtime.available && <span data-testid="cloud-workspace-runtime-admission">{t('cloudRuntime.admissionClosed')}</span>}
              </div>
              {runtime.runtime_id && (runtime.state === 'ready' ? <Button variant="quiet"
                onClick={() => onUse(runtime)} data-testid="cloud-workspace-runtime-use">
                {t('cloudRuntime.useInCode')}
              </Button> : <Button variant="quiet"
                onClick={() => void provision(undefined, runtime.runtime_id)} disabled={!runtime.available || busy !== null || runtime.state === 'starting'}
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
            <label htmlFor="cloud-runtime-profile">{t('cloudRuntime.template')}</label>
            <Select id="cloud-runtime-profile" type="button" value={template?.runtime_profile_id ?? ''}
              onChange={setProfile} disabled={busy !== null}
              options={templates.map(item => ({
                value: item.runtime_profile_id, label: templateLabel(item.runtime_profile_id),
                disabled: !item.available, disabledReason: t('cloudRuntime.admissionClosed'),
              }))} data-testid="cloud-workspace-runtime-profile" />
            {template && <span>{t('cloudRuntime.resources', { cpu: template.cpu / 1000, memory: template.memory })}</span>}
          </div>
          {needsModel && <div className="cloud-runtime-panel__template" role="group"
            aria-labelledby="cloud-runtime-model-label" data-testid="cloud-workspace-runtime-model">
            <span id="cloud-runtime-model-label">{t('cloudRuntime.model')}</span>
            <ModelPicker value={selectedModel?.model_name ?? null}
              catalog={{ models: deviceModels.catalog?.models ?? [], groups: [] }}
              selection={selectedModel?.model_id ? { type: 'model', id: selectedModel.model_id } : null}
              onChange={() => {}}
              onSelectionChange={selection => { if (selection.type === 'model') setChosenModelId(selection.id); }}
              includeModelGroups={false} excludeFreeModels disabled={!deviceModels.catalog?.models.length || busy !== null}
              testIdPrefix="cloud-workspace-runtime-model" />
            {deviceModels.error ? <div role="alert" data-testid="cloud-workspace-runtime-model-error">
              {t('cloudRuntime.modelLoadFailed')}
              <Button type="button" variant="quiet" onClick={deviceModels.retry}
                data-testid="cloud-workspace-runtime-model-retry">{t('codeWorkspace.refresh')}</Button>
            </div> : deviceModels.catalog?.models.length === 0 ? <span data-testid="cloud-workspace-runtime-model-empty">
              {t('cloudRuntime.noCompatibleModels')}
            </span> : !deviceModels.catalog && <span role="status" data-testid="cloud-workspace-runtime-model-loading">
              {t('cloudRuntime.modelLoading')}
            </span>}
          </div>}
          <label htmlFor="cloud-runtime-device-name">{t('cloudRuntime.name')}</label>
          <Input id="cloud-runtime-device-name" value={name} onChange={setName} changeOnBlur={false}
            required autoFocus maxLength={30} disabled={busy !== null} data-testid="cloud-workspace-runtime-device-name" />
          {open && error && <p role="alert" data-testid="cloud-workspace-runtime-create-error">{error}</p>}
          <div className="cloud-runtime-panel__actions">
            <Button type="button" variant="quiet" onClick={() => setOpen(false)} disabled={busy !== null} data-testid="cloud-workspace-runtime-create-cancel">{t('common.cancel')}</Button>
            <Button type="submit" disabled={!template?.available || !name.trim() || (needsModel && !selectedModel) || busy !== null} data-testid="cloud-workspace-runtime-create-submit">
              {t(busy === 'create' ? 'cloudRuntime.state.starting' : 'cloudRuntime.createAndStart')}
            </Button>
          </div>
        </form>
      </Dialog>
    </section>
  );
}
