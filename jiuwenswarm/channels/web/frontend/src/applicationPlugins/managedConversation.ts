import { useSyncExternalStore } from 'react';
import type { AskUserQuestionPayload, UserAnswer } from '../types';
import type { ApplicationPluginContribution } from './types';

export interface ManagedConversation {
  follow(text: string, operationId: string): Promise<void>;
  pending(signal: AbortSignal): Promise<AskUserQuestionPayload | null>;
  answer(requestId: string, answers: UserAnswer[]): Promise<void>;
}

export interface PluginConversationModule {
  applicationPluginId: string;
  applicationPluginConversation: (sessionId: string) => Promise<ManagedConversation | null>;
}

const plugins: PluginConversationModule[] = [];
const listeners = new Set<() => void>();
let activeIds: ReadonlySet<string> = new Set();

export function configureApplicationConversations(contributions: readonly ApplicationPluginContribution[]): void {
  const ids = new Set(contributions.filter(plugin => plugin.enabled !== false).map(plugin => plugin.plugin_id));
  if (activeIds.size === ids.size && [...ids].every(id => activeIds.has(id))) return;
  activeIds = ids;
  listeners.forEach(listener => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function useApplicationConversationAvailability(): ReadonlySet<string> {
  return useSyncExternalStore(subscribe, () => activeIds);
}

export function registerApplicationConversation(plugin: PluginConversationModule): void {
  plugins.push(plugin);
}

export async function resolveApplicationConversation(sessionId: string): Promise<ManagedConversation | null> {
  for (const plugin of plugins) {
    if (!activeIds.has(plugin.applicationPluginId)) continue;
    const conversation = await plugin.applicationPluginConversation(sessionId);
    if (conversation) return conversation;
  }
  return null;
}
