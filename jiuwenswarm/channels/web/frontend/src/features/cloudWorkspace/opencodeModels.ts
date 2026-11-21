import type { ModelEntry, ModelSelection } from '../../types';
import { cloudRequest } from './client';

const nativePrefix = 'opencode:';

export type ManagedOpenCodeModels = {
  default: { id: string; label: string } | null;
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
    return policy as ManagedOpenCodeModels;
  } catch {
    return null;
  }
}

export function isOpenCodeNativeModel(selection?: ModelSelection | null): boolean {
  return selection?.type === 'model' && selection.id.startsWith(nativePrefix);
}

export function managedOpenCodeReason(policy: ManagedOpenCodeModels, selection: ModelSelection): string | null {
  if (selection.type !== 'model') return 'opencode_shared_model_group_unsupported';
  if (isOpenCodeNativeModel(selection)) {
    return selection.id === policy.default?.id ? null : 'opencode_model_not_registered';
  }
  return Object.prototype.hasOwnProperty.call(policy.reasons, selection.id) ? policy.reasons[selection.id] : null;
}

export function reportManagedOpenCodeRejection(reason: string): void {
  // Keep the local selection rejection independent of telemetry delivery.
  void cloudRequest('observations/opencode-model-rejection', { reason }, 3000).catch(() => {});
}

export function openCodeDefaultOption(policy: ManagedOpenCodeModels): ModelEntry | null {
  return policy.default && {
    model_id: policy.default.id,
    model_name: policy.default.label,
    model_provider: 'OpenCode',
    api_base: '',
    api_key: '',
  };
}
