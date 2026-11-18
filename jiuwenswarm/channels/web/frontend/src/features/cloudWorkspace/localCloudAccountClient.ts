import { getApiBase } from '../../utils/env';

export type LocalCloudIdentity = { enabled: boolean; authenticated?: boolean; kind?: 'local' | 'cloud'; username?: string; cloud_origin?: string };
type AccountAction = 'status' | 'register' | 'login' | 'logout';

async function performAccountRequest(action: AccountAction, body?: Record<string, string>): Promise<LocalCloudIdentity> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(`${getApiBase()}/api/v1/data-sync/${action}`, {
      method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', cache: 'no-store',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json', 'X-Jiuwen-Sync': '1' },
      body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal,
    });
    if (action === 'status' && response.status === 404) return { enabled: false };
    const value = await response.json();
    if (!response.ok) throw Object.assign(new Error('Cloud account request failed'), {
      code: response.status === 401 ? 'UNAUTHORIZED' : value?.code ?? 'ACCOUNT_UNAVAILABLE',
    });
    return value;
  } finally { window.clearTimeout(timer); }
}

// Share only unfinished reads; completed identities are never cached.
let pendingStatus: Promise<LocalCloudIdentity> | null = null;
export function localCloudAccountRequest(action: AccountAction, body?: Record<string, string>): Promise<LocalCloudIdentity> {
  if (action !== 'status') {
    pendingStatus = null;
    return performAccountRequest(action, body).finally(() => { pendingStatus = null; });
  }
  if (pendingStatus) return pendingStatus;
  const current = performAccountRequest(action).finally(() => {
    if (pendingStatus === current) pendingStatus = null;
  });
  pendingStatus = current;
  return current;
}

// Window events notify this document; BroadcastChannel only notifies other documents.
const localAccountSender = Math.random().toString(36).slice(2);

export function notifyLocalCloudAccountChange() {
  pendingStatus = null;
  window.dispatchEvent(new Event('jiuwenswarm-cloud-account'));
  if (typeof BroadcastChannel !== 'undefined') {
    const channel = new BroadcastChannel('jiuwenswarm-cloud-account'); channel.postMessage({ type: 'changed', sender: localAccountSender }); channel.close();
  }
}

export function onLocalCloudAccountChange(callback: () => void) {
  window.addEventListener('jiuwenswarm-cloud-account', callback);
  const channel = typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel('jiuwenswarm-cloud-account');
  if (channel) channel.onmessage = event => {
    if (event.data?.sender !== localAccountSender) { pendingStatus = null; callback(); }
  };
  return () => { window.removeEventListener('jiuwenswarm-cloud-account', callback); channel?.close(); };
}

/** Open the existing account dialog in this page; credentials stay on the same-origin bridge. */
export function requestLocalCloudLogin(complete: (authenticated: boolean) => void) {
  window.dispatchEvent(new CustomEvent('jiuwenswarm-cloud-login-request', { detail: complete }));
}

export async function localCloudWorkspaceRequest<T>(operation: 'environment' | 'ensure' | 'list' | 'mkdir' | 'open', params: Record<string, unknown> = {}): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 155000);
  try {
    const response = await fetch(`${getApiBase()}/api/v1/data-sync/workspace`, {
      method: 'POST', credentials: 'same-origin', cache: 'no-store',
      headers: { 'Content-Type': 'application/json', 'X-Jiuwen-Sync': '1' },
      body: JSON.stringify({ ...params, operation }), signal: controller.signal,
    });
    const value = await response.json();
    if (!response.ok) throw Object.assign(new Error('Cloud workspace request failed'), {
      code: response.status === 401 ? 'UNAUTHORIZED' : value.code || 'WORKSPACE_UNAVAILABLE',
    });
    return value;
  } finally { window.clearTimeout(timer); }
}

export type LocalCloudModelSyncStatus = {
  scope: string | null;
  enabled_ids: string[];
  applied_without_restart?: boolean;
};

export type LocalCloudModelSyncOperation =
  | { operation: 'set'; model_id: string; enabled: boolean }
  | { operation: 'refresh'; model_id: string };

export async function localCloudModelSyncRequest(
  command?: LocalCloudModelSyncOperation & { scope: string },
): Promise<LocalCloudModelSyncStatus | null> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), command ? 155000 : 30000);
  try {
    const response = await fetch(`${getApiBase()}/api/v1/data-sync/model-sync`, {
      method: command ? 'POST' : 'GET',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: command ? { 'Content-Type': 'application/json', 'X-Jiuwen-Sync': '1' } : undefined,
      body: command ? JSON.stringify(command) : undefined,
      signal: controller.signal,
    });
    if (!command && response.status === 404) return null;
    if (!response.ok) throw new Error('Cloud model sync failed');
    const status: LocalCloudModelSyncStatus = await response.json();
    if (!status || (status.scope !== null && typeof status.scope !== 'string') ||
        !Array.isArray(status.enabled_ids) || status.enabled_ids.some(id => typeof id !== 'string')) {
      throw new Error('Invalid cloud model sync status');
    }
    return status;
  } finally {
    window.clearTimeout(timer);
  }
}
