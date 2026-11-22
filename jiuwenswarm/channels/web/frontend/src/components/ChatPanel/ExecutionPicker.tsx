import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown, Cpu, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useSessionStore } from '../../stores/sessionStore';
import { NEW_CONVERSATION_ID } from '../../multi-session/state/newConversationLifecycle';
import { parseExecutionProviderCatalog, type ExecutionProviderOption } from '../../services/executionProviderCatalog';
import { isOpenCodeNativeModel, readManagedOpenCodeModels } from '../../features/cloudWorkspace/opencodeModels';
import { useCloudCatalog } from '../../features/cloudWorkspace/useCloudCatalog';
import { useCloudRuntimes, useProjectRuntime } from '../../features/cloudWorkspace/useProjectRuntime';
import './ExecutionPicker.css';

type RuntimeOption = ExecutionProviderOption & { runtimeId?: string; runtimeState?: string };

export function ExecutionPicker({ sessionId, disabled = false, runtimeProjectId = null }: {
  sessionId: string; disabled?: boolean; runtimeProjectId?: string | null;
}) {
  const { t } = useTranslation();
  const cloud = useCloudCatalog(sessionId);
  const draft = sessionId === NEW_CONVERSATION_ID;
  const runtime = useProjectRuntime(draft ? runtimeProjectId : null);
  const selectedId = useSessionStore((s) => s.runtimes[sessionId]?.executionProvider ?? 'harness');
  const selectedRuntimeId = useSessionStore((s) => s.runtimes[sessionId]?.executionRuntimeId);
  const mode = useSessionStore((s) => s.runtimes[sessionId]?.mode ?? 'agent');
  const namedCatalog = useCloudRuntimes(Boolean(draft ? runtimeProjectId : selectedRuntimeId));
  const options = useMemo<RuntimeOption[] | null>(() => {
    if (!cloud.catalog) return null;
    try {
      return parseExecutionProviderCatalog(cloud.catalog.config.execution_provider_catalog).flatMap<RuntimeOption>(option => {
        const defaultOption = runtime?.provider_id === option.id ? {
          ...option,
          label: `${option.label} · ${runtime.display_name ?? t('chat.executionProvider.cloudRuntimeName')}`,
          available: option.available && runtime.available,
          reason: option.available && !runtime.available ? 'managed_admission_closed' : option.reason,
        } as RuntimeOption : option;
        const namedOptions = (namedCatalog?.runtimes ?? [])
          .filter(device => device.runtime_id && device.provider_id === option.id)
          .map(device => ({
            ...option, runtimeId: device.runtime_id, runtimeState: device.state, label: `${option.label} · ${device.display_name}`,
            available: option.available && device.available && device.state !== 'starting',
          }));
        return [defaultOption, ...namedOptions];
      });
    } catch {
      return null;
    }
  }, [cloud.catalog, namedCatalog, runtime, t]);
  const error = cloud.error || (cloud.catalog !== null && options === null);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<CSSProperties>({ visibility: 'hidden' });
  const anchor = useRef<HTMLDivElement>(null);
  const menu = useRef<HTMLDivElement>(null);

  useEffect(() => { setOpen(false); }, [mode, disabled, sessionId, cloud.catalog]);

  useEffect(() => {
    if (!open) return;
    const dismiss = (e: PointerEvent) => {
      if (!anchor.current?.contains(e.target as Node) && !menu.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', dismiss);
    return () => document.removeEventListener('pointerdown', dismiss);
  }, [open]);
  useLayoutEffect(() => {
    if (!open) return;
    const update = () => {
      if (!anchor.current || !menu.current) return;
      const rect = anchor.current.getBoundingClientRect();
      const above = rect.top - 10,
        below = window.innerHeight - rect.bottom - 10;
      setPosition({
        left: Math.max(10, Math.min(rect.left, window.innerWidth - menu.current.offsetWidth - 10)),
        ...(above > below ? { bottom: window.innerHeight - rect.top + 8 } : { top: rect.bottom + 8 }),
        maxHeight: Math.max(100, Math.min(340, above > below ? above : below)),
      });
    };
    update();
    menu.current?.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus();
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [open]);

  function choose(option: RuntimeOption) {
    if (!draft || disabled || !option.available || !option.modes.includes(mode)) return;
    const state = useSessionStore.getState();
    const current = state.runtimes[sessionId];
    const policy = readManagedOpenCodeModels(cloud.catalog?.config);
    state.setExecutionProvider(sessionId, option.id, option.runtimeId);
    if (option.id === 'opencode-direct' && policy && current?.executionProvider !== option.id) {
      state.setSelectedModelSelection(sessionId, policy.default ? { type: 'model', id: policy.default.id } : null);
    } else if (option.id !== 'opencode-direct' && isOpenCodeNativeModel(current?.selectedModelSelection)) {
      state.setSelectedModelSelection(sessionId, null);
    }
    setOpen(false);
    anchor.current?.querySelector('button')?.focus();
  }
  const isSelected = (option: RuntimeOption) => option.id === selectedId && option.runtimeId === selectedRuntimeId;
  const label = options?.find(isSelected)?.label
    ?? (selectedId === 'harness' ? 'Deepagent' : selectedId);
  const unavailable = draft && options && !options.some(
    (option) => isSelected(option) && option.available && option.modes.includes(mode),
  );
  return (
    <div className="chat-mode-select chat-execution-picker" ref={anchor} data-testid="chat-panel-execution-picker">
      {!draft ? (
        <span
          className="chat-mode-select__trigger"
          title={t('chat.executionProvider.locked')}
          data-testid="chat-panel-execution-binding"
        >
          <Cpu size={16} aria-hidden="true" />
          <span data-testid="chat-panel-execution-label">
            {label}
          </span>
        </span>
      ) : (
        <button
          type="button"
          className="chat-mode-select__trigger"
          data-testid="chat-panel-execution-trigger"
          aria-label={t('chat.executionProvider.title')}
          aria-expanded={open}
          aria-haspopup="menu"
          disabled={disabled}
          onClick={() => {
            setOpen((value) => !value);
          }}
        >
          <Cpu size={16} aria-hidden="true" />
          <span data-testid="chat-panel-execution-label">
            {label}
          </span>
          <ChevronDown size={12} aria-hidden="true" />
        </button>
      )}
      {draft &&
        open &&
        createPortal(
          <div
            ref={menu}
            style={position}
            className="chat-execution-menu"
            role="menu"
            data-testid="chat-panel-execution-menu"
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                e.preventDefault();
                setOpen(false);
                anchor.current?.querySelector('button')?.focus();
              } else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) {
                e.preventDefault();
                const items = Array.from(
                  menu.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? [],
                );
                const index = items.indexOf(document.activeElement as HTMLButtonElement);
                const next =
                  e.key === 'Home'
                    ? 0
                    : e.key === 'End'
                      ? items.length - 1
                      : (index + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
                items[next]?.focus();
              }
            }}
          >
            <div className="chat-execution-menu__title" data-testid="chat-panel-execution-menu-title">
              {t('chat.executionProvider.title')}
            </div>
            {unavailable && (
              <p role="alert" data-testid="chat-panel-execution-unavailable">
                {t('chat.executionProvider.selectionUnavailable')}
              </p>
            )}
            {error ? (
              <button
                type="button"
                className="chat-mode-select__option"
                data-testid="chat-panel-execution-retry"
                onClick={cloud.retry}
              >
                <RefreshCw size={14} />
                {t('chat.executionProvider.retry')}
              </button>
            ) : !options ? (
              <p role="status" data-testid="chat-panel-execution-loading">
                {t('chat.executionProvider.loading')}
              </p>
            ) : (
              options.map((option) => (
                <button
                  type="button"
                  className="chat-mode-select__option"
                  role="menuitemradio"
                  aria-checked={isSelected(option)}
                  disabled={disabled || !option.available || !option.modes.includes(mode)}
                  data-testid="chat-panel-execution-option"
                  data-variant={option.runtimeId ?? option.id ?? 'legacy-native'}
                  key={option.runtimeId ?? option.id ?? 'legacy-native'}
                  onClick={() => choose(option)}
                >
                  <span className="chat-execution-option__copy">
                    <span>{option.label}</span>
                    {option.runtimeState && <small>{t(`cloudRuntime.state.${option.runtimeState}`)}</small>}
                    {(!option.available || !option.modes.includes(mode)) && option.runtimeState !== 'starting' &&
                      <small>{t(`chat.executionProvider.reason.${option.reason ?? 'unsupported_mode'}`)}</small>}
                  </span>
                  {isSelected(option) && <Check size={14} aria-hidden="true" />}
                </button>
              ))
            )}

          </div>,
          document.body,
        )}
    </div>
  );
}
