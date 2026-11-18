import { useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Dialog } from '../ui/Dialog/Dialog';
import { ProjectGitHubConnection, type GitHubRepositorySelection } from './ProjectGitHubConnection';
import { webClient } from '../../services/webClient';
import { onOrganizationCredentialChange } from '../../services/organizationCredentialEvents';
import { cloudProjectRequest } from '../../features/cloudWorkspace/projectEnvironmentClient';
import { onLocalCloudAccountChange } from '../../features/cloudWorkspace/localCloudAccountClient';
import { generateUuidV4 } from '../../utils/uuid';
import type { ProjectInfo } from '../../features/workspace/projectTypes';
import './CloudEnvironmentDialog.css';

/** Shared by desktop, local Web and cloud Web through the original composer. */
export function CloudEnvironmentDialog({
  open,
  mode,
  remote,
  onClose,
  onPrepared,
}: {
  open: boolean;
  mode: string;
  remote: boolean;
  onClose: () => void;
  onPrepared?: (project: ProjectInfo, target: string) => void;
}) {
  const { t } = useTranslation();
  const webRequest = <T,>(method: string, params: Record<string, unknown>) => cloudProjectRequest<T>(method, params, remote);
  const titleId = useId();
  const [name, setName] = useState('');
  const [provider, setProvider] = useState<'github' | 'gitcode'>('github');
  const operationKey = (selectedTarget: string) => `swarm.environment.operation.${selectedTarget}${provider === 'gitcode' ? '.gitcode' : ''}`;
  const providerParams = provider === 'gitcode' ? { provider } : {};
  const [draftId, setDraftId] = useState(() => `cloud-${generateUuidV4()}`);
  const [target, setTarget] = useState<string | null>(null);
  const [source, setSource] = useState<GitHubRepositorySelection | null>(null);
  const [state, setState] = useState('loading');
  const [retry, setRetry] = useState(0);
  type Preparation = {
    execution_target: string;
    operation_id: string;
    state: string;
    error?: string;
    project?: ProjectInfo;
    selection?: Record<string, unknown>;
  };
  const [preparation, setPreparation] = useState<Preparation | null>(null);
  const intent = useRef<Record<string, unknown> | null>(null);
  const [preparing, setPreparing] = useState(false);
  const generation = useRef(0);
  const openRef = useRef(open);
  openRef.current = open;
  const close = useRef(onClose);
  close.current = onClose;

  useEffect(() => {
    const invalidate = () => {
      generation.current += 1;
      setTarget(null);
      setSource(null);
      intent.current = null;
      setPreparation(null);
      setPreparing(false);
      setName('');
      setDraftId(`cloud-${generateUuidV4()}`);
      setState('notConnected');
      if (openRef.current) close.current();
    };
    const clearAccount = () => {
      for (const key of Object.keys(sessionStorage)) {
        if (key.startsWith('swarm.environment.operation.')) sessionStorage.removeItem(key);
      }
      invalidate();
    };
    const auth = onOrganizationCredentialChange(clearAccount);
    const localAuth = onLocalCloudAccountChange(clearAccount);
    const connection = webClient.onStateChange((next) => {
      if (next !== 'ready') invalidate();
    });
    return () => {
      generation.current += 1;
      auth();
      localAuth();
      connection();
    };
  }, []);

  useEffect(() => {
    setName('');
    setSource(null);
    intent.current = null;
    setPreparation(null);
    setDraftId(`cloud-${generateUuidV4()}`);
  }, [remote, mode]);

  useEffect(() => {
    const current = ++generation.current;
    setPreparing(false);
    setTarget(null);
    setSource(null);
    if (!open) return;
    setState('loading');
    void webRequest<{ execution_target: string }>(`project.${provider}.status`, {})
      .then((options) => {
        if (generation.current !== current) return;
        try {
          if (options.execution_target !== 'cloud') throw new Error('notConnected');
          const selectedTarget = 'cloud';
          setTarget(selectedTarget);
          setState('connected');
          const operation = sessionStorage.getItem(operationKey(selectedTarget));
          if (operation && /^[a-f0-9]{32}$/.test(operation)) {
            void webRequest<Preparation>('project.environment.status', {
              execution_target: selectedTarget,
              operation_id: operation,
              ...providerParams,
            })
              .then((result) => {
                if (generation.current !== current || result.execution_target !== selectedTarget) return;
                setPreparation(result);
                if (result.selection) {
                  intent.current = { execution_target: selectedTarget, operation_id: operation, ...providerParams, ...result.selection };
                  setName(String(result.selection.name));
                }
              })
              .catch(() => {
                /* Keep opaque ID for reconnect; it grants no authority. */
              });
          }
        } catch (error) {
          setState(error instanceof Error ? error.message : 'failed');
        }
      })
      .catch(() => {
        if (generation.current === current) setState('failed');
      });
    return () => {
      generation.current += 1;
    };
  }, [open, remote, mode, retry, provider]);

  const prepare = async () => {
    if (!target || preparing || (!source && !intent.current)) return;
    if (!intent.current && source)
      intent.current = {
        execution_target: target,
        operation_id: generateUuidV4().replace(/-/g, ''),
        name: name.trim(),
        account_id: source.accountId,
        repository_id: source.repository.id,
        branch: source.branch.name,
        ...(provider === 'gitcode' ? { provider, full_name: source.repository.full_name } : {}),
      };
    sessionStorage.setItem(operationKey(target), String(intent.current!.operation_id));
    const current = generation.current;
    setPreparing(true);
    try {
      const result = await webRequest<Preparation>('project.environment.prepare', intent.current!);
      if (generation.current === current && result.execution_target === target) setPreparation(result);
    } catch {
      if (generation.current === current)
        setPreparation({
          execution_target: target,
          operation_id: String(intent.current?.operation_id),
          state: 'interrupted',
        });
    } finally {
      if (generation.current === current) setPreparing(false);
    }
  };
  useEffect(() => {
    if (!open || !target || !preparation || ['ready', 'failed', 'interrupted'].includes(preparation.state)) return;
    const current = generation.current;
    const timer = window.setTimeout(() => {
      void webRequest<Preparation>('project.environment.status', {
        execution_target: target,
        operation_id: preparation.operation_id,
        ...providerParams,
      })
        .then((result) => {
          if (generation.current === current && result.execution_target === target) setPreparation(result);
        })
        .catch(() => {
          if (generation.current === current) setPreparation({ ...preparation, state: 'interrupted' });
        });
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [open, target, preparation, provider]);

  return (
    <Dialog
      open={open}
      titleId={titleId}
      onCancel={onClose}
      onBackdropClick={onClose}
      className="chat-cloud-environment"
    >
      <section data-testid="chat-panel-cloud-environment-dialog">
        <header className="chat-cloud-environment__header" data-testid="chat-panel-cloud-environment-header">
          <h2 id={titleId} data-testid="chat-panel-cloud-environment-title">
            {t('cloudEnvironment.create')}
          </h2>
          <button type="button" onClick={onClose} data-testid="chat-panel-cloud-environment-close">
            {t('cloudEnvironment.close')}
          </button>
        </header>
        <p data-testid="chat-panel-cloud-environment-description">{t('cloudEnvironment.description')}</p>
        <label data-testid="chat-panel-cloud-environment-provider-label">
          {t('cloudEnvironment.provider')}
          <select
            value={provider}
            disabled={preparing || Boolean(preparation)}
            data-testid="chat-panel-cloud-environment-provider"
            onChange={(event) => {
              const next = event.target.value;
              if (next !== 'github' && next !== 'gitcode') return;
              generation.current += 1;
              intent.current = null;
              setPreparation(null);
              setSource(null);
              setName('');
              setDraftId(`cloud-${generateUuidV4()}`);
              setProvider(next);
            }}
          >
            <option value="github" data-testid="chat-panel-cloud-environment-provider-option" data-variant="github">GitHub</option>
            <option value="gitcode" data-testid="chat-panel-cloud-environment-provider-option" data-variant="gitcode">GitCode</option>
          </select>
        </label>
        <div
          role="status"
          hidden={state === 'connected'}
          data-testid="chat-panel-cloud-environment-status"
          data-variant={state}
        >
          {t(`cloudEnvironment.state.${state}`, { defaultValue: t('cloudEnvironment.state.failed') })}
        </div>
        {!target ? (
          <button
            type="button"
            disabled={state === 'loading'}
            onClick={() => setRetry((n) => n + 1)}
            data-testid="chat-panel-cloud-environment-retry"
          >
            {t('cloudEnvironment.retry')}
          </button>
        ) : (
          <>
            {open && !preparation ? (
              <ProjectGitHubConnection
                key={`${provider}:${target}:${draftId}`}
                provider={provider}
                target={target}
                remote={remote}
                embedded
                draftId={draftId}
                onSelectionChange={(selection) => {
                  setSource(selection);
                  if (selection) setName((current) => current || selection.repository.full_name.split('/').pop() || '');
                }}
              />
            ) : null}
            {source ? (
              <>
                <label className="chat-cloud-environment__name" data-testid="chat-panel-cloud-environment-name-label">
                  {t('cloudEnvironment.name')}
                  <input
                    value={name}
                    disabled={Boolean(preparation) || preparing}
                    onChange={(event) => setName(event.target.value)}
                    maxLength={80}
                    data-testid="chat-panel-cloud-environment-name"
                    autoComplete="off"
                  />
                </label>

                <p data-testid="chat-panel-cloud-environment-source">
                  {source.repository.full_name} · {source.branch.name}
                </p>
              </>
            ) : null}
          </>
        )}
        <footer className="chat-cloud-environment__footer" data-testid="chat-panel-cloud-environment-footer">
          <div
            role="status"
            data-testid="chat-panel-cloud-environment-preparation"
            data-variant={preparation?.state ?? 'idle'}
          >
            {preparation
              ? t(`cloudEnvironment.preparation.${preparation.state}`, {
                  defaultValue: t('cloudEnvironment.preparation.failed'),
                })
              : t('cloudEnvironment.prepareScope')}
            {preparation?.error ? (
              <span data-testid="chat-panel-cloud-environment-error">
                {' '}{t(`cloudEnvironment.errorCode.${preparation.error}`, {
                  defaultValue: preparation.error,
                })}
              </span>
            ) : null}
          </div>
          <button type="button" onClick={onClose} data-testid="chat-panel-cloud-environment-cancel">
            {t(preparation ? 'cloudEnvironment.close' : 'cloudEnvironment.cancel')}
          </button>
          {preparation && ['failed', 'interrupted'].includes(preparation.state) ? (
            <button
              type="button"
              data-testid="chat-panel-cloud-environment-reselect"
              onClick={() => {
                sessionStorage.removeItem(operationKey(preparation.execution_target));
                intent.current = null;
                setPreparation(null);
                setSource(null);
                setDraftId(`cloud-${generateUuidV4()}`);
              }}
            >
              {t('cloudEnvironment.reselect')}
            </button>
          ) : null}
          {preparation?.state === 'ready' && preparation.project ? (
            <button
              type="button"
              onClick={() => {
                sessionStorage.removeItem(operationKey(preparation.execution_target));
                onPrepared?.(preparation.project!, preparation.execution_target);
                intent.current = null;
                setPreparation(null);
                setSource(null);
                setName('');
                setDraftId(`cloud-${generateUuidV4()}`);
                onClose();
              }}
              data-testid="chat-panel-cloud-environment-use"
            >
              {t('cloudEnvironment.use')}
            </button>
          ) : (
            <button
              type="button"
              disabled={
                preparing ||
                !target ||
                (!source && !intent.current) ||
                !name.trim() ||
                Boolean(preparation && !['failed', 'interrupted'].includes(preparation.state))
              }
              onClick={() => void prepare()}
              data-testid="chat-panel-cloud-environment-prepare"
            >
              {t(
                preparation && ['failed', 'interrupted'].includes(preparation.state)
                  ? 'cloudEnvironment.retryPrepare'
                  : 'cloudEnvironment.prepare',
              )}
            </button>
          )}
        </footer>
      </section>
    </Dialog>
  );
}
