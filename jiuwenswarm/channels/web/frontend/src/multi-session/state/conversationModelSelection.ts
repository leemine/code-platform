import type { ModelSelection } from '../../types';

/** Collaboration is available only to interactive single-agent Work and Code chats. */
export function supportsMultiModelCollaboration(mode: string | undefined, cronId?: string | null): boolean {
  return !cronId && (mode === 'agent' || Boolean(mode?.startsWith('agent.')));
}

/** Keep the saved group intact when the feature is disabled; require an explicit model choice. */
export function isConversationModelGroupBlocked(settings: {
  mode?: string;
  cronId?: string | null;
  selectedModelSelection?: ModelSelection | null;
  collaborationEnabled: boolean;
}): boolean {
  return (
    supportsMultiModelCollaboration(settings.mode, settings.cronId) &&
    settings.selectedModelSelection?.type === 'model_group' &&
    !settings.collaborationEnabled
  );
}

export function buildConversationModelPayload(settings: {
  executionProvider?: string;
  mode?: string;
  selectedModelName: string | null;
  selectedModelSelection?: ModelSelection | null;
  cronId?: string | null;
}): { execution_provider?: string; model_name?: string; model_selection?: ModelSelection } {
  const model = settings.selectedModelSelection?.id
    ? { model_selection: { ...settings.selectedModelSelection } }
    : settings.selectedModelName
      ? { model_name: settings.selectedModelName }
      : {};
  return settings.executionProvider && settings.executionProvider !== 'harness'
    ? { ...model, execution_provider: settings.executionProvider }
    : model;
}
