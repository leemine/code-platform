import type { ModelEntry, ModelSelection } from '../../types';
import { cloudRequest } from './client';

const nativePrefix = 'opencode:';

export type ManagedOpenCodeModels = {
  default: { id: string; label: string } | null;
  registered?: string[];
  error?: string | null;
  reasons: Record<string, string>;
};

export function readManagedOpenCodeModels(config?: Record<string, unknown>): ManagedOpenCodeModels | null {
  const value = config?.managed_opencode_models;
  if (typeof value !== 'string') return null;
  try {
    const policy = JSON.parse(value);
    if (!policy || !policy.reasons || typeof policy.reasons !== 'object') return null;
    if (policy.default !== null && (
      typeof policy.default?.id !== 'string' || !policy.default.id.startsWith(nativePrefix)
      || typeof policy.default.label !== 'string'
    )) return null;
    if (policy.registered !== undefined && (!Array.isArray(policy.registered)
      || !policy.registered.every((id: unknown) => typeof id === 'string'))) return null;
    if (policy.default && typeof policy.default_account_id === 'string' && policy.default_account_id) {
      return { ...policy, default: { id: policy.default_account_id, label: policy.default.label } };
    }
    return policy as ManagedOpenCodeModels;
  } catch {
    return null;
  }
}

export function isOpenCodeNativeModel(selection?: ModelSelection | null): boolean {
  return selection?.type === 'model' && selection.id.startsWith(nativePrefix);
}

export function managedOpenCodeReason(policy: ManagedOpenCodeModels, selection: ModelSelection): string | null {
  if (policy.error) return policy.error;
  if (selection.type !== 'model') return 'opencode_shared_model_group_unsupported';
  if (isOpenCodeNativeModel(selection)) {
    return (selection.id === policy.default?.id || policy.registered?.includes(selection.id.slice(nativePrefix.length))) ? null : 'opencode_model_not_registered';
  }
  return Object.prototype.hasOwnProperty.call(policy.reasons, selection.id) ? policy.reasons[selection.id] : null;
}

export function reportManagedOpenCodeRejection(reason: string): void {
  // Keep the local selection rejection independent of telemetry delivery.
  void cloudRequest('observations/opencode-model-rejection', { reason }, 3000).catch(() => {});
}

export function openCodeDefaultOption(policy: ManagedOpenCodeModels): ModelEntry | null {
  if (!policy.default?.id.startsWith(nativePrefix)) return null;
  return {
    model_id: policy.default.id,
    model_name: policy.default.label,
    model_provider: 'OpenCode',
    api_base: '',
    api_key: '',
  };
}
