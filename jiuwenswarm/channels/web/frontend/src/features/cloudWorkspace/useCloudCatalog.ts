import { useEffect, useState } from 'react';
import { useWorkspaceStore } from '../../stores/workspaceStore';
import { isCloudResource, webClient, webRequest } from '../../services/webClient';
import { NEW_CONVERSATION_ID } from '../../multi-session/state/newConversationLifecycle';
import type { ModelEntry, ModelGroup } from '../../types';
import { useSessionStore } from '../../stores/sessionStore';
import { readManagedOpenCodeModels } from './opencodeModels';
import { SETTINGS_CONFIG_CHANGED_EVENT } from '../settings/services/settingsContract';
import { parseModelGroups } from '../settings/modules/models/modelGroupAdapters';

interface AccountModels {
  models: ModelEntry[];
  active_model?: string;
  model_groups?: ModelGroup[];
}

const pending = new Map<string, Promise<[AccountModels | null, Record<string, unknown>]>>();
function readCatalog(target: string, active: boolean) {
  let request = pending.get(target);
  if (!request) {
    const params = active ? { execution_target: 'cloud' } : undefined;
    request = Promise.all([
      active ? webRequest<AccountModels>('models.list', params) : Promise.resolve(null),
      webRequest<Record<string, unknown>>('config.get', params),
    ]).finally(() => pending.delete(target));
    pending.set(target, request);
  }
  return request;
}

/** Read the selected backend's catalog without overwriting Local settings. */
export function useCloudCatalog(sessionId: string) {
  const location = useWorkspaceStore(s => s.codeLocation);
  const project = useWorkspaceStore(s => s.cloudProject);
  const workMode = useWorkspaceStore(s => s.workMode);
  const active = isCloudResource(sessionId) || sessionId === NEW_CONVERSATION_ID && workMode === 'code' && location === 'cloud';
  const target = active ? (isCloudResource(sessionId) ? sessionId : project?.project_id) : 'current-worker';
  const [catalog, setCatalog] = useState<{ target: string; models: ModelEntry[]; groups: ModelGroup[]; config: Record<string, unknown> } | null>(null);
  const [error, setError] = useState(false);
  const [revision, setRevision] = useState(0);
  const retry = () => window.dispatchEvent(new Event('jiuwenswarm-cloud-catalog-refresh'));
  useEffect(() => {
    const refresh = () => setRevision(n => n + 1);
    window.addEventListener('jiuwenswarm-cloud-catalog-refresh', refresh);
    window.addEventListener(SETTINGS_CONFIG_CHANGED_EVENT, refresh);
    const offReady = webClient.on('connection.cloud_ready', refresh);
    return () => {
      window.removeEventListener('jiuwenswarm-cloud-catalog-refresh', refresh);
      window.removeEventListener(SETTINGS_CONFIG_CHANGED_EVENT, refresh);
      offReady();
    };
  }, []);
  useEffect(() => {
    let current = true;
    setCatalog(null); setError(false);
    if (!target) return;
    void readCatalog(target, active).then(([models, config]) => {
      if (models && !Array.isArray(models.models)) throw new Error('Invalid cloud model catalog');
      if (!current) return;
      setCatalog({ target, models: models?.models ?? [], groups: parseModelGroups(models?.model_groups), config });
      if (models && sessionId === NEW_CONVERSATION_ID && useWorkspaceStore.getState().codeLocation === 'cloud') {
        const state = useSessionStore.getState(), draft = state.runtimes[sessionId];
        if (draft) {
          const selected = models.models.find(m => m.model_name === models.active_model) ?? models.models[0];
          const prior = draft.executionTarget === 'cloud' ? draft.selectedModelSelection : null;
          const managed = draft.executionProvider === 'opencode-direct' ? readManagedOpenCodeModels(config) : null;
          const selection = prior ?? (managed
            ? (managed.default ? { type: 'model' as const, id: managed.default.id } : null)
            : (selected?.model_id ? { type: 'model' as const, id: selected.model_id } : null));
          useSessionStore.setState({ runtimes: { ...state.runtimes, [sessionId]: { ...draft, executionTarget: 'cloud',
            selectedModelSelection: selection,
            selectedModelName: prior ? draft.selectedModelName : managed ? null : selected?.model_name ?? null,
          } } });
        }
      }
    }).catch(() => { if (current) setError(true); });
    return () => { current = false; };
  }, [target, active, revision]);
  return { active, catalog: catalog?.target === target ? catalog : null, error, retry };
}
