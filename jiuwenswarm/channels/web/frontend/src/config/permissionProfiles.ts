import type { AgentMode, Permission } from '../types';

const NON_AGENT_PERMISSION_OPTIONS: Permission[] = ['default', 'full_access'];
const AGENT_PERMISSION_OPTIONS: Permission[] = ['default', 'automatic', 'full_access'];

export function permissionOptionsForMode(mode: AgentMode): Permission[] {
  return mode === 'agent' ? AGENT_PERMISSION_OPTIONS : NON_AGENT_PERMISSION_OPTIONS;
}

export function effectivePermissionProfile(persistedProfile: Permission, mode: AgentMode): Permission {
  if (persistedProfile === 'automatic' && mode !== 'agent') return 'default';
  return persistedProfile;
}

export interface RuntimePermissionStatus {
  supported_profiles: Permission[];
  update_timing: 'idle' | 'new_session';
  desired_profile: Permission;
  effective_profile: Permission | null;
  state: 'not_started' | 'pending' | 'applied' | 'failed' | 'unsupported';
}

export function providerPermissionProfiles(catalog: unknown, provider: string): Permission[] | undefined {
  if (provider === 'harness') return undefined;
  try {
    const profiles = JSON.parse(typeof catalog === 'string' ? catalog : '{}')[provider];
    return Array.isArray(profiles)
      ? profiles.filter((p): p is Permission => ['default', 'automatic', 'full_access'].includes(p)) : [];
  } catch { return []; }
}

