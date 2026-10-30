import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown, Cpu, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useSessionStore } from '../../stores/sessionStore';
import { webRequest } from '../../services/webClient';
import { NEW_CONVERSATION_ID } from '../../multi-session/state/newConversationLifecycle';
import { SETTINGS_CONFIG_CHANGED_EVENT } from '../../features/settings/services/settingsContract';
import { parseExecutionProviderCatalog, type ExecutionProviderOption } from '../../services/executionProviderCatalog';
import './ExecutionPicker.css';

export function ExecutionPicker({ sessionId, disabled = false }: { sessionId: string; disabled?: boolean }) {
  const { t } = useTranslation();
  const draft = sessionId === NEW_CONVERSATION_ID;
  const selectedId = useSessionStore((s) => s.runtimes[sessionId]?.executionProvider ?? 'harness');
  const mode = useSessionStore((s) => s.runtimes[sessionId]?.mode ?? 'agent');
  const [options, setOptions] = useState<ExecutionProviderOption[] | null>(null);
  const [error, setError] = useState(false);
  const [reload, setReload] = useState(0);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<CSSProperties>({ visibility: 'hidden' });
  const anchor = useRef<HTMLDivElement>(null);
  const menu = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const refresh = () => setReload((value) => value + 1);
    window.addEventListener(SETTINGS_CONFIG_CHANGED_EVENT, refresh);
    return () => window.removeEventListener(SETTINGS_CONFIG_CHANGED_EVENT, refresh);
  }, []);
  useEffect(() => {
    let active = true;
    setOptions(null);
    setError(false);
    setOpen(false);
    void webRequest<Record<string, unknown>>('config.get').then((config) => {
      if (active) setOptions(parseExecutionProviderCatalog(config.execution_provider_catalog));
    }).catch(() => { if (active) setError(true); });
    return () => { active = false; };
  }, [sessionId, reload]);
  useEffect(() => { setOpen(false); }, [mode, disabled]);

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

  function choose(option: ExecutionProviderOption) {
    if (!draft || disabled || !option.available || !option.modes.includes(mode)) return;
    useSessionStore.getState().setExecutionProvider(sessionId, option.id);
    setOpen(false);
    anchor.current?.querySelector('button')?.focus();
  }
  const label = options?.find((option) => option.id === selectedId)?.label
    ?? (selectedId === 'harness' ? 'Deepagent' : selectedId);
  const unavailable = draft && options && !options.some(
    (option) => option.id === selectedId && option.available && option.modes.includes(mode),
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
                onClick={() => setReload((n) => n + 1)}
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
                  aria-checked={selectedId === option.id}
                  disabled={disabled || !option.available || !option.modes.includes(mode)}
                  data-testid="chat-panel-execution-option"
                  data-variant={option.id ?? 'legacy-native'}
                  key={option.id ?? 'legacy-native'}
                  onClick={() => choose(option)}
                >
                  <span className="chat-execution-option__copy">
                    <span>{option.label}</span>
                    {(!option.available || !option.modes.includes(mode)) && <small>{t(`chat.executionProvider.reason.${option.reason ?? 'unsupported_mode'}`)}</small>}
                  </span>
                  {selectedId === option.id && <Check size={14} aria-hidden="true" />}
                </button>
              ))
            )}

          </div>,
          document.body,
        )}
    </div>
  );
}
