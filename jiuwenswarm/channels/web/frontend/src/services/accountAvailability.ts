import { getApiBase } from '../utils/env';

export type AccountFailureKind = 'localUnavailable' | 'connectionUnavailable' | 'authorityUnavailable' | 'unavailable';

/** Presentation facts only; no cached identity or authorization decision. */
export class AccountAvailabilityError extends Error {
  constructor(readonly kind: AccountFailureKind) {
    super('Account connection unavailable');
  }
}

export function accountTransportFailure(): AccountFailureKind {
  const hostname = new URL(getApiBase() || window.location.origin, window.location.href).hostname;
  return ['localhost', '127.0.0.1', '[::1]'].includes(hostname) ? 'localUnavailable' : 'connectionUnavailable';
}

export function accountFailureKind(error: unknown): AccountFailureKind {
  return error instanceof AccountAvailabilityError ? error.kind : 'unavailable';
}

export async function accountResponseFailure(response: Response): Promise<AccountFailureKind> {
  // Only explicit server codes identify the failing hop. A generic 503 or an
  // unreadable body cannot establish that the cloud authority is unavailable.
  const value = await response.json().catch(() => null);
  if (value?.code === 'AUTHORITY_UNAVAILABLE') return 'authorityUnavailable';
  if (value?.code === 'LOCAL_SERVICE_UNAVAILABLE') return accountTransportFailure();
  return 'unavailable';
}
