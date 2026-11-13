import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { Cloud, Monitor, Folder, FolderPlus, Plus, Server, ChevronDown, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '../ui/Button/Button';
import { Dialog } from '../ui/Dialog/Dialog';
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from '../ui/DropdownMenu/DropdownMenu';
import { webClient, webRequest } from '../../services/webClient';
import { onOrganizationCredentialChange } from '../../services/organizationCredentialEvents';
import { useWorkspaceStore } from '../../stores/workspaceStore';
import type { ProjectInfo } from '../../features/workspace/projectTypes';
import { localCloudWorkspaceRequest, onLocalCloudAccountChange, requestLocalCloudLogin } from '../../features/cloudWorkspace/localCloudAccountClient';
import './CodeWorkspaceControls.css';

type Location = 'local' | 'cloud';
type CloudAction = 'directory' | 'folder' | 'environment' | 'environments';
type Catalog = { kind: Location; switch_mode: 'entry_navigation'; entries: { kind: Location; current: boolean; url: string | null }[] };
type Page = { path: string; work_mode: 'code'; items: { name: string; path: string }[]; next_offset: number | null };
type Environment = { environment_id: string; state: string };

export function parseWorkspaceCatalog(value: Catalog): Catalog {
  if (!value || !['local', 'cloud'].includes(value.kind) || value.switch_mode !== 'entry_navigation' ||
      !Array.isArray(value.entries) || value.entries.length !== 2 ||
      new Set(value.entries.map(row => row.kind)).size !== 2 || value.entries.some(row => {
        if (!['local', 'cloud'].includes(row.kind) || row.current !== (row.kind === value.kind)) return true;
        if (row.url === null) return false;
        try {
          const url = new URL(row.url);
          return !!(url.username || url.password || url.search || url.hash || url.pathname !== '/' ||
            (url.protocol !== 'https:' && !(row.kind === 'local' && url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname))));
        } catch { return true; }
      })) throw new Error('INVALID_CATALOG');
  return value;
}

export function parseWorkspacePage(page: Page, path: string): Page {
  if (!page || page.path !== path || page.work_mode !== 'code' || !Array.isArray(page.items) || page.items.length > 100 ||
      !(page.next_offset === null || (Number.isInteger(page.next_offset) && page.next_offset > 0 && page.next_offset <= 10000)) ||
      page.items.some(row => !row || !row.name || row.name.startsWith('.') || /[\\/]/.test(row.name) || row.path !== [path, row.name].filter(Boolean).join('/'))) {
    throw new Error('INVALID_DIRECTORY');
  }
  return page;
}

/** Three controls; explicit cloud actions reuse the local account bridge without navigation. */
export function CodeWorkspaceControls({ localControl, enabled, disabled, onBlockedChange }: {
  localControl: ReactNode; enabled: boolean; disabled: boolean; onBlockedChange: (blocked: boolean) => void;
}) {
  const { t } = useTranslation();
  const titleId = useId();
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [location, setLocation] = useState<Location | null>(null);
  const chosen = useRef(false);
  const [environment, setEnvironment] = useState<Environment | null>(null);
  const [menu, setMenu] = useState<'location' | 'cloud' | null>(null);
  const [dialog, setDialog] = useState<CloudAction | null>(null);
  const [remoteProject, setRemoteProject] = useState<ProjectInfo | null>(null);
  const intent = useRef(0);
  const currentAction = useRef<CloudAction | null>(null);
  const [page, setPage] = useState<Page | null>(null);
  const [path, setPath] = useState('');
  const [selected, setSelected] = useState('');
  const [folder, setFolder] = useState('');
  const [busy, setBusy] = useState(false);
  const [mutating, setMutating] = useState(false);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const generation = useRef(0), working = useRef(false);
  const selectedProject = useWorkspaceStore(s => s.selectedProject);
  const selectedLocation = location || catalog?.kind || 'local';
  const remote = catalog?.kind === 'local' && selectedLocation === 'cloud';
  const needsEntry = !catalog || selectedLocation !== catalog.kind;
  const cloudProject = remote ? remoteProject : selectedProject;
  const blocked = enabled && (needsEntry || busy || Boolean(dialog));
  useEffect(() => { onBlockedChange(blocked); }, [blocked, onBlockedChange]);
  useEffect(() => {
    if (!menu) return;
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') setMenu(null); };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [menu]);
  useEffect(() => () => onBlockedChange(false), [onBlockedChange]);
  const failure = (reason: unknown, mutation = false) => {
    const code = (reason as { code?: string })?.code;
    return t(code === 'PROJECT_ROOT_REQUIRED' ? 'codeWorkspace.projectRootRequired' : code === 'CONFLICT' ? 'codeWorkspace.exists' : mutation ? 'codeWorkspace.unknown' : 'codeWorkspace.unavailable');
  };
  useEffect(() => {
    const invalidate = () => {
      generation.current++; working.current = false;
      setCatalog(null); setEnvironment(null); setMenu(null); setDialog(null); setPage(null); setBusy(false); setMutating(false);
    };
    const localAuth = onLocalCloudAccountChange(() => {
      generation.current++; working.current = false; setBusy(false); setMutating(false);
      setEnvironment(null); setRemoteProject(null); setDialog(null); setPage(null); setError('');
    });
    const auth = onOrganizationCredentialChange(() => { chosen.current = false; setLocation(null); invalidate(); setReload(n => n + 1); });
    const connection = webClient.onStateChange(state => {
      if (state !== 'ready') invalidate(); else setReload(n => n + 1);
    });
    return () => { generation.current++; intent.current++; auth(); localAuth(); connection(); };
  }, []);
  useEffect(() => {
    if (!enabled) { intent.current++; generation.current++; working.current = false; setBusy(false); setMutating(false); setDialog(null); return; }
    const epoch = ++generation.current;
    setError(''); setCatalog(null);
    void webRequest<Catalog>('workspace.locations', {}).then(parseWorkspaceCatalog).then(value => {
      if (epoch !== generation.current) return;
      setCatalog(value);
      if (!chosen.current) setLocation(value.kind);
    }).catch(reason => { if (epoch === generation.current) setError(failure(reason)); });
    return () => { generation.current++; };
  }, [reload, enabled]);
  async function workspaceRequest<T>(operation: 'environment' | 'ensure' | 'list' | 'mkdir' | 'open', params: Record<string, unknown> = {}): Promise<T> {
    if (remote) return localCloudWorkspaceRequest<T>(operation, params);
    if (catalog?.kind !== 'cloud') throw new Error('CLOUD_REQUIRED');
    if (operation === 'environment' || operation === 'ensure') return webRequest<T>(`cloud.environment.${operation === 'environment' ? 'status' : 'ensure'}`, {}, { timeoutMs: 150000 });
    return webRequest<T>(`project.workspace.${operation}`, { ...params, work_mode: 'code' });
  }
  function requestLogin(reason: unknown, retry: () => void): boolean {
    if (!remote || (reason as { code?: string })?.code !== 'UNAUTHORIZED') return false;
    const expected = intent.current;
    setDialog(null);
    requestLocalCloudLogin(authenticated => {
      if (authenticated && expected === intent.current) retry();
    });
    return true;
  }
  async function list(next: string, offset = 0) {
    if (working.current) return;
    working.current = true; setBusy(true); setError('');
    const epoch = generation.current;
    try {
      const result = parseWorkspacePage(await workspaceRequest<Page>('list', { path: next, offset }), next);
      if (epoch !== generation.current) return;
      setPath(next); setSelected('');
      setPage(old => offset && old?.path === next ? { ...result, items: [...old.items, ...result.items] } : result);
    } catch (reason) { if (epoch === generation.current) { setPage(null); if (!requestLogin(reason, () => { if (currentAction.current) void perform(currentAction.current, true); })) setError(failure(reason)); } }
    finally { if (epoch === generation.current) { working.current = false; setBusy(false); setMutating(false); } }
  }
  function showDirectory(kind: 'directory' | 'folder', preserveDraft = false) {
    setMenu(null); setDialog(kind); if (!preserveDraft) setFolder(''); setPage(null); setPath(''); setSelected(''); void list('');
  }
  async function mutate(operation: 'open' | 'mkdir' | 'environment') {
    if (working.current || !catalog || selectedLocation !== 'cloud') return;
    working.current = true; setBusy(true); setMutating(true); setError('');
    const epoch = generation.current;
    try {
      if (operation === 'environment') {
        const row = await workspaceRequest<Environment>('ensure');
        if (!row?.environment_id || row.state !== 'READY') throw new Error('NOT_READY');
        if (epoch === generation.current) { setEnvironment(row); setDialog(null); }
      } else if (operation === 'mkdir') {
        const result = await workspaceRequest<{ path: string; created: boolean }>('mkdir', { path, name: folder.trim() });
        const expected = [path, folder.trim()].filter(Boolean).join('/');
        if (result.path !== expected || !result.created) throw new Error('INVALID_DIRECTORY');
        if (epoch === generation.current) { setDialog('directory'); setFolder(''); setPage(null); setSelected(result.path); }
      } else {
        const result = await workspaceRequest<{ project: ProjectInfo }>('open', { path: selected || path });
        if (!result.project?.project_id || result.project.work_mode !== 'code' || !result.project.project_dir) throw new Error('INVALID_PROJECT');
        if (epoch === generation.current) {
          if (remote) setRemoteProject(result.project);
          else {
            useWorkspaceStore.getState().setSelectedProject(result.project);
            void useWorkspaceStore.getState().loadProjects();
          }
          setDialog(null);
        }
      }
    } catch (reason) { if (epoch === generation.current) { if (!requestLogin(reason, () => void perform(operation === 'environment' ? 'environment' : 'directory'))) setError(failure(reason, true)); setPage(null); } }
    finally { if (epoch === generation.current) { working.current = false; setBusy(false); setMutating(false); } }
  }
  function switchLocation(kind: Location) {
    if (disabled) return;
    if (busy) { generation.current++; working.current = false; setBusy(false); setMutating(false); }
    intent.current++; currentAction.current = null;
    chosen.current = true;
    setLocation(kind); setMenu(null); setDialog(null); setError('');
  }
  async function perform(action: CloudAction, preserveDraft = false) {
    if (disabled || working.current) return;
    currentAction.current = action;
    setMenu(null); setError('');
    if (!catalog) { setError(t('codeWorkspace.entryUnavailable')); setReload(n => n + 1); return; }
    if (action === 'environment') { setDialog('environment'); return; }
    if (action !== 'environments') { showDirectory(action, preserveDraft); return; }
    working.current = true; setBusy(true); setDialog('environments');
    const epoch = generation.current;
    try {
      const value = await workspaceRequest<Environment>('environment');
      if (!value?.environment_id || !['NEW', 'ALLOCATED', 'READY'].includes(value.state)) throw new Error('INVALID_ENVIRONMENT');
      if (epoch === generation.current) setEnvironment(value);
    } catch (reason) {
      if (epoch === generation.current && !requestLogin(reason, () => void perform(action))) setError(failure(reason));
    } finally { if (epoch === generation.current) { working.current = false; setBusy(false); setMutating(false); } }
  }
  function cancelDialog() {
    if (mutating) return;
    intent.current++; generation.current++; currentAction.current = null;
    working.current = false; setBusy(false); setDialog(null); setPage(null); setError('');
  }
  if (!enabled) return <>{localControl}</>;
  return <>
    {catalog?.kind === 'local' ? <span onClickCapture={() => switchLocation('local')} data-testid="chat-panel-code-local-control">{localControl}</span> : <button type="button" className="chat-work-select__trigger" disabled
      data-testid="chat-panel-code-local-directory" data-tooltip={t('codeWorkspace.localClientRequired')}><Folder size={14} /><span>{t('codeWorkspace.localDirectory')}</span></button>}
    <DropdownMenu open={menu === 'location'} onOpenChange={open => setMenu(open ? 'location' : null)}>
      <DropdownMenuTrigger className="chat-work-select__trigger" disabled={disabled} data-testid="chat-panel-code-location-trigger">
        {selectedLocation === 'cloud' ? <Cloud size={14} /> : <Monitor size={14} />}<span>{t(`codeWorkspace.${selectedLocation}`)}</span><ChevronDown size={12} />
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="start" data-testid="chat-panel-code-location-menu">
        {(['local', 'cloud'] as const).map(kind => <DropdownMenuItem key={kind} onSelect={() => switchLocation(kind)} data-testid="chat-panel-code-location-option" data-variant={kind}>
          {t(`codeWorkspace.${kind}`)}{selectedLocation === kind ? ' ✓' : ''}
        </DropdownMenuItem>)}
        {!catalog && <DropdownMenuItem icon={<RefreshCw size={14} />} onSelect={() => setReload(n => n + 1)} data-testid="chat-panel-code-location-retry">{t('codeWorkspace.retry')}</DropdownMenuItem>}
      </DropdownMenuContent>
    </DropdownMenu>
    {selectedLocation === 'cloud' && <DropdownMenu open={menu === 'cloud'} onOpenChange={open => setMenu(open ? 'cloud' : null)}>
      <DropdownMenuTrigger className="chat-work-select__trigger" disabled={disabled || busy} data-testid="chat-panel-code-cloud-trigger" data-tooltip={cloudProject?.project_dir}>
        <Server size={14} /><span>{environment ? t('codeWorkspace.defaultEnvironment') : t('codeWorkspace.chooseCloudContext')}{cloudProject && !cloudProject.is_default ? ` · ${cloudProject.name}` : ''}</span><ChevronDown size={12} />
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="start" data-testid="chat-panel-code-cloud-menu">
        <DropdownMenuItem onSelect={() => void perform('environments')} data-testid="chat-panel-code-cloud-environment">{t('codeWorkspace.chooseEnvironment')}</DropdownMenuItem>
        <DropdownMenuItem onSelect={() => void perform('directory')} icon={<Folder size={14} />} data-testid="chat-panel-code-cloud-directory">{t('codeWorkspace.chooseDirectory')}</DropdownMenuItem>
        <DropdownMenuItem onSelect={() => void perform('folder')} icon={<FolderPlus size={14} />} data-testid="chat-panel-code-cloud-mkdir">{t('codeWorkspace.newFolder')}</DropdownMenuItem>
        <DropdownMenuItem onSelect={() => void perform('environment')} icon={<Plus size={14} />} data-testid="chat-panel-code-cloud-create">{t('codeWorkspace.createEnvironment')}</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>}
    {catalog?.kind === 'cloud' && selectedLocation === 'local' && <span className="code-workspace-error" data-testid="chat-panel-code-local-client-required">{t('codeWorkspace.localClientRequired')}</span>}
    {error && !dialog && <span role="alert" className="code-workspace-error" data-testid="chat-panel-code-workspace-error">{error}</span>}
    <Dialog open={Boolean(dialog)} titleId={titleId} onCancel={cancelDialog} closeDisabled={mutating} className="code-workspace-dialog">
      <section data-testid="chat-panel-code-workspace-dialog" data-variant={dialog || ''}>
        <h2 id={titleId} data-testid="chat-panel-code-workspace-title">{t(dialog === 'environments' ? 'codeWorkspace.chooseEnvironment' : dialog === 'environment' ? 'codeWorkspace.createEnvironment' : dialog === 'folder' ? 'codeWorkspace.newFolder' : 'codeWorkspace.chooseDirectory')}</h2>
        {dialog === 'environments' ? <div data-testid="chat-panel-code-environment-list">{environment && <p data-testid="chat-panel-code-environment-item">{t('codeWorkspace.defaultEnvironment')} · {t(`codeWorkspace.environmentState.${environment.state}`)}</p>}</div> : dialog === 'environment' ? <p data-testid="chat-panel-code-environment-description">{t('codeWorkspace.environmentDescription')}</p> : <>
          <div className="code-workspace-path" data-testid="chat-panel-code-directory-path">Cloud / Code / {path}</div>
          <div className="code-workspace-actions">
            <Button variant="quiet" disabled={busy} onClick={() => void list(path.split('/').slice(0, -1).join('/'))} data-testid="chat-panel-code-directory-up">{t('codeWorkspace.up')}</Button>
            <Button variant="quiet" disabled={busy} onClick={() => void list(path)} data-testid="chat-panel-code-directory-refresh">{t('codeWorkspace.refresh')}</Button>
          </div>
          <div className="code-workspace-directories" data-testid="chat-panel-code-directory-list">
            {page?.items.map(row => <button type="button" disabled={busy} key={row.path} className="chat-work-select__option" aria-pressed={selected === row.path}
              onClick={() => setSelected(row.path)} onDoubleClick={() => void list(row.path)} data-testid="chat-panel-code-directory-item" data-variant={row.path}><Folder size={14} />{row.name}</button>)}
            {page?.items.length === 0 && <p data-testid="chat-panel-code-directory-empty">{t('codeWorkspace.empty')}</p>}
          </div>
          {page?.next_offset != null && <Button variant="quiet" disabled={busy} onClick={() => void list(path, page.next_offset!)} data-testid="chat-panel-code-directory-more">{t('codeWorkspace.more')}</Button>}
          {selected && <div className="code-workspace-path" data-testid="chat-panel-code-directory-selection">{selected}</div>}
          <Button variant="quiet" disabled={busy || !selected} onClick={() => void list(selected)} data-testid="chat-panel-code-directory-enter">{t('codeWorkspace.enter')}</Button>
          {dialog === 'folder' && <label data-testid="chat-panel-code-folder-label">{t('codeWorkspace.folderName')}<input value={folder} onChange={event => setFolder(event.target.value)} disabled={mutating} maxLength={200} data-testid="chat-panel-code-folder-name" /></label>}
        </>}
        {busy && <p role="status" data-testid="chat-panel-code-workspace-busy">{t('codeWorkspace.preparing')}</p>}
        {error && <p role="alert" className="code-workspace-error" data-testid="chat-panel-code-workspace-dialog-error">{error}</p>}
        <div className="code-workspace-actions">
          <Button variant="quiet" disabled={mutating} onClick={cancelDialog} data-testid="chat-panel-code-workspace-cancel">{t('codeWorkspace.cancel')}</Button>
          <Button variant="primary" disabled={busy || (dialog === 'folder' ? !page || !folder.trim() : dialog === 'directory' ? (!selected && !path) || Boolean(error) : dialog === 'environments' ? !environment || Boolean(error) : false)}
            onClick={() => void mutate(dialog === 'environment' || dialog === 'environments' ? 'environment' : dialog === 'folder' ? 'mkdir' : 'open')} data-testid="chat-panel-code-workspace-confirm">
            {t(dialog === 'environments' ? 'codeWorkspace.selectEnvironment' : dialog === 'directory' ? 'codeWorkspace.open' : 'codeWorkspace.create')}
          </Button>
        </div>
      </section>
    </Dialog>
  </>;
}
