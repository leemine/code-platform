import { getApiBase } from '../../utils/env';

export type LocalCloudIdentity = { enabled: boolean; authenticated?: boolean; kind?: 'local' | 'cloud'; username?: string; cloud_origin?: string };

export async function localCloudAccountRequest(action: 'status' | 'login' | 'logout', body?: Record<string, string>): Promise<LocalCloudIdentity> {
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
    if (!response.ok) throw Object.assign(new Error('Cloud account request failed'), { code: response.status === 401 ? 'UNAUTHORIZED' : 'ACCOUNT_UNAVAILABLE' });
    return value;
  } finally { window.clearTimeout(timer); }
}

export function notifyLocalCloudAccountChange() {
  window.dispatchEvent(new Event('jiuwenswarm-cloud-account'));
  if (typeof BroadcastChannel !== 'undefined') {
    const channel = new BroadcastChannel('jiuwenswarm-cloud-account'); channel.postMessage('changed'); channel.close();
  }
}

export function onLocalCloudAccountChange(callback: () => void) {
  window.addEventListener('jiuwenswarm-cloud-account', callback);
  const channel = typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel('jiuwenswarm-cloud-account');
  if (channel) channel.onmessage = callback;
  return () => { window.removeEventListener('jiuwenswarm-cloud-account', callback); channel?.close(); };
}
