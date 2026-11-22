import { useEffect, useState } from 'react';
import { webClient, webRequest } from '../../services/webClient';
import { onOrganizationCredentialChange } from '../../services/organizationCredentialEvents';
import { localCloudAccountRequest, onLocalCloudAccountChange } from './localCloudAccountClient';

const states = ['not_created', 'not_started', 'starting', 'ready', 'idle', 'reconciling', 'unknown'] as const;
type RuntimeState = (typeof states)[number];

export interface CloudRuntime {
  provider_id: 'opencode-direct';
  runtime_profile_id: 'opencode-cloud';
  runtime_id?: string;
  display_name: string | null;
  available: boolean;
  state?: RuntimeState;
}

export interface CloudRuntimeTemplate {
  runtime_profile_id: 'opencode-cloud';
  cpu: number;
  memory: number;
  available: boolean;
}

interface CloudRuntimeCatalog {
  runtimes: CloudRuntime[];
  templates: CloudRuntimeTemplate[];
  remote: boolean;
}

const RUNTIME_CHANGED = 'jiuwenswarm-cloud-runtime-changed';

function readRuntime(runtime: CloudRuntime): CloudRuntime | null {
  if (runtime?.provider_id !== 'opencode-direct' || runtime.runtime_profile_id !== 'opencode-cloud'
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
    window.addEventListener(RUNTIME_CHANGED, refresh);
    return () => {
      offAccount(); offLocalAccount(); offCloudReady(); offConnection();
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
      template?.runtime_profile_id === 'opencode-cloud' && typeof template.available === 'boolean'
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
  const result = await webRequest<CloudRuntime & { start_failed?: boolean }>(`cloud.runtime.${method}`, {
    ...params, ...(remote ? { execution_target: 'cloud' } : {}),
  }, { timeoutMs: 165_000 });
  if (!readRuntime(result)?.runtime_id) throw new Error('Invalid cloud runtime device');
  return result;
}
