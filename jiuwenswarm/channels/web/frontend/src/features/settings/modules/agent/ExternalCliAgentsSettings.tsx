// Copyright (c) Huawei Technologies Co., Ltd. 2025-2026. All rights reserved.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  EXTERNAL_CLI_AGENT_KINDS,
  ExternalCliAgentsSection,
  applyExternalCliAgentAtomicUpdates,
  externalCliDependencyInstalls,
  externalCliSaveValidationMessage,
  externalCliKey,
  parseExternalCliPathHistories,
  type ExternalCliAgentChoice,
  type ExternalCliAgentKind,
  type ExternalCliConfigSaveResult,
} from '../../../../components/ExternalCliAgentsSection';
import type { SettingsCustomItemProps } from '../../registry/types';
import { parseConfigBoolean } from '../../services/settingsContract';
import { useSettingsServices } from '../../services/SettingsServicesProvider';
import { useSettingsSource } from '../../services/SettingsSourceProvider';
import { useUnsavedChanges } from '../../services/useUnsavedChanges';
import { applyExternalCliPendingChoices, hasUnsavedExternalCliChanges } from './externalCliInstallState';

function externalCliDefaults(agents: ExternalCliAgentKind[]): Record<string, string> {
  return Object.fromEntries(
    agents.flatMap((agent) => [
      [externalCliKey(agent, 'enabled'), 'false'],
      [externalCliKey(agent, 'use_builtin'), 'false'],
      [externalCliKey(agent, 'cli_path'), ''],
      [externalCliKey(agent, 'path_histories'), '[]'],
    ]),
  );
}

/** Auto-dismiss both the save-failure banner and the auto-save success notice after this delay. */
const NOTICE_AUTO_DISMISS_MS = 8000;

/** Mirrors EXTERNAL_CLI_PATH_HISTORY_LIMIT on the backend (config.py). */
const EXTERNAL_CLI_PATH_HISTORY_LIMIT = 10;

function ExternalCliSettings({
  config,
  onConfigPatch,
  onSave,
  inheritedDisabled,
}: {
  config: Record<string, unknown>;
  onConfigPatch: (updates: Record<string, unknown>) => void;
  onSave: (values: Record<string, string>) => Promise<ExternalCliConfigSaveResult | void>;
  inheritedDisabled: boolean;
}) {
  const { t } = useTranslation();
  const {
    isConnected,
    externalCliInstallStatuses,
    externalCliPendingChoices,
    externalCliDetectResults,
    onDetectExternalCli,
    onExternalCliPendingChoicesChange,
    onExternalCliDetectResultsChange,
    onGetExternalCliInstallStatus,
    onExternalCliInstallStatusChange,
    onSelectExternalCliPath,
    onValidateExternalCliPaths,
    onPruneExternalCliPathHistories,
    onTrackExternalCliDependencyInstalls,
  } = useSettingsServices();
  const sourceValues = useMemo(
    () =>
      Object.fromEntries(
        Object.entries(externalCliDefaults(EXTERNAL_CLI_AGENT_KINDS)).map(([key, fallback]) => [
          key,
          String(config[key] ?? fallback),
        ]),
      ),
    [config],
  );
  // User choices deferred behind a dependency install. Held at the App layer
  // and session storage so they survive navigation and full page refreshes.
  const pendingChoices = externalCliPendingChoices ?? {};
  const setPendingChoices = onExternalCliPendingChoicesChange;
  const restoredDraftValues = useMemo(
    () => applyExternalCliPendingChoices(sourceValues, pendingChoices),
    [pendingChoices, sourceValues],
  );
  const [savedValues, setSavedValues] = useState(sourceValues);
  const [draftValues, setDraftValues] = useState(restoredDraftValues);
  const [saveError, setSaveError] = useState('');
  const [autoSavedAgents, setAutoSavedAgents] = useState<string[]>([]);
  // Latest CLI detect results, held at the App layer (via services) so they
  // survive unmounting the Settings page; the save flow pre-validates them to
  // surface a localized error instead of the backend's raw English message.
  // Memoized so identity only changes when the App-layer result object does.
  const detectResults = useMemo(() => externalCliDetectResults ?? {}, [externalCliDetectResults]);
  const setDetectResults = onExternalCliDetectResultsChange;
  const changed = hasUnsavedExternalCliChanges(
    savedValues,
    draftValues,
    pendingChoices,
    externalCliInstallStatuses,
  );
  useEffect(() => {
    if (!saveError) return undefined;
    const timer = window.setTimeout(() => setSaveError(''), NOTICE_AUTO_DISMISS_MS);
    return () => window.clearTimeout(timer);
  }, [saveError]);
  // Installs are per-agent: only the installing agent's card is disabled (the
  // section disables it), so the other agent stays installable in parallel.
  // Card-level saves do not lock the panel either: the saving card shows its
  // own busy state, and concurrent saves only ever merge their own keys into
  // savedValues functionally (persistUpdates), so they cannot clobber each
  // other and no global lock is needed.
  const disabled = inheritedDisabled || !isConnected;
  useUnsavedChanges('external-cli', changed);

  useEffect(() => {
    if (!changed) {
      setSavedValues(sourceValues);
      setDraftValues(restoredDraftValues);
    }
  }, [changed, restoredDraftValues, sourceValues]);

  // After a successful detection, drop stale addresses from the persisted
  // Prunes stale entries from the persisted path history: the persisted
  // cli_path and the just-detected path count as known-good, everything
  // else is checked on disk via external_cli.validate_paths. The actual
  // drop happens server-side (external_cli.prune_path_histories) against
  // the on-disk history, so entries appended by a concurrent save — e.g.
  // the just-replaced cli_path — can never be rolled back by this
  // component's snapshot.
  const cleanupPersistedPathHistories = useCallback(
    async (
      cliAgent: ExternalCliAgentKind,
      detectedPath: string,
      options?: { effectivePath?: string },
    ) => {
      if (!onValidateExternalCliPaths || !onPruneExternalCliPathHistories) return;
      const historyKey = externalCliKey(cliAgent, 'path_histories');
      const effectivePath = (options?.effectivePath ?? savedValues[externalCliKey(cliAgent, 'cli_path')] ?? '').trim();
      const histories = parseExternalCliPathHistories(savedValues[historyKey]);
      if (!histories.length) return;
      const knownGood = [effectivePath, detectedPath].filter(Boolean);
      let results: Record<string, boolean | null>;
      try {
        results = await onValidateExternalCliPaths([...new Set([...histories, ...knownGood])]);
      } catch {
        return; // Validation unavailable: keep the history untouched.
      }
      // Only a confirmed miss is handed to the backend: an unreadable path
      // (null) or one the backend could not answer stays put. The server
      // drops only the intersection with the on-disk history, so anything
      // appended after this snapshot was taken survives.
      const removePaths = histories.filter((path) => !knownGood.includes(path) && results[path] === false);
      if (!removePaths.length) return;
      let next: string[];
      try {
        // Adopt the server's survivors: the prune ran against the on-disk
        // history, so this also picks up entries a concurrent save appended
        // after this component's snapshot was taken.
        next = await onPruneExternalCliPathHistories(cliAgent, removePaths);
      } catch {
        return; // The next explicit action retries the cleanup.
      }
      const updates = { [historyKey]: JSON.stringify(next) };
      setSavedValues((current) => ({ ...current, ...updates }));
      setDraftValues((current) => ({ ...current, ...updates }));
      onConfigPatch(updates);
    },
    [onConfigPatch, onPruneExternalCliPathHistories, onValidateExternalCliPaths, savedValues],
  );

  // On first load, sweep every agent's persisted path history: entries that
  // no longer exist on disk are pruned server-side so the path dropdown does
  // not offer stale addresses. This must not depend on detection results —
  // the saved path itself may be the dead one, in which case detection fails
  // and the detection-gated cleanup never fires. Runs once per mount, after
  // saved values first become available.
  const initialHistorySweepDoneRef = useRef(false);
  useEffect(() => {
    if (initialHistorySweepDoneRef.current) return;
    if (!onValidateExternalCliPaths || !onPruneExternalCliPathHistories) return;
    const pendingAgents = EXTERNAL_CLI_AGENT_KINDS.filter(
      (agent) => parseExternalCliPathHistories(savedValues[externalCliKey(agent, 'path_histories')]).length > 0,
    );
    if (!pendingAgents.length) return; // Saved values not loaded yet: retry on the next render.
    initialHistorySweepDoneRef.current = true;
    for (const agent of pendingAgents) {
      // Empty detectedPath: only the persisted cli_path counts as known-good.
      void cleanupPersistedPathHistories(agent, '');
    }
  }, [cleanupPersistedPathHistories, onPruneExternalCliPathHistories, onValidateExternalCliPaths, savedValues]);

  // App completes the deferred save even while this page is unmounted.
  // Adopt confirmed drafts, and roll back a failed install's optimistic choice.
  useEffect(() => {
    const confirmed = EXTERNAL_CLI_AGENT_KINDS.filter((agent) => {
      const keys = (['enabled', 'use_builtin', 'cli_path'] as const).map((suffix) => externalCliKey(agent, suffix));
      return keys.every((key) => sourceValues[key] === draftValues[key])
        && keys.some((key) => sourceValues[key] !== savedValues[key]);
    });
    const failed = EXTERNAL_CLI_AGENT_KINDS.filter((agent) =>
      !pendingChoices[agent] && externalCliInstallStatuses?.[agent]?.status === 'failed'
      && (['enabled', 'use_builtin', 'cli_path'] as const).some((suffix) => {
        const key = externalCliKey(agent, suffix);
        return draftValues[key] !== sourceValues[key];
      }),
    );
    if (!confirmed.length && !failed.length) return;
    const patch = Object.fromEntries([...confirmed, ...failed].flatMap((agent) =>
      (['enabled', 'use_builtin', 'cli_path'] as const).map((suffix) => {
        const key = externalCliKey(agent, suffix);
        return [key, sourceValues[key]];
      }),
    ));
    setSavedValues((current) => ({ ...current, ...patch }));
    if (failed.length) setDraftValues((current) => ({ ...current, ...patch }));
    if (confirmed.length) setAutoSavedAgents(confirmed);
  }, [draftValues, externalCliInstallStatuses, pendingChoices, savedValues, sourceValues]);
  useEffect(() => {
    if (!autoSavedAgents.length) return undefined;
    const timer = window.setTimeout(() => setAutoSavedAgents([]), NOTICE_AUTO_DISMISS_MS);
    return () => window.clearTimeout(timer);
  }, [autoSavedAgents]);

  // Persists one batch of agent updates on behalf of a card-level commit.
  // Errors are rethrown so the calling card can surface them in its own
  // message row instead of the global banner.
  const persistUpdates = useCallback(
    async (
      updates: Record<string, string>,
      effectiveDrafts: Record<string, string>,
      skipValidationFor?: ExternalCliAgentKind,
    ) => {
      // Pre-validate against the latest detect results: fail fast with a
      // localized message before the backend rejects with its raw English error.
      for (const agent of EXTERNAL_CLI_AGENT_KINDS) {
        if (agent === skipValidationFor) continue;
        const validation = externalCliSaveValidationMessage(agent, effectiveDrafts, detectResults[agent], t);
        if (validation) throw new Error(validation);
      }
      const result = await onSave(updates);
      const installs = externalCliDependencyInstalls(result);
      const deferredAgents = EXTERNAL_CLI_AGENT_KINDS.filter(
        (agent) => installs[agent]?.status === 'running',
      );
      // An explicit, confirmed card save supersedes any older deferred choice.
      // Retaining it would replay the old path after the next reconnect.
      const confirmedAgents = EXTERNAL_CLI_AGENT_KINDS.filter((agent) =>
        !installs[agent] && Object.keys(updates).some((key) => key.startsWith(`external_cli_agent_${agent}_`)),
      );
      if (confirmedAgents.length) setPendingChoices?.((current) => {
        const next = { ...current };
        for (const agent of confirmedAgents) delete next[agent];
        return next;
      });
      // The backend skips persisting agents whose dependency is still
      // installing. Keep the user's choices in the form (so the cards stay as
      // chosen) and remember them for an automatic re-save once it succeeds.
      if (deferredAgents.length) {
        setPendingChoices?.((current) => {
          const next: typeof current = { ...current };
          for (const agent of deferredAgents) {
            next[agent] = {
              enabled: effectiveDrafts[externalCliKey(agent, 'enabled')] === 'true' ? 'true' : 'false',
              useBuiltin: effectiveDrafts[externalCliKey(agent, 'use_builtin')] === 'true' ? 'true' : 'false',
              cliPath: (effectiveDrafts[externalCliKey(agent, 'cli_path')] ?? '').trim(),
            };
          }
          return next;
        });
      }
      if (Object.keys(installs).length) onTrackExternalCliDependencyInstalls?.(installs);
      // Deferred agents are not persisted yet: align savedValues and the config
      // store with what the backend actually stored (agent disabled), while
      // draftValues keeps the user's selection visible until the automatic
      // re-save completes.
      const savedPatch: Record<string, string> = {};
      const configPatch: Record<string, string> = {};
      for (const agent of deferredAgents) {
        savedPatch[externalCliKey(agent, 'enabled')] = 'false';
        savedPatch[externalCliKey(agent, 'use_builtin')] = 'false';
        savedPatch[externalCliKey(agent, 'cli_path')] = '';
        configPatch[externalCliKey(agent, 'enabled')] = 'false';
        configPatch[externalCliKey(agent, 'use_builtin')] = 'false';
        configPatch[externalCliKey(agent, 'cli_path')] = '';
      }
      // Non-deferred updates were persisted verbatim: keep savedValues,
      // draftValues, and the config store in lockstep so `changed` clears.
      const isDeferredKey = (key: string) =>
        deferredAgents.some((agent) => key.startsWith(`external_cli_agent_${agent}_`));
      for (const [key, value] of Object.entries(updates)) {
        if (isDeferredKey(key)) continue;
        savedPatch[key] = value;
        configPatch[key] = value;
      }
      // Mirror the backend's history append locally: when a save replaces one
      // agent's cli_path, the previous effective path joins the path history
      // so the dropdown offers it immediately instead of only after the next
      // config reload. Deferred agents are skipped because the backend has
      // not stored their entry yet; the replay save appends server-side.
      const historyPatch: Record<string, string> = {};
      for (const agent of EXTERNAL_CLI_AGENT_KINDS) {
        if (deferredAgents.includes(agent)) continue;
        const pathKey = externalCliKey(agent, 'cli_path');
        if (!(pathKey in updates)) continue;
        const oldPath = (savedValues[pathKey] ?? '').trim();
        const newPath = (updates[pathKey] ?? '').trim();
        // Switching to the built-in CLI writes an empty path; the replaced
        // custom path must still join the local history.
        if (!oldPath || oldPath === newPath) continue;
        const historyKey = externalCliKey(agent, 'path_histories');
        const history = parseExternalCliPathHistories(savedValues[historyKey]);
        if (history.includes(oldPath)) continue;
        historyPatch[historyKey] = JSON.stringify(
          [...history, oldPath].slice(-EXTERNAL_CLI_PATH_HISTORY_LIMIT),
        );
      }
      for (const [key, value] of Object.entries(historyPatch)) {
        savedPatch[key] = value;
        configPatch[key] = value;
      }
      // Merge functionally: card-level saves run per agent and can overlap, so
      // each settled save only adds its own keys on top of the latest state —
      // spreading a captured snapshot would clobber the other agent's merge.
      setSavedValues((current) => ({ ...current, ...savedPatch }));
      // draftValues keeps deferred agents' user selections; everything else
      // mirrors what was persisted (including the values the atomic updater
      // produced, e.g. the preserved mode/path on disable).
      setDraftValues((current) => {
        const next = { ...current };
        for (const [key, value] of Object.entries(updates)) {
          if (isDeferredKey(key)) continue;
          next[key] = value;
        }
        for (const [key, value] of Object.entries(historyPatch)) {
          next[key] = value;
        }
        return next;
      });
      if (Object.keys(configPatch).length) onConfigPatch(configPatch);
    },
    [
      detectResults,
      onConfigPatch,
      onSave,
      onTrackExternalCliDependencyInstalls,
      setPendingChoices,
      savedValues,
      t,
    ],
  );

  // Card-level commit from ExternalCliAgentsSection: persists one agent's
  // choice (install / path selection / manual path save / enable switch)
  // immediately. Memoized so the card's callbacks (and their effect deps)
  // stay stable across renders.
  const commitAgentChoice = useCallback(
    async (cliAgent: ExternalCliAgentKind, choice: ExternalCliAgentChoice) => {
      // Install progress is rendered inline above the cards, so a click while
      // this agent's install is running is simply ignored. Other agents stay
      // usable: installs are per-agent (per-agent locks on the backend).
      if (externalCliInstallStatuses?.[cliAgent]?.status === 'running') return;
      const effectiveDrafts: Record<string, string> = {
        ...draftValues,
        [externalCliKey(cliAgent, 'enabled')]: choice.enabled ? 'true' : 'false',
        [externalCliKey(cliAgent, 'use_builtin')]: choice.useBuiltin ? 'true' : 'false',
        [externalCliKey(cliAgent, 'cli_path')]: choice.cliPath,
      };
      const updates: Record<string, string> = {};
      applyExternalCliAgentAtomicUpdates(updates, cliAgent, effectiveDrafts, savedValues);
      if (!Object.keys(updates).length) {
        if (!choice.force) return;
        // An install click must always produce a payload: the backend only
        // checks/repairs the dependency when this save carries the agent's
        // keys, and the choice can legitimately match the persisted state
        // (e.g. the built-in CLI was deleted and the card shows 未安装).
        updates[externalCliKey(cliAgent, 'enabled')] = choice.enabled ? 'true' : 'false';
        updates[externalCliKey(cliAgent, 'use_builtin')] = choice.useBuiltin ? 'true' : 'false';
        updates[externalCliKey(cliAgent, 'cli_path')] = choice.cliPath;
      }
      // The card pre-validated this agent's path with a probe detect call, so
      // the persisted validation loop skips it here.
      await persistUpdates(updates, effectiveDrafts, cliAgent);
    },
    [draftValues, externalCliInstallStatuses, persistUpdates, savedValues],
  );

  if (config.external_cli_agents_supported !== undefined && !parseConfigBoolean(config.external_cli_agents_supported))
    return null;
  return (
    <div className="settings-experimental-cli" data-testid="settings-experimental-cli">
      {autoSavedAgents.length ? (
        <div className="settings-experimental-cli__install-running settings-experimental-cli__install-running--success" role="status">
          {t('config.externalCli.autoSaved', {
            agents: autoSavedAgents.map((agent) => agent === 'claude' ? 'Claude' : 'Codex').join(' / '),
          })}
        </div>
      ) : null}
      {saveError ? (
        <div className="settings-page__error" role="alert" data-testid="settings-experimental-cli-error">
          {saveError}
        </div>
      ) : null}
      <ExternalCliAgentsSection
        draftValues={draftValues}
        onChange={(key, value) => {
          setDraftValues((current) => ({ ...current, [key]: value }));
          setSaveError('');
        }}
        onDetect={onDetectExternalCli}
        onCommitAgent={commitAgentChoice}
        onCleanupPathHistories={cleanupPersistedPathHistories}
        onSelectFile={onSelectExternalCliPath}
        initialResults={detectResults}
        onResultsChange={setDetectResults}
        installStatuses={externalCliInstallStatuses ?? {}}
        onInstallStatusGet={onGetExternalCliInstallStatus}
        onInstallStatusChange={onExternalCliInstallStatusChange}
        t={t}
        disabled={disabled}
      />
    </div>
  );
}

export function ExternalCliSettingsItem({ disabled }: SettingsCustomItemProps) {
  const source = useSettingsSource();
  return (
    <ExternalCliSettings
      config={source.values}
      inheritedDisabled={disabled}
      onConfigPatch={source.patchLocal}
      onSave={(updates) => source.save(updates, 'external-cli-agents') as Promise<ExternalCliConfigSaveResult | void>}
    />
  );
}
