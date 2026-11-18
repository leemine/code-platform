import { webRequest } from '../../services/webClient';

/** Both entries reach the same cloud account broker. No navigation or credential transfer. */
export function cloudProjectRequest<T>(method: string, params: Record<string, unknown>, remote: boolean) {
  const { execution_target: _target, ...rest } = params;
  return webRequest<T>(method, remote ? { ...rest, execution_target: 'cloud' } : rest, { timeoutMs: 150000 });
}
