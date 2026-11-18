import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { webClient } from '../../services/webClient';
import { cloudProjectRequest } from '../../features/cloudWorkspace/projectEnvironmentClient';
import { onLocalCloudAccountChange } from '../../features/cloudWorkspace/localCloudAccountClient';
import { generateUuidV4 } from '../../utils/uuid';
import { onOrganizationCredentialChange } from '../../services/organizationCredentialEvents';

type DeviceGrant = {
  attempt_id: string;
  user_code: string;
  verification_uri: string;
  expires_at: number;
  retry_after: number;
};
type Status = {
  configured: boolean;
  state: string;
  login?: string;
  can_import: boolean;
  device?: DeviceGrant | null;
  reason?: string;
};
type Account = { id: number | string; account: string };
type Repository = { id: number; full_name: string; default_branch: string };
type Branch = { name: string; commit: string };
type Page<T> = { items: T[]; has_more: boolean };
const GITCODE_TOKEN_URL = 'https://gitcode.com/setting/token-classic/create';

function validateDevice(value: DeviceGrant): DeviceGrant {
  if (
    !value ||
    !/^[a-f0-9]{32}$/.test(value.attempt_id) ||
    !/^[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(value.user_code) ||
    value.verification_uri !== 'https://github.com/login/device' ||
    !Number.isFinite(value.expires_at) ||
    !Number.isFinite(value.retry_after) ||
    value.retry_after < 1 ||
    value.retry_after > 3600
  )
    throw new Error('invalid device grant');
  return value;
}

export type GitHubRepositorySelection = { accountId: number | string; repository: Repository; branch: Branch };

/** A lazy section in the original project menu. No Session creation or input. */
export function ProjectGitHubConnection({
  target,
  remote,
  embedded = false,
  provider = 'github',
  draftId,
  onSelectionChange,
}: {
  target: string;
  remote: boolean;
  embedded?: boolean;
  provider?: 'github' | 'gitcode';
  draftId?: string;
  onSelectionChange?: (source: GitHubRepositorySelection | null) => void;
}) {
  const { t } = useTranslation();
  const label = (key: string, options: Record<string, unknown> = {}) => t(`${provider === 'gitcode' ? 'projectGitCode' : 'projectGitHub'}.${key}`, options);
  const [token, setToken] = useState('');
  const [tokenPrompt, setTokenPrompt] = useState(false);
  const [open, setOpen] = useState(false);
  const [selectedBranch, setSelectedBranch] = useState<string | null>(null);
  const ownDraftId = useRef(`draft-${generateUuidV4()}`);
  const selectionChanged = useRef(onSelectionChange);
  selectionChanged.current = onSelectionChange;
  const [status, setStatus] = useState<Status | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [authorization, setAuthorization] = useState('');
  const [chromeOpenFailed, setChromeOpenFailed] = useState(false);
  const isElectron = window.jiuwenDesktop?.isElectron === true;
  const [device, setDevice] = useState<DeviceGrant | null>(null);
  const [accounts, setAccounts] = useState<Page<Account>>({ items: [], has_more: false });
  const [accountPage, setAccountPage] = useState(1);
  const [account, setAccount] = useState<number | string | null>(null);
  const [repositories, setRepositories] = useState<Page<Repository>>({ items: [], has_more: false });
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [repository, setRepository] = useState<Repository | null>(null);
  const [branches, setBranches] = useState<Page<Branch>>({ items: [], has_more: false });
  const [branchPage, setBranchPage] = useState(1);
  const [branchPickerOpen, setBranchPickerOpen] = useState(false);
  const generation = useRef(0);
  const inFlight = useRef(false);
  useEffect(() => {
    const invalidate = () => {
      generation.current += 1;
      inFlight.current = false;
      setOpen(false);
      setBusy(false);
      setFailed(false);
      setStatus(null);
      setToken('');
      setTokenPrompt(false);
      setAuthorization('');
      setChromeOpenFailed(false);
      setDevice(null);
      clearCatalog();
    };
    invalidate();
    if (embedded) void refresh();
    const offAuth = onOrganizationCredentialChange(invalidate);
    const offLocalAuth = onLocalCloudAccountChange(invalidate);
    const offConnection = webClient.onStateChange((state) => {
      if (state !== 'ready') invalidate();
    });
    return () => {
      generation.current += 1;
      offAuth();
      offLocalAuth();
      offConnection();
    };
  }, [target, embedded, draftId, provider]);

  const request = async <T,>(action: string, params: Record<string, unknown> = {}) => {
    const result = await cloudProjectRequest<T & { execution_target: string }>(
      `project.${provider}.${action}`,
      {
        execution_target: target,
        ...params,
      },
      remote,
    );
    if (result.execution_target !== target) throw new Error('target changed');
    return result;
  };
  const run = async (action: (current: () => boolean) => Promise<void>) => {
    if (inFlight.current) return;
    inFlight.current = true;
    const current = ++generation.current;
    setBusy(true);
    setFailed(false);
    try {
      await action(() => generation.current === current);
    } catch {
      if (generation.current === current) setFailed(true);
    } finally {
      if (generation.current === current) {
        inFlight.current = false;
        setBusy(false);
      }
    }
  };
  const clearSelection = () => {
    setSelectedBranch(null);
    setBranchPickerOpen(false);
    selectionChanged.current?.(null);
  };
  const clearCatalog = () => {
    clearSelection();
    setAccounts({ items: [], has_more: false });
    setAccount(null);
    setRepositories({ items: [], has_more: false });
    setRepository(null);
    setBranches({ items: [], has_more: false });
    setSearch('');
  };
  const refresh = () =>
    run(async (current) => {
      clearCatalog();
      setAuthorization('');
      setDevice(null);
      setStatus(null);
      const next = await request<Status>('status');
      if (!current()) return;
      setStatus(next);
      if (next.state === 'pending' && next.device) {
        setDevice(validateDevice(next.device));
        setAuthorization(next.device.verification_uri);
      }
      if (next.state === 'connected') {
        const values = await request<Page<Account>>('accounts', { page: 1 });
        if (current()) {
          setAccounts(values);
          setAccountPage(1);
        }
      }
    });
  const readRepositories = (id: number | string, nextPage: number) =>
    run(async (current) => {
      clearSelection();
      setRepository(null);
      setBranches({ items: [], has_more: false });
      setRepositories({ items: [], has_more: false });
      const values = await request<Page<Repository>>('repositories', { account_id: id, page: nextPage });
      if (current()) {
        setAccount(id);
        setPage(nextPage);
        setRepositories(values);
      }
    });
  const selectRepository = (selected: Repository) =>
    run(async (current) => {
      clearSelection();
      setBranches({ items: [], has_more: false });
      setRepository(selected);
      const resolved = await request<{ branch: Branch }>('resolve', {
        account_id: account,
        repository_id: selected.id,
        ...(provider === 'gitcode' ? { full_name: selected.full_name } : {}),
      });
      if (!current()) return;
      let values: Page<Branch> = { items: [resolved.branch], has_more: false };
      if (!embedded) {
        values = await request<Page<Branch>>('branches', {
          account_id: account,
          repository_id: selected.id,
        ...(provider === 'gitcode' ? { full_name: selected.full_name } : {}),
          page,
          ref_page: 1,
        });
        if (!current()) return;
        if (!values.items.some((item) => item.name === resolved.branch.name)) values.items.unshift(resolved.branch);
      }
      setSelectedBranch(resolved.branch.name);
      setBranches(values);
      setBranchPage(1);
      if (account)
        selectionChanged.current?.(status?.can_import ? { accountId: account, repository: selected, branch: resolved.branch } : null);
    });
  const readBranches = (selected: Repository, nextPage: number) =>
    run(async (current) => {
      const values = await request<Page<Branch>>('branches', {
        account_id: account,
        repository_id: selected.id,
        ...(provider === 'gitcode' ? { full_name: selected.full_name } : {}),
        page,
        ref_page: nextPage,
      });
      if (!current()) return;
      const chosen = branches.items.find((item) => item.name === selectedBranch);
      if (chosen && !values.items.some((item) => item.name === chosen.name)) values.items.unshift(chosen);
      if (current()) {
        setBranches(values);
        setBranchPage(nextPage);
      }
    });
  const openInChrome = async () => {
    const current = generation.current;
    setChromeOpenFailed(false);
    try {
      if (await window.jiuwenDesktop?.openRepositoryAuthorization?.(provider)) return;
    } catch {
      // Keep the official link available to open manually.
    }
    if (current === generation.current) setChromeOpenFailed(true);
  };
  useEffect(() => {
    if ((!open && !embedded) || status?.state !== 'pending' || !device || busy || failed) return;
    const timer = window.setTimeout(() => {
      void run(async (current) => {
        const next = await request<{ state: string; retry_after?: number; reason?: string }>('poll', {
          attempt_id: device.attempt_id,
        });
        if (!current()) return;
        if (next.state === 'pending') {
          setDevice(validateDevice({ ...device, retry_after: next.retry_after ?? device.retry_after }));
          return;
        }
        setDevice(null);
        setAuthorization('');
        setStatus({ ...status, state: next.state, reason: next.reason });
        if (next.state === 'connected') {
          const updated = await request<Status>('status');
          if (!current()) return;
          setStatus(updated);
          if (updated.state !== 'connected') return;
          const values = await request<Page<Account>>('accounts', { page: 1 });
          if (current()) {
            setAccounts(values);
            setAccountPage(1);
          }
        }
      });
    }, device.retry_after * 1000);
    return () => window.clearTimeout(timer);
  }, [open, embedded, status, device, busy, failed]);
  return (
    <div className="chat-project-environment" data-testid={`chat-panel-project-${provider}`}>
      {!embedded ? (
        <button
          type="button"
          className="chat-work-select__option"
          data-testid={`chat-panel-project-${provider}-toggle`}
          aria-expanded={open}
          disabled={busy}
          onClick={() => {
            setOpen(!open);
            if (!open) void refresh();
          }}
        >
          {label('title')}
        </button>
      ) : null}
      {open || embedded ? (
        <div className="chat-project-github__body" data-testid={`chat-panel-project-${provider}-body`}>
          <div role="status" data-testid={`chat-panel-project-${provider}-status`}>
            {busy && !device
              ? label('loading')
              : failed
                ? label('failed')
                : status?.configured
                  ? `${t(device ? 'projectGitHub.devicePending' : `projectGitHub.state.${status.state}`, { defaultValue: t('projectGitHub.state.disconnected') })} ${status.login || ''}`
                  : label('unconfigured')}
          </div>
          {status?.state === 'connected' && !status.can_import ? (
            <p data-testid={`chat-panel-project-${provider}-import-unavailable`}>{label('importUnavailable')}</p>
          ) : null}
          <details
            className="chat-project-github__connection"
            open={!embedded || status?.state !== 'connected'}
            data-testid={`chat-panel-project-${provider}-management`}
          >
            <summary
              hidden={embedded && status?.state !== 'connected'}
              data-testid={`chat-panel-project-${provider}-management-toggle`}
            >
              {label('manageConnection')}
            </summary>
            <button
              type="button"
              disabled={busy}
              onClick={() => void refresh()}
              hidden={embedded && !failed && status?.state !== 'connected'}
              data-testid={`chat-panel-project-${provider}-refresh`}
            >
              {label('refresh')}
            </button>
            {status?.configured ? (
              <>
                <button
                  type="button"
                  disabled={busy || !!device}
                  data-testid={`chat-panel-project-${provider}-connect`}
                  onClick={() => {
                    if (provider === 'gitcode') {
                      clearCatalog();
                      setToken('');
                      setTokenPrompt(true);
                      setAuthorization(GITCODE_TOKEN_URL);
                      if (isElectron) void openInChrome();
                      else window.open(GITCODE_TOKEN_URL, '_blank', 'noopener,noreferrer');
                      return;
                    }
                    void run(async (current) => {
                      clearCatalog();
                      setAuthorization('');
                      setChromeOpenFailed(false);
                      setDevice(null);
                      const next = await request<{ flow: string; device: DeviceGrant }>(
                        'begin',
                        {
                          draft_id: draftId ?? ownDraftId.current,
                        },
                      );
                      if (next.flow !== 'device') throw new Error('invalid authorization flow');
                      const grant = validateDevice(next.device);
                      if (current()) {
                        setDevice(grant);
                        setAuthorization(grant.verification_uri);
                        setStatus({ ...status, state: 'pending', reason: undefined });
                      }
                    });
                  }}
                >
                  {label('connect')}
                </button>
                {provider === 'gitcode' && tokenPrompt ? (
                  <form
                    data-testid="chat-panel-project-gitcode-token-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      if (busy || !token.trim()) return;
                      const submitted = token.trim();
                      setToken('');
                      void run(async (current) => {
                        clearCatalog();
                        await request('connect', { access_token: submitted });
                        if (!current()) return;
                        const next = await request<Status>('status');
                        if (!current()) return;
                        setStatus(next);
                        setTokenPrompt(false);
                        setAuthorization('');
                        const values = await request<Page<Account>>('accounts', { page: 1 });
                        if (current()) {
                          setAccounts(values);
                          setAccountPage(1);
                        }
                      });
                    }}
                  >
                    <p data-testid="chat-panel-project-gitcode-token-instructions">{label('tokenInstructions')}</p>
                    <label data-testid="chat-panel-project-gitcode-token-label">
                      {label('token')}
                      <input
                        type="password"
                        value={token}
                        onChange={(event) => setToken(event.target.value)}
                        autoComplete="off"
                        spellCheck={false}
                        maxLength={4096}
                        disabled={busy}
                        data-testid="chat-panel-project-gitcode-token"
                      />
                    </label>
                    <button type="submit" disabled={busy || !token.trim()} data-testid="chat-panel-project-gitcode-token-submit">
                      {label('confirmConnection')}
                    </button>
                  </form>
                ) : null}
                {device ? (
                  <div data-testid={`chat-panel-project-${provider}-device`}>
                    <p data-testid={`chat-panel-project-${provider}-device-instructions`}>
                      {label('deviceInstructions')}
                    </p>
                    <strong data-testid={`chat-panel-project-${provider}-device-code`}>{device.user_code}</strong>
                    <p data-testid={`chat-panel-project-${provider}-device-waiting`}>{label('deviceWaiting')}</p>
                  </div>
                ) : null}
                {status.reason ? (
                  <p data-testid={`chat-panel-project-${provider}-device-reason`}>
                    {t(`projectGitHub.deviceReason.${status.reason}`, { defaultValue: label('failed') })}
                  </p>
                ) : null}
                {authorization ? (
                  <a
                    href={authorization}
                    target="_blank"
                    rel="noopener noreferrer"
                    data-testid={`chat-panel-project-${provider}-authorize`}
                    onClick={isElectron ? (event) => {
                      event.preventDefault();
                      void openInChrome();
                    } : undefined}
                  >
                    {isElectron ? t('projectGitHub.openInChrome') : label('authorize')}
                  </a>
                ) : null}
                {authorization && chromeOpenFailed ? (
                  <p role="alert" data-testid={`chat-panel-project-${provider}-chrome-error`}>
                    {t('projectGitHub.chromeOpenFailed')}
                  </p>
                ) : null}
                <button
                  type="button"
                  disabled={busy && !device}
                  hidden={embedded && !device && !authorization && status.state !== 'connected'}
                  data-testid={`chat-panel-project-${provider}-disconnect`}
                  onClick={() => {
                    if (device) {
                      generation.current += 1;
                      inFlight.current = false;
                      setDevice(null);
                      setAuthorization('');
                    }
                    void run(async (current) => {
                      await request('disconnect');
                      if (current()) {
                        clearCatalog();
                        setAuthorization('');
                        setDevice(null);
                        setToken('');
                        setTokenPrompt(false);
                        setStatus({ configured: true, state: 'disconnected', can_import: false });
                      }
                    });
                  }}
                >
                  {label('disconnect')}
                </button>
              </>
            ) : null}
          </details>
          {status?.state === 'connected' ? (
            <>
              <label data-testid={`chat-panel-project-${provider}-account-label`}>
                {label('account')}
                <select
                  value={account ?? ''}
                  disabled={busy}
                  data-testid={`chat-panel-project-${provider}-account`}
                  onChange={(event) => {
                    const selected = accounts.items.find((item) => String(item.id) === event.target.value);
                    if (selected) void readRepositories(selected.id, 1);
                  }}
                >
                  <option value="">{label('choose')}</option>
                  {accounts.items.map((item) => (
                    <option
                      key={item.id}
                      value={item.id}
                      data-testid={`chat-panel-project-${provider}-account-option`}
                      data-variant={item.id}
                    >
                      {item.account}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                disabled={busy || accountPage === 1}
                hidden={embedded && accountPage === 1 && !accounts.has_more}
                data-testid={`chat-panel-project-${provider}-accounts-previous`}
                onClick={() =>
                  void run(async (current) => {
                    const values = await request<Page<Account>>('accounts', { page: accountPage - 1 });
                    if (current()) {
                      clearCatalog();
                      setAccounts(values);
                      setAccountPage(accountPage - 1);
                    }
                  })
                }
              >
                {label('previous')}
              </button>
              <button
                type="button"
                disabled={busy || !accounts.has_more}
                hidden={embedded && accountPage === 1 && !accounts.has_more}
                data-testid={`chat-panel-project-${provider}-accounts-next`}
                onClick={() =>
                  void run(async (current) => {
                    const values = await request<Page<Account>>('accounts', { page: accountPage + 1 });
                    if (current()) {
                      clearCatalog();
                      setAccounts(values);
                      setAccountPage(accountPage + 1);
                    }
                  })
                }
              >
                {label('next')}
              </button>
              {!accounts.items.length && !busy && !failed ? (
                <p data-testid={`chat-panel-project-${provider}-empty`}>{label('noAccess')}</p>
              ) : null}
            </>
          ) : null}
          {account ? (
            <>
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder={label('searchPage')}
                aria-label={label('searchPage')}
                data-testid={`chat-panel-project-${provider}-search`}
              />
              <div className="chat-project-github__repositories" data-testid={`chat-panel-project-${provider}-repositories`}>
                {repositories.items
                  .filter((item) => item.full_name.toLowerCase().includes(search.toLowerCase()))
                  .map((item) => (
                    <button
                      type="button"
                      key={item.id}
                      disabled={busy}
                      aria-pressed={repository?.id === item.id}
                      className="chat-work-select__option"
                      data-testid={`chat-panel-project-${provider}-repository`}
                      data-variant={item.id}
                      onClick={() => void selectRepository(item)}
                    >
                      <span aria-hidden="true">{repository?.id === item.id ? '✓' : '○'}</span> {item.full_name}
                    </button>
                  ))}
              </div>
              <button
                type="button"
                disabled={busy || page === 1}
                hidden={embedded && page === 1 && !repositories.has_more}
                data-testid={`chat-panel-project-${provider}-repositories-previous`}
                onClick={() => void readRepositories(account, page - 1)}
              >
                {label('previous')}
              </button>
              <button
                type="button"
                disabled={busy || !repositories.has_more}
                hidden={embedded && page === 1 && !repositories.has_more}
                data-testid={`chat-panel-project-${provider}-repositories-next`}
                onClick={() => void readRepositories(account, page + 1)}
              >
                {label('next')}
              </button>
            </>
          ) : null}
          {repository ? (
            <div data-testid={`chat-panel-project-${provider}-branches`}>
              {embedded && !branchPickerOpen ? (
                <button
                  type="button"
                  disabled={busy || !selectedBranch}
                  data-testid={`chat-panel-project-${provider}-branch-toggle`}
                  onClick={() => {
                    setBranchPickerOpen(true);
                    void readBranches(repository, 1);
                  }}
                >
                  {label('optionalBranch', { branch: selectedBranch })}
                </button>
              ) : (
                <>
                  {embedded ? (
                    <label
                      className="chat-project-github__branch-label"
                      data-testid={`chat-panel-project-${provider}-branch-label`}
                    >
                      {label('branch')}
                      <select
                        value={selectedBranch ?? ''}
                        disabled={busy}
                        data-testid={`chat-panel-project-${provider}-branch-select`}
                        onChange={(event) => {
                          const branch = branches.items.find((item) => item.name === event.target.value);
                          if (!branch || !account) return;
                          setSelectedBranch(branch.name);
                          selectionChanged.current?.(status?.can_import ? { accountId: account, repository, branch } : null);
                        }}
                      >
                        <option value="" data-testid={`chat-panel-project-${provider}-branch-placeholder`}>
                          {label('chooseBranch')}
                        </option>
                        {branches.items.map((branch) => (
                          <option
                            key={branch.name}
                            value={branch.name}
                            data-testid={`chat-panel-project-${provider}-branch-option`}
                            data-variant={branch.name}
                          >
                            {branch.name}
                          </option>
                        ))}
                      </select>
                    </label>
                  ) : (
                    <>
                      {branches.items.map((branch) => (
                        <button
                          type="button"
                          key={branch.name}
                          disabled={busy}
                          aria-pressed={selectedBranch === branch.name}
                          data-testid={`chat-panel-project-${provider}-branch`}
                          data-variant={branch.name}
                          onClick={() => {
                            if (!account) return;
                            setSelectedBranch(branch.name);
                            selectionChanged.current?.(status?.can_import ? { accountId: account, repository, branch } : null);
                          }}
                        >
                          {branch.name} · {branch.commit.slice(0, 8)}
                        </button>
                      ))}
                    </>
                  )}
                  <button
                    type="button"
                    disabled={busy || branchPage === 1}
                    hidden={embedded && branchPage === 1 && !branches.has_more}
                    data-testid={`chat-panel-project-${provider}-branches-previous`}
                    onClick={() => void readBranches(repository, branchPage - 1)}
                  >
                    {label('previous')}
                  </button>
                  <button
                    type="button"
                    disabled={busy || !branches.has_more}
                    hidden={embedded && branchPage === 1 && !branches.has_more}
                    data-testid={`chat-panel-project-${provider}-branches-next`}
                    onClick={() => void readBranches(repository, branchPage + 1)}
                  >
                    {label('next')}
                  </button>
                </>
              )}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
