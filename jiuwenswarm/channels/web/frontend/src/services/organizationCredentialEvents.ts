import { getApiBase } from '../utils/env';
/** Cache invalidation only. Messages carry no identity or credential authority. */
const CHANNEL = 'jiuwen:organization-credentials';
const EVENT = 'jiuwen:organization-credentials-changed';

export interface OrganizationStatus {
  registration_enabled?: boolean;
  enabled: boolean;
  authenticated?: boolean;
  actor_id?: string;
  authority?: string;
  subject_id?: string;
  auth_backend?: string;
  username?: string;
  session_revision?: string;
  execution_mode?: string;
  sharing_enabled?: boolean;
}

/** Keep a route only after both statuses were freshly verified by the server.
 * The caller must still discard the old account UI, caches and connection.
 * Missing scope on older servers deliberately retains the root-only behavior.
 */
export function organizationCredentialReloadUrl(
  previous: OrganizationStatus | null | undefined,
  current: OrganizationStatus,
  href: string,
): string {
  const verified = (status: OrganizationStatus | null | undefined) =>
    status?.enabled === true &&
    status.authenticated === true &&
    status.auth_backend === 'builtin' &&
    [status.actor_id, status.authority, status.subject_id, status.session_revision].every(
      (value) => typeof value === 'string' && value.length > 0,
    );
  return verified(previous) &&
    verified(current) &&
    previous?.actor_id === current.actor_id &&
    previous?.authority === current.authority &&
    previous?.subject_id === current.subject_id
    ? href
    : new URL(href).origin + '/';
}

/** A failed probe is not evidence that authentication is disabled or changed. */
export async function readOrganizationStatus(): Promise<OrganizationStatus> {
  // A broken proxy may never finish a request. Keep the login gate closed, but
  // let its existing sequential retry recover instead of waiting indefinitely.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch(`${getApiBase()}/api/v1/auth/organization/status`, {
      credentials: 'same-origin',
      cache: 'no-store',
      signal: controller.signal,
    });
    // Only an explicitly absent old endpoint may use the existing legacy probe.
    if (response.status === 404) return { enabled: false };
    if (!response.ok) throw new Error('Authentication unavailable');
    const value: unknown = await response.json();
    if (!value || typeof value !== 'object') throw new Error('Invalid authentication status');
    const status = value as OrganizationStatus;
    if (typeof status.enabled !== 'boolean' || (status.enabled && typeof status.authenticated !== 'boolean')) {
      throw new Error('Invalid authentication status');
    }
    if (
      status.enabled &&
      status.authenticated &&
      status.auth_backend === 'builtin' &&
      (typeof status.session_revision !== 'string' ||
        !status.session_revision ||
        typeof status.actor_id !== 'string' ||
        !status.actor_id)
    ) {
      throw new Error('Invalid login identity');
    }
    return status;
  } finally {
    clearTimeout(timer);
  }
}

/** Account data caches are hints only; never carry one user's state into another. */
export function clearAccountCaches(): void {
  try {
    for (const key of Object.keys(localStorage)) {
      if (
        key.startsWith('jiuwenswarm.goal.') ||
        key.startsWith('jiuwenclaw_agent_') ||
        [
          'jiuwenswarm_cron_unread',
          'jiuwenclaw_selected_model',
          'jiuwenclaw_team_panel_state',
          'jiuwenclaw_single_agent_panel_state',
          'jiuwenswarm:last-file-picker-dir',
        ].includes(key)
      ) {
        localStorage.removeItem(key);
      }
    }
    sessionStorage.removeItem('jiuwenswarm.rsi.session_id');
    sessionStorage.removeItem('marketplace_oauth_access_token');
    sessionStorage.removeItem('marketplace_oauth_provider');
  } catch {
    /* Restricted storage: full page navigation still resets in-memory stores. */
  }
}

function openChannel(): BroadcastChannel | null {
  try {
    return typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel(CHANNEL);
  } catch {
    // Restricted browser contexts still have local events and visibility cleanup.
    return null;
  }
}

export function notifyOrganizationCredentialChange(): void {
  window.dispatchEvent(new window.Event(EVENT));
  const channel = openChannel();
  try {
    channel?.postMessage('changed');
  } catch {
    // Notification failure must not undo successful server-side login/logout.
  } finally {
    channel?.close();
  }
}

export function onOrganizationCredentialChange(clear: () => void): () => void {
  window.addEventListener(EVENT, clear);
  const channel = openChannel();
  if (channel) channel.onmessage = () => clear();
  return () => {
    window.removeEventListener(EVENT, clear);
    channel?.close();
  };
}

