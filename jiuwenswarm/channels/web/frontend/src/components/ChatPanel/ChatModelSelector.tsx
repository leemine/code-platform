import { useEffect, useState } from 'react';
import {
  isConversationModelGroupBlocked,
  supportsMultiModelCollaboration,
} from '../../multi-session/state/conversationModelSelection';
import { useMultiModelCollaborationEnabled } from '../../features/multiModelCollaboration/featureConfig';
import { useTranslation } from 'react-i18next';
import { requestSettingsModule } from '../../features/settings/settingsNavigation';
import { selectionFromModel } from '../../features/settings/modules/models/modelGroupAdapters';
import { NEW_CONVERSATION_ID } from '../../multi-session/state/newConversationLifecycle';
import { webRequest } from '../../services/webClient';
import { useChatStore } from '../../stores/chatStore';
import {
  isModelCatalogPending,
  isModelSelectionAvailable,
  resolveAvailableModelSelection,
  resolveChatModelSelection,
  useSessionStore,
} from '../../stores/sessionStore';
import type { ModelSelection } from '../../types';
import ModelPicker from '../ModelPicker';
import { useTeamSelectorStore } from '../../stores/teamSelectorStore';
import { useTeamOrganizationUiEnabled } from '../../features/teamOrganization/featureConfig';
import {
  isOpenCodeNativeModel,
  managedOpenCodeReason,
  openCodeDefaultOption,
  readManagedOpenCodeModels,
  reportManagedOpenCodeRejection,
} from '../../features/cloudWorkspace/opencodeModels';
import { useCloudCatalog } from '../../features/cloudWorkspace/useCloudCatalog';

function openModelSettings(): void {
  requestSettingsModule('models');
}

function sameModelSelection(left: ModelSelection | null, right: ModelSelection | null): boolean {
  if (!left || !right) return left === right;
  return left.type === right.type
    && left.id === right.id
    && (left.type !== 'model_group' || left.route_id === right.route_id);
}

function ConversationModelSelector({
  disabled = false,
  sessionId,
  allowModelGroups = true,
}: {
  disabled?: boolean;
  /** Session this selector edits. Surfaces that own a session (the design
   * canvas) pass it explicitly: `activeSessionId` follows the app route and can
   * point at another conversation while the surface stays mounted (#5394). */
  sessionId?: string;
  allowModelGroups?: boolean;
}): JSX.Element | null {
  const { t } = useTranslation();
  const localModels = useSessionStore((state) => state.chatAvailableModels);
  const localModelGroups = useSessionStore((state) => state.availableModelGroups);
  const activeSessionId = useChatStore((state) => state.activeSessionId);
  const boundSessionId = sessionId || activeSessionId;
  const cloud = useCloudCatalog(boundSessionId || NEW_CONVERSATION_ID);
  const provider = useSessionStore((state) => state.runtimes[boundSessionId ?? '']?.executionProvider);
  const runtimeId = useSessionStore((state) => state.runtimes[boundSessionId ?? '']?.executionRuntimeId);
  const codexDevice = provider === 'codex-direct' && Boolean(runtimeId);
  const managed = provider === 'opencode-direct' ? readManagedOpenCodeModels(cloud.catalog?.config) : null;
  const loadingOpenCode = provider === 'opencode-direct' && !cloud.catalog;
  const preserveSelection = cloud.active || loadingOpenCode || managed !== null;
  const defaultOption = managed ? openCodeDefaultOption(managed) : null;
  const availableModels = cloud.active ? cloud.catalog?.models ?? [] : localModels;
  const models = defaultOption ? [defaultOption, ...availableModels] : availableModels;
  const modelGroups = cloud.active ? cloud.catalog?.groups ?? [] : localModelGroups;
  const organizationEnabled = useTeamOrganizationUiEnabled();
  const selectedChildTeam = useTeamSelectorStore((state) => {
    if (!organizationEnabled) return undefined;
    const runtime = state.runtimes[boundSessionId ?? ''];
    return runtime?.teams.find((team) =>
      team.team_id === runtime.selectedTeamId && team.organization_id && !team.is_owner,
    );
  });
  const selectedModelName = useSessionStore(
    (state) => state.runtimes[boundSessionId ?? '']?.selectedModelName ?? null,
  );
  const selectedModelSelection = useSessionStore(
    (state) => state.runtimes[boundSessionId ?? '']?.selectedModelSelection ?? null,
  );
  const defaultModelName = useSessionStore((state) => state.defaultModelName);
  const setSelectedModelName = useSessionStore((state) => state.setSelectedModelName);
  const setSelectedModelSelection = useSessionStore((state) => state.setSelectedModelSelection);
  const [selectionError, setSelectionError] = useState('');
  const [saving, setSaving] = useState(false);
  useEffect(() => setSelectionError(''), [provider, boundSessionId]);
  const mode = useSessionStore((state) => state.runtimes[boundSessionId ?? '']?.mode);
  const cronId = useSessionStore((state) =>
    state.currentSession?.session_id === boundSessionId
      ? state.currentSession.cron_id
      : state.sessions.find((session) => session.session_id === boundSessionId)?.cron_id,
  );
  const collaborationEnabled = useMultiModelCollaborationEnabled();
  const singleAgent = supportsMultiModelCollaboration(mode, cronId);
  const includeModelGroups = allowModelGroups && (!singleAgent || collaborationEnabled);
  const selectableGroups = allowModelGroups ? modelGroups : [];
  const groupBlocked = isConversationModelGroupBlocked({
    mode,
    cronId,
    selectedModelSelection,
    collaborationEnabled,
  });

  // Deleted/disabled model groups must fall back and be written back (#5424).
  useEffect(() => {
    if (selectedChildTeam || preserveSelection || isOpenCodeNativeModel(selectedModelSelection)) return;
    if (!boundSessionId || disabled) return;
    if (groupBlocked && allowModelGroups) return;
    if (!selectedModelSelection) return;
    // Empty catalog means models.list has not arrived yet — not that the selection
    // was deleted. Clearing here races metadata restore on refresh (#5860).
    if (isModelCatalogPending(models, modelGroups)) return;
    if (isModelSelectionAvailable(selectedModelSelection, models, selectableGroups)) return;
    if (useChatStore.getState().getRuntime(boundSessionId)?.isProcessing) return;
    const next = resolveAvailableModelSelection(selectedModelSelection, models, selectableGroups);
    if (sameModelSelection(next, selectedModelSelection)) return;
    setSelectionError('');
    if (!next) {
      setSelectedModelSelection(boundSessionId, null);
      return;
    }
    setSelectedModelSelection(boundSessionId, next);
    if (boundSessionId === NEW_CONVERSATION_ID) return;
    void webRequest('session.selection.set', {
      session_id: boundSessionId,
      model_selection: next,
    }).catch((error: unknown) => {
      setSelectionError(
        error instanceof Error && error.message ? error.message : t('chat.modelSelector.selectionFailed'),
      );
    });
  }, [
    boundSessionId,
    allowModelGroups,
    disabled,
    groupBlocked,
    selectedModelSelection,
    selectedChildTeam,
    preserveSelection,
    models,
    selectableGroups,
    setSelectedModelSelection,
    t,
  ]);

  // Preserve the saved stable choice, even if the feature or its catalog entry is unavailable.
  const selected = managed && !selectedModelSelection
    ? null : resolveChatModelSelection(models, selectedModelName, cloud.active ? null : defaultModelName);
  const inferredSelection =
    selectedModelSelection
    ?? selectionFromModel(selected)
    ?? null;
  const catalogPending = isModelCatalogPending(models, modelGroups);
  const healedSelection = preserveSelection || isOpenCodeNativeModel(selectedModelSelection) ? selectedModelSelection : selectedModelSelection
    && !catalogPending
    && !isModelSelectionAvailable(selectedModelSelection, models, selectableGroups)
    ? resolveAvailableModelSelection(selectedModelSelection, models, selectableGroups)
    : inferredSelection;
  const pickerSelection =
    singleAgent && collaborationEnabled && healedSelection?.type === 'model_group'
      ? { type: 'model_group' as const, id: healedSelection.id }
      : healedSelection;
  const hasSelectableGroup =
    includeModelGroups && selectableGroups.some((group) => group.enabled !== false && Boolean(group.model_group_id));
  if (!selected && !pickerSelection && models.length === 0 && !hasSelectableGroup && !singleAgent) return null;

  const rejectManagedSelection = (reason: string) => {
    setSelectionError(t(`chat.modelSelector.managedOpenCode.${reason}`));
    reportManagedOpenCodeRejection(reason);
  };

  const persistSelection = async (next: ModelSelection) => {
    if (selectedChildTeam) return;
    if (!boundSessionId || disabled || useChatStore.getState().getRuntime(boundSessionId)?.isProcessing) return;
    if (managed) {
      const reason = managedOpenCodeReason(managed, next);
      if (reason) {
        rejectManagedSelection(reason);
        return;
      }
    }
    setSelectionError('');
    const applySelection = () => {
      setSelectedModelSelection(boundSessionId, next);
      if (cloud.active) {
        const state = useSessionStore.getState(), runtime = state.runtimes[boundSessionId];
        if (runtime) useSessionStore.setState({ runtimes: { ...state.runtimes, [boundSessionId]: {
          ...runtime, selectedModelName: next.type === 'model' ? models.find(m => m.model_id === next.id)?.model_name ?? null : null,
        } } });
      }
    };
    const waitForSave = managed !== null && boundSessionId !== NEW_CONVERSATION_ID;
    if (!waitForSave) applySelection();
    if (boundSessionId === NEW_CONVERSATION_ID) return;
    if (waitForSave) setSaving(true);
    try {
      await webRequest('session.selection.set', {
        session_id: boundSessionId,
        model_selection: next,
      });
      if (waitForSave) applySelection();
    } catch (error) {
      setSelectionError(
        error instanceof Error && error.message ? error.message : t('chat.modelSelector.selectionFailed'),
      );
    } finally {
      if (waitForSave) setSaving(false);
    }
  };

  const savedReason = managed && selectedModelSelection && (
    managedOpenCodeReason(managed, selectedModelSelection)
    || (!isOpenCodeNativeModel(selectedModelSelection) && !models.some(model => model.model_id === selectedModelSelection.id)
      && !isModelCatalogPending(models, modelGroups) ? 'opencode_model_unavailable' : null)
  );
  const admissionError = selectionError || (managed?.error ? t(`chat.modelSelector.managedOpenCode.${managed.error}`) : '')
    || (savedReason ? t(`chat.modelSelector.managedOpenCode.${savedReason}`) : '') || (managed && !managed.default && !selectedModelSelection
    ? t('chat.modelSelector.managedOpenCode.opencode_default_model_unconfigured') : '');
  return (
    <div className="chat-model-selector" data-testid="chat-panel-model-selector-wrap">
      <ModelPicker
        catalog={cloud.active || managed ? { models, groups: modelGroups } : undefined}
        testIdPrefix="chat-panel-model-selector"
        value={selectedChildTeam?.execution_model_name ?? selected?.model_name ?? selectedModelName}
        selection={selectedChildTeam?.execution_model_selection ?? pickerSelection}
        includeModelGroups={includeModelGroups}
        modelRejection={managed ? (model) => {
          const reason = model.model_id ? managedOpenCodeReason(managed, { type: 'model', id: model.model_id })
            : 'opencode_model_not_registered';
          return reason ? {
            message: t(`chat.modelSelector.managedOpenCode.${reason}`),
            onSelect: () => rejectManagedSelection(reason),
          } : undefined;
        } : undefined}
        unavailableSelectionLabel={groupBlocked ? t('chat.modelSelector.selectOrdinaryModel')
          : managed && isOpenCodeNativeModel(pickerSelection) && pickerSelection?.id === managed.default?.id
            ? t('chat.modelSelector.managedOpenCode.default', { model: managed.default?.label })
            : preserveSelection && pickerSelection?.type === 'model' && !models.some(model => model.model_id === pickerSelection.id)
              ? pickerSelection.id : undefined}
        onChange={(modelName) => {
          if (selectedChildTeam) return;
          if (!boundSessionId || disabled || useChatStore.getState().getRuntime(boundSessionId)?.isProcessing) return;
          if (managed) {
            rejectManagedSelection('opencode_model_not_registered');
            return;
          }
          setSelectionError('');
          setSelectedModelName(boundSessionId, modelName);
        }}
        onSelectionChange={(next) => {
          void persistSelection(next);
        }}
        disabled={disabled || codexDevice || saving || Boolean(selectedChildTeam) || loadingOpenCode || (cloud.active && !cloud.catalog)}
        onAddModel={cloud.active ? undefined : openModelSettings}
      />
      {admissionError ? (
        <div className="chat-model-selector__error" role="alert" data-testid="chat-panel-model-selector-error">
          {admissionError}
        </div>
      ) : null}
    </div>
  );
}


export default function ChatModelSelector(props: { disabled?: boolean; sessionId?: string; allowModelGroups?: boolean }): JSX.Element {
  const activeSessionId = useChatStore((state) => state.activeSessionId);
  const sid = props.sessionId || activeSessionId || NEW_CONVERSATION_ID;
  const provider = useSessionStore((state) => state.runtimes[sid]?.executionProvider ?? 'harness');
  return (
    <div className="chat-model-selector" data-testid="chat-panel-execution-selection">
      <ConversationModelSelector {...props} allowModelGroups={provider === 'harness' && props.allowModelGroups !== false} />
    </div>
  );
}
