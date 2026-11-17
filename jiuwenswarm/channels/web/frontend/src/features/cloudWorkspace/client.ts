import { getApiBase } from '../../utils/env';
import { AccountAvailabilityError, accountResponseFailure, accountTransportFailure, type AccountFailureKind } from '../../services/accountAvailability';

export class CloudRequestError extends AccountAvailabilityError {
  constructor(readonly status: number, kind: AccountFailureKind = 'unavailable') {
    super(kind);
  }
}

/** Same-origin HttpOnly sessions; requests never carry account/instance selectors. */
export async function cloudRequest(path: string, body?: Record<string, unknown>, timeout = 10000): Promise<unknown> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeout);
  let received = false;
  try {
    const response = await fetch(`${getApiBase()}/api/v1/auth/organization/${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json', 'X-Jiuwen-Auth': '1' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    received = true;
    if (!response.ok) throw new CloudRequestError(response.status, await accountResponseFailure(response));
    return await response.json();
  } catch (error) {
    if (error instanceof AccountAvailabilityError || received) throw error;
    throw new AccountAvailabilityError(accountTransportFailure());
  } finally {
    window.clearTimeout(timer);
  }
}

export function environmentState(value: unknown): string {
  if (!value || typeof value !== 'object' || !('state' in value) || typeof value.state !== 'string') {
    throw new Error('Invalid environment status');
  }
  return value.state;
}
