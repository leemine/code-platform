// Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

import { useEffect, useRef, type Dispatch, type SetStateAction } from 'react';
import {
  EXTERNAL_CLI_AGENT_KINDS,
  externalCliDependencyInstalls,
  externalCliKey,
  type ExternalCliAgentKind,
  type ExternalCliConfigSaveResult,
  type ExternalCliPendingChoice,
} from '../../../../components/ExternalCliAgentsSection';
import type { ExternalCliInstallStatuses } from '../../../../components/ExternalCliInstallDialog';

type Choices = Partial<Record<ExternalCliAgentKind, ExternalCliPendingChoice>>;

/** Complete the existing deferred config save independently of Settings navigation. */
export function useExternalCliInstallCompletion({
  connected, choices, statuses, setChoices, save, onSaved, onError,
}: {
  connected: boolean;
  choices: Choices;
  statuses: ExternalCliInstallStatuses;
  setChoices: Dispatch<SetStateAction<Choices>>;
  save: (updates: Record<string, string>) => Promise<ExternalCliConfigSaveResult | void>;
  onSaved: () => void;
  onError: (message: string) => void;
}) {
  const inFlight = useRef(new Set<ExternalCliAgentKind>());
  const attempted = useRef(new Map<ExternalCliAgentKind, ExternalCliPendingChoice>());
  useEffect(() => {
    if (!connected) {
      attempted.current.clear();
      return;
    }
    for (const agent of EXTERNAL_CLI_AGENT_KINDS) {
      const pending = choices[agent];
      const status = statuses[agent]?.status;
      if (!pending || !['succeeded', 'failed'].includes(status ?? '')) continue;
      if (inFlight.current.has(agent)) continue;
      const clearPending = () => {
        attempted.current.delete(agent);
        setChoices((current) => {
          if (current[agent] !== pending) return current;
          const next = { ...current };
          delete next[agent];
          return next;
        });
      };
      if (status === 'failed') {
        clearPending();
        onError(statuses[agent]?.error || '');
        continue;
      }
      if (attempted.current.get(agent) === pending) continue;
      attempted.current.set(agent, pending);
      inFlight.current.add(agent);
      void (async () => {
        try {
          const result = await save({
            [externalCliKey(agent, 'enabled')]: pending.enabled,
            [externalCliKey(agent, 'use_builtin')]: pending.useBuiltin,
            [externalCliKey(agent, 'cli_path')]: pending.cliPath,
          });
          // A successful RPC may only have queued another dependency install.
          if (Object.keys(externalCliDependencyInstalls(result)).length) {
            throw new Error('');
          }
          clearPending();
          onSaved();
        } catch (error) {
          // Retain the choice for a reconnect or explicit user retry; never
          // claim persistence or spin an automatic config-save retry loop.
          onError(error instanceof Error ? error.message : String(error));
        } finally {
          inFlight.current.delete(agent);
          // A user may replace this choice while its previous save is in flight.
          setChoices((current) => current[agent] && current[agent] !== pending ? { ...current } : current);
        }
      })();
    }
  }, [choices, connected, onError, onSaved, save, setChoices, statuses]);
}
