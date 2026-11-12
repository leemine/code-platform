import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { Cloud, Monitor, Folder, FolderPlus, Plus, Server, ChevronDown, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '../ui/Button/Button';
import { Dialog } from '../ui/Dialog/Dialog';
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from '../ui/DropdownMenu/DropdownMenu';
import { webClient, webRequest } from '../../services/webClient';
import { onOrganizationCredentialChange } from '../../services/organizationCredentialEvents';
import { useWorkspaceStore } from '../../stores/workspaceStore';
import { getDirectoryName } from '../../features/workspace/projectDirectoryPicker';
import type { ProjectInfo } from '../../features/workspace/projectTypes';
import './CodeWorkspaceControls.css';

type Location = 'local' | 'cloud';
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

/** Three controls; host navigation retains the original authenticated route. */
export function CodeWorkspaceControls({ localControl, enabled, disabled, onBlockedChange, navigationBlocked = false }: {
  localControl: ReactNode; enabled: boolean; disabled: boolean; navigationBlocked?: boolean; onBlockedChange: (blocked: boolean) => void;
}) {
  const { t } = useTranslation();
  const titleId = useId();
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [environment, setEnvironment] = useState<Environment | null>(null);
  const [localPath, setLocalPath] = useState('');
  const [menu, setMenu] = useState<'location' | 'cloud' | null>(null);
  const [dialog, setDialog] = useState<'directory' | 'folder' | 'environment' | null>(null);
  const [page, setPage] = useState<Page | null>(null);
  const [path, setPath] = useState('');
  const [selected, setSelected] = useState('');
  const [folder, setFolder] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const generation = useRef(0), working = useRef(false);
  const selectedProject = useWorkspaceStore(s => s.selectedProject);
  const blocked = enabled && (!catalog || busy || Boolean(dialog));
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
      setCatalog(null); setEnvironment(null); setMenu(null); setDialog(null); setPage(null); setBusy(false); setLocalPath('');
    };
    const auth = onOrganizationCredentialChange(() => { invalidate(); setReload(n => n + 1); });
    const connection = webClient.onStateChange(state => {
      if (state !== 'ready') invalidate(); else setReload(n => n + 1);
    });
    return () => { generation.current++; auth(); connection(); };
  }, []);
  useEffect(() => {
    if (!enabled) { generation.current++; working.current = false; setBusy(false); setDialog(null); return; }
    const epoch = ++generation.current;
    setError(''); setCatalog(null);
    void webRequest<Catalog>('workspace.locations', {}).then(parseWorkspaceCatalog).then(value => {
      if (epoch !== generation.current) return;
      setCatalog(value);
      if (value.kind === 'cloud') void webRequest<Environment>('cloud.environment.status', {}).then(row => {
        if (epoch === generation.current && row?.environment_id) setEnvironment(row);
      }).catch(reason => { if (epoch === generation.current) setError(failure(reason)); });
    }).catch(reason => { if (epoch === generation.current) setError(failure(reason)); });
    return () => { generation.current++; };
  }, [reload, enabled]);
  async function list(next: string, offset = 0) {
    if (working.current) return;
    working.current = true; setBusy(true); setError('');
    const epoch = generation.current;
    try {
      const result = parseWorkspacePage(await webRequest<Page>('project.workspace.list', { path: next, offset, work_mode: 'code' }), next);
      if (epoch !== generation.current) return;
      setPath(next); setSelected('');
      setPage(old => offset && old?.path === next ? { ...result, items: [...old.items, ...result.items] } : result);
    } catch (reason) { if (epoch === generation.current) { setPage(null); setError(failure(reason)); } }
    finally { if (epoch === generation.current) { working.current = false; setBusy(false); } }
  }
  function showDirectory(kind: 'directory' | 'folder') {
    setMenu(null); setDialog(kind); setFolder(''); setPage(null); setPath(''); setSelected(''); void list('');
  }
  async function mutate(operation: 'open' | 'mkdir' | 'environment') {
    if (working.current || !catalog || catalog.kind !== 'cloud') return;
    working.current = true; setBusy(true); setError('');
    const epoch = generation.current;
    try {
      if (operation === 'environment') {
        const row = await webRequest<Environment>('cloud.environment.ensure', {}, { timeoutMs: 150000 });
        if (!row?.environment_id || row.state !== 'READY') throw new Error('NOT_READY');
        if (epoch === generation.current) { setEnvironment(row); setDialog(null); }
      } else if (operation === 'mkdir') {
        const result = await webRequest<{ path: string; created: boolean }>('project.workspace.mkdir', { path, name: folder.trim(), work_mode: 'code' });
        const expected = [path, folder.trim()].filter(Boolean).join('/');
        if (result.path !== expected || !result.created) throw new Error('INVALID_DIRECTORY');
        if (epoch === generation.current) { setDialog('directory'); setFolder(''); setPage(null); setSelected(result.path); }
      } else {
        const result = await webRequest<{ project: ProjectInfo }>('project.workspace.open', { path: selected || path, work_mode: 'code' });
        if (!result.project?.project_id || result.project.work_mode !== 'code' || !result.project.project_dir) throw new Error('INVALID_PROJECT');
        if (epoch === generation.current) {
          useWorkspaceStore.getState().setSelectedProject(result.project);
          void useWorkspaceStore.getState().loadProjects(); setDialog(null);
        }
      }
    } catch (reason) { if (epoch === generation.current) { setError(failure(reason, true)); setPage(null); } }
    finally { if (epoch === generation.current) { working.current = false; setBusy(false); } }
  }
  async function pickLocal() {
    // A cloud entry must never fall back to a Gateway-native picker.
    const picker = window.pywebview?.api?.select_project_directory;
    if (!picker) { setError(t('codeWorkspace.localUnavailable')); return; }
    const epoch = generation.current;
    try { const value = await picker(); if (epoch === generation.current && typeof value === 'string') setLocalPath(value); }
    catch { if (epoch === generation.current) setError(t('codeWorkspace.localUnavailable')); }
  }
  async function switchLocation(row: Catalog['entries'][number]) {
    if (row.current || !row.url || working.current || navigationBlocked) { setMenu(null); return; }
    working.current = true; setBusy(true); setMenu(null);
    // Never reuse sessions/projects from another host. Full navigation uses
    // that entry's normal login and original Runtime, rather than rebinding it.
    try { await webClient.disconnect('workspace entry changed'); window.location.assign(row.url + '#code-workspace'); }
    catch { working.current = false; setBusy(false); setError(t('codeWorkspace.unavailable')); }
  }
  if (!enabled) return <>{localControl}</>;
  return <>
    {catalog?.kind === 'local' ? localControl : <button type="button" className="chat-work-select__trigger" onClick={() => void pickLocal()} disabled={disabled || busy || !catalog}
      data-testid="chat-panel-code-local-directory" data-tooltip={localPath || t('codeWorkspace.localUnavailable')}><Folder size={14} /><span>{localPath ? getDirectoryName(localPath) : t('codeWorkspace.localDirectory')}</span></button>}
    <DropdownMenu open={menu === 'location'} onOpenChange={open => setMenu(open ? 'location' : null)}>
      <DropdownMenuTrigger className="chat-work-select__trigger" disabled={disabled || busy} data-testid="chat-panel-code-location-trigger">
        {catalog?.kind === 'cloud' ? <Cloud size={14} /> : <Monitor size={14} />}<span>{catalog ? t(`codeWorkspace.${catalog.kind}`) : t('codeWorkspace.loading')}</span><ChevronDown size={12} />
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="start" data-testid="chat-panel-code-location-menu">
        {catalog?.entries.map(row => <DropdownMenuItem key={row.kind} disabled={!row.current && (!row.url || navigationBlocked)} onSelect={() => void switchLocation(row)} data-testid="chat-panel-code-location-option" data-variant={row.kind}>
          {t(`codeWorkspace.${row.kind}`)}{row.current ? ' ✓' : !row.url ? ` · ${t('codeWorkspace.notConnected')}` : navigationBlocked ? ` · ${t('codeWorkspace.draftPending')}` : ''}
        </DropdownMenuItem>)}
        {!catalog && <DropdownMenuItem icon={<RefreshCw size={14} />} onSelect={() => setReload(n => n + 1)} data-testid="chat-panel-code-location-retry">{t('codeWorkspace.retry')}</DropdownMenuItem>}
      </DropdownMenuContent>
    </DropdownMenu>
    {catalog?.kind === 'cloud' && <DropdownMenu open={menu === 'cloud'} onOpenChange={open => setMenu(open ? 'cloud' : null)}>
      <DropdownMenuTrigger className="chat-work-select__trigger" disabled={disabled || busy} data-testid="chat-panel-code-cloud-trigger" data-tooltip={selectedProject?.project_dir}>
        <Server size={14} /><span>{t('codeWorkspace.defaultEnvironment')}{selectedProject && !selectedProject.is_default ? ` · ${selectedProject.name}` : ''}</span><ChevronDown size={12} />
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="start" data-testid="chat-panel-code-cloud-menu">
        <DropdownMenuItem disabled data-testid="chat-panel-code-cloud-environment">{t('codeWorkspace.defaultEnvironment')}{environment ? ' ✓' : ''}</DropdownMenuItem>
        <DropdownMenuItem onSelect={() => showDirectory('directory')} icon={<Folder size={14} />} data-testid="chat-panel-code-cloud-directory">{t('codeWorkspace.chooseDirectory')}</DropdownMenuItem>
        <DropdownMenuItem onSelect={() => showDirectory('folder')} icon={<FolderPlus size={14} />} data-testid="chat-panel-code-cloud-mkdir">{t('codeWorkspace.newFolder')}</DropdownMenuItem>
        <DropdownMenuItem onSelect={() => { setMenu(null); setError(''); setDialog('environment'); }} icon={<Plus size={14} />} data-testid="chat-panel-code-cloud-create">{t('codeWorkspace.createEnvironment')}</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>}
    {error && !dialog && <span role="alert" className="code-workspace-error" data-testid="chat-panel-code-workspace-error">{error}</span>}
    <Dialog open={Boolean(dialog)} titleId={titleId} onCancel={() => { if (!busy) setDialog(null); }} closeDisabled={busy} className="code-workspace-dialog">
      <section data-testid="chat-panel-code-workspace-dialog" data-variant={dialog || ''}>
        <h2 id={titleId} data-testid="chat-panel-code-workspace-title">{t(dialog === 'environment' ? 'codeWorkspace.createEnvironment' : dialog === 'folder' ? 'codeWorkspace.newFolder' : 'codeWorkspace.chooseDirectory')}</h2>
        {dialog === 'environment' ? <p data-testid="chat-panel-code-environment-description">{t('codeWorkspace.environmentDescription')}</p> : <>
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
          {dialog === 'folder' && <label data-testid="chat-panel-code-folder-label">{t('codeWorkspace.folderName')}<input value={folder} onChange={event => setFolder(event.target.value)} disabled={busy || !page} maxLength={200} data-testid="chat-panel-code-folder-name" /></label>}
        </>}
        {busy && <p role="status" data-testid="chat-panel-code-workspace-busy">{t('codeWorkspace.preparing')}</p>}
        {error && <p role="alert" className="code-workspace-error" data-testid="chat-panel-code-workspace-dialog-error">{error}</p>}
        <div className="code-workspace-actions">
          <Button variant="quiet" disabled={busy} onClick={() => setDialog(null)} data-testid="chat-panel-code-workspace-cancel">{t('codeWorkspace.cancel')}</Button>
          <Button variant="primary" disabled={busy || (dialog === 'folder' ? !page || !folder.trim() : dialog === 'directory' ? (!selected && !path) || Boolean(error) : false)}
            onClick={() => void mutate(dialog === 'environment' ? 'environment' : dialog === 'folder' ? 'mkdir' : 'open')} data-testid="chat-panel-code-workspace-confirm">
            {t(dialog === 'directory' ? 'codeWorkspace.open' : 'codeWorkspace.create')}
          </Button>
        </div>
      </section>
    </Dialog>
  </>;
}
