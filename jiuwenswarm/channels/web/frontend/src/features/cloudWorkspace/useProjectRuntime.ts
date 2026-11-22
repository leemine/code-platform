import { useEffect, useState } from 'react';
import { webClient, webRequest } from '../../services/webClient';
import type { ModelEntry } from '../../types';
import { onOrganizationCredentialChange } from '../../services/organizationCredentialEvents';
import { localCloudAccountRequest, onLocalCloudAccountChange } from './localCloudAccountClient';

const states = ['not_created', 'not_started', 'starting', 'ready', 'idle', 'reconciling', 'unknown'] as const;
type RuntimeState = (typeof states)[number];

const profileProviders = { 'opencode-cloud': 'opencode-direct', 'codex-cloud': 'codex-direct' } as const;
type RuntimeProfileId = keyof typeof profileProviders;
type RuntimeProviderId = (typeof profileProviders)[RuntimeProfileId];

export interface CloudRuntime {
  provider_id: RuntimeProviderId;
  runtime_profile_id: RuntimeProfileId;
  runtime_id?: string;
  display_name: string | null;
  model_id?: string | null;
  session_models?: boolean;
  available: boolean;
  state?: RuntimeState;
}

export interface CloudRuntimeTemplate {
  runtime_profile_id: RuntimeProfileId;
  cpu: number;
  memory: number;
  available: boolean;
  default_session_models?: boolean;
  supports_model_selection?: boolean;
}

interface CloudRuntimeCatalog {
  runtimes: CloudRuntime[];
  templates: CloudRuntimeTemplate[];
  remote: boolean;
}

const RUNTIME_CHANGED = 'jiuwenswarm-cloud-runtime-changed';

function isRuntimeProfile(value: unknown): value is RuntimeProfileId {
  return value === 'opencode-cloud' || value === 'codex-cloud';
}

function readRuntime(runtime: CloudRuntime): CloudRuntime | null {
  if (!runtime || !isRuntimeProfile(runtime.runtime_profile_id)
    || runtime.provider_id !== profileProviders[runtime.runtime_profile_id]
    || runtime.model_id != null && (typeof runtime.model_id !== 'string' || !runtime.model_id.trim())
    || runtime.runtime_id !== undefined && !/^[a-f0-9]{32}$/.test(runtime.runtime_id)
    || typeof runtime.available !== 'boolean' || runtime.display_name !== null && typeof runtime.display_name !== 'string'
    || runtime.state !== undefined && !states.includes(runtime.state)) return null;
  return runtime;
}

export function refreshCloudRuntime() {
  window.dispatchEvent(new Event(RUNTIME_CHANGED));
}

function useRuntimeRevision(enabled: boolean) {
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    const refresh = () => setRevision(value => value + 1);
    const offAccount = onOrganizationCredentialChange(refresh);
    const offLocalAccount = onLocalCloudAccountChange(refresh);
    const offCloudReady = webClient.on('connection.cloud_ready', refresh);
    const offConnection = webClient.onStateChange(refresh);
    const offModels = webClient.on('models.updated', refresh);
    window.addEventListener(RUNTIME_CHANGED, refresh);
    return () => {
      offAccount(); offLocalAccount(); offCloudReady(); offConnection(); offModels();
      window.removeEventListener(RUNTIME_CHANGED, refresh);
    };
  }, [enabled]);
  return revision;
}

/** Older Gateways keep the original Provider catalog. */
export function useProjectRuntime(projectId: string | null) {
  const revision = useRuntimeRevision(Boolean(projectId));
  const [result, setResult] = useState<{ projectId: string; revision: number; runtime: CloudRuntime } | null>(null);

  useEffect(() => {
    setResult(null);
    if (!projectId) return;
    let current = true;
    // The existing cloud bridge decodes a remote project ID before forwarding.
    void webRequest<CloudRuntime>('project.runtime.status', { project_id: projectId }).then(value => {
      const runtime = readRuntime(value);
      if (current && runtime) setResult({ projectId, revision, runtime });
    }).catch(() => {});
    return () => { current = false; };
  }, [projectId, revision]);

  return result?.projectId === projectId && result.revision === revision ? result.runtime : null;
}

async function listCloudRuntimes(): Promise<CloudRuntimeCatalog> {
  let remote = false;
  const result = await webRequest<CloudRuntimeCatalog>('cloud.runtime.list', {}).catch(async () => {
    const identity = await localCloudAccountRequest('status');
    if (identity.kind !== 'local' || !identity.authenticated) return null;
    remote = true;
    return webRequest<CloudRuntimeCatalog>('cloud.runtime.list', { execution_target: 'cloud' });
  });
  return {
    remote,
    runtimes: Array.isArray(result?.runtimes) ? result.runtimes.map(readRuntime).filter(runtime => runtime !== null) : [],
    templates: Array.isArray(result?.templates) ? result.templates.filter(template =>
      isRuntimeProfile(template?.runtime_profile_id) && typeof template.available === 'boolean'
      && Number.isFinite(template.cpu) && Number.isFinite(template.memory)) : [],
  };
}

export function useCloudRuntimes(connected: boolean) {
  const revision = useRuntimeRevision(connected);
  const [result, setResult] = useState<{ revision: number; catalog: CloudRuntimeCatalog } | null>(null);
  useEffect(() => {
    if (!connected) { setResult(null); return; }
    let current = true;
    void listCloudRuntimes().then(catalog => {
      if (current) setResult({ revision, catalog });
    }).catch(() => {
      if (current) setResult({ revision, catalog: { runtimes: [], templates: [], remote: false } });
    });
    return () => { current = false; };
  }, [connected, revision]);
  return connected && result?.revision === revision ? result.catalog : null;
}

export async function requestRuntimeDevice(method: 'create' | 'start', params: Record<string, string>, remote: boolean) {
  const result = await webRequest<CloudRuntime & { start_failed?: boolean; start_error?: string }>(`cloud.runtime.${method}`, {
    ...params, ...(remote ? { execution_target: 'cloud' } : {}),
  }, { timeoutMs: 165_000 });
  if (!readRuntime(result)?.runtime_id) throw new Error('Invalid cloud runtime device');
  return result;
}


type CodexModelAdmission = { model_ids: string[]; default_model_id: string | null };

export function useCodexModelAdmission(enabled: boolean, remote: boolean) {
  const revision = useRuntimeRevision(enabled);
  const [result, setResult] = useState<{ revision: number; remote: boolean; catalog: CodexModelAdmission | null } | null>(null);
  useEffect(() => {
    if (!enabled) { setResult(null); return; }
    let current = true;
    void webRequest<CodexModelAdmission>('cloud.runtime.models', remote ? { execution_target: 'cloud' } : {}).then(catalog => {
      if (!Array.isArray(catalog?.model_ids)) throw new Error('Invalid Codex model catalog');
      if (current) setResult({ revision, remote, catalog });
    }).catch(() => {
      if (current) setResult({ revision, remote, catalog: null });
    });
    return () => { current = false; };
  }, [enabled, remote, revision]);
  return enabled && result?.revision === revision && result.remote === remote ? result : null;
}

type DeviceModels = { models: ModelEntry[]; defaultModelId: string | null };

export function useRuntimeDeviceModels(enabled: boolean, remote: boolean) {
  const revision = useRuntimeRevision(enabled);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ remote: boolean; revision: number; attempt: number; catalog: DeviceModels | null } | null>(null);
  useEffect(() => {
    if (!enabled) { setResult(null); return; }
    let current = true;
    const params = remote ? { execution_target: 'cloud' } : {};
    void Promise.all([
      webRequest<{ models: ModelEntry[] }>('models.list', params),
      webRequest<{ model_ids: string[]; default_model_id: string | null }>('cloud.runtime.models', params),
    ]).then(([account, supported]) => {
      if (!Array.isArray(account?.models) || !Array.isArray(supported?.model_ids)) throw new Error('Invalid runtime model catalog');
      if (!current) return;
      const ids = new Set(supported.model_ids);
      const models = account.models.filter(model => model.model_id && ids.has(model.model_id) && model.is_free !== true);
      const defaultModelId = models.find(model => model.model_id === supported.default_model_id)?.model_id ?? null;
      setResult({ remote, attempt, revision, catalog: { models, defaultModelId } });
    }).catch(() => {
      if (current) setResult({ remote, attempt, revision, catalog: null });
    });
    return () => { current = false; };
  }, [enabled, remote, revision, attempt]);

  const resolved = enabled && result?.remote === remote && result.revision === revision && result.attempt === attempt;
  return {
    catalog: resolved ? result.catalog : null,
    error: resolved && result.catalog === null,
    retry: () => setAttempt(value => value + 1),
  };
}
