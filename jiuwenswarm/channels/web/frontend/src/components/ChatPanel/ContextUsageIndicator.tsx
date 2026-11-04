import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useChatStore } from '../../stores/chatStore';
import { useSessionStore } from '../../stores/sessionStore';
import {
  formatContextPercent,
  formatContextLimitTokens,
  formatContextTokens,
  getContextRingPercent,
} from '../../features/contextUsage/contextUsageModel';
import {
  CONTEXT_USAGE_CATEGORY_KEYS,
  getContextUsageCategoryDefinition,
} from '../../features/contextUsage/contextUsageCategories';
import './ContextUsageIndicator.css';

const VIEWPORT_GAP = 8;
const TOOLTIP_GAP = 5;
const TOOLTIP_ALIGN_OFFSET = 3;
const DETAIL_GAP = 7;

function formatCumulativeTokens(value: number): string {
  return `${(value / 1_000).toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}K`;
}

function useElementWidth(ref: RefObject<HTMLElement | null>, visible: boolean): number {
  const [width, setWidth] = useState(0);

  useLayoutEffect(() => {
    if (!visible) {
      setWidth(0);
      return;
    }

    const element = ref.current;
    if (!element) return;

    const updateWidth = () => setWidth(element.getBoundingClientRect().width);
    updateWidth();

    const observer = new ResizeObserver(updateWidth);
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref, visible]);

  return width;
}

function getPopoverStyle(anchor: DOMRect, width: number, gap: number, alignOffset = 0): CSSProperties {
  const availableWidth = Math.max(window.innerWidth - VIEWPORT_GAP * 2, 0);
  const actualWidth = Math.min(width, availableWidth);
  const left = Math.min(
    Math.max(anchor.right + alignOffset - actualWidth, VIEWPORT_GAP),
    Math.max(window.innerWidth - actualWidth - VIEWPORT_GAP, VIEWPORT_GAP),
  );
  return {
    left,
    top: anchor.top - gap,
    transform: 'translateY(-100%)',
    maxHeight: `calc(${anchor.top}px - ${gap}px - ${VIEWPORT_GAP}px)`,
  };
}

export function ContextUsageIndicator() {
  const { t } = useTranslation();
  const activeSessionId = useChatStore((state) => state.activeSessionId);
  const mode = useSessionStore((state) => state.runtimes[activeSessionId ?? '']?.mode ?? 'agent');
  const snapshot = useSessionStore((state) => state.runtimes[activeSessionId ?? '']?.contextUsageSnapshot ?? null);
  const tokenUsageSnapshot = useSessionStore((state) => state.runtimes[activeSessionId ?? '']?.tokenUsageSnapshot ?? null);
  const rate = snapshot?.context_window.occupancy_rate ?? null;
  const used = snapshot?.context_window.input_tokens ?? null;
  const limit = snapshot?.context_window.limit_tokens ?? null;
  const cacheRate = snapshot?.session_kv_cache_hit_rate ?? null;
  const tokenRows = tokenUsageSnapshot && tokenUsageSnapshot.revision > 0
    ? ([
      ['main', tokenUsageSnapshot.main, 'chat.contextUsage.mainAgentTokens'],
      ['others', tokenUsageSnapshot.others, 'chat.contextUsage.otherAgentTokens'],
    ] as const).filter(([, usage]) => usage.input_tokens !== null || usage.output_tokens !== null
      || usage.total_tokens !== undefined || usage.cached_input_tokens !== undefined
      || usage.reasoning_output_tokens !== undefined || usage.cache_write_input_tokens !== undefined)
    : [];
  const hasMetrics = rate !== null || used !== null || limit !== null || cacheRate !== null
    || Object.keys(snapshot?.parts ?? {}).length > 0 || tokenRows.length > 0;

  const triggerRef = useRef<HTMLButtonElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const [anchor, setAnchor] = useState<DOMRect | null>(null);
  const [isHovered, setIsHovered] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const [detailSessionId, setDetailSessionId] = useState<string | null>(null);

  const detailOpen = detailSessionId !== null && detailSessionId === activeSessionId;
  const tooltipOpen = Boolean(hasMetrics && !detailOpen && (isHovered || isFocused));
  const tooltipWidth = useElementWidth(tooltipRef, tooltipOpen);
  const detailWidth = useElementWidth(dialogRef, detailOpen);

  const updateAnchor = useCallback(() => {
    const nextAnchor = triggerRef.current?.getBoundingClientRect();
    if (nextAnchor) setAnchor(nextAnchor);
  }, []);

  const closeDetail = useCallback((restoreFocus: boolean) => {
    setDetailSessionId(null);
    if (restoreFocus) {
      window.requestAnimationFrame(() => triggerRef.current?.focus());
    }
  }, []);

  const openDetail = useCallback(() => {
    updateAnchor();
    setDetailSessionId(activeSessionId);
  }, [activeSessionId, updateAnchor]);

  useEffect(() => {
    setDetailSessionId(null);
    setIsHovered(false);
    setIsFocused(false);
  }, [activeSessionId, mode]);

  useEffect(() => {
    if (hasMetrics) return;
    setDetailSessionId(null);
  }, [hasMetrics]);

  useEffect(() => {
    if (!tooltipOpen && !detailOpen) return;
    updateAnchor();
    const handleViewportChange = () => updateAnchor();
    window.addEventListener('resize', handleViewportChange);
    window.addEventListener('scroll', handleViewportChange, true);
    return () => {
      window.removeEventListener('resize', handleViewportChange);
      window.removeEventListener('scroll', handleViewportChange, true);
    };
  }, [detailOpen, tooltipOpen, updateAnchor]);

  useEffect(() => {
    if (!detailOpen) return;
    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeDetail(true);
      }
    };
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (dialogRef.current?.contains(target) || triggerRef.current?.contains(target)) return;
      closeDetail(false);
    };
    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('pointerdown', handlePointerDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('pointerdown', handlePointerDown);
    };
  }, [closeDetail, detailOpen]);

  if ((mode !== 'agent' && mode !== 'team') || !activeSessionId
    || !hasMetrics) return null;

  const displayRate = rate === null ? null : formatContextPercent(rate);
  const ringPercent = rate === null ? null : getContextRingPercent(rate);
  const overviewUsed = used === null ? null : formatContextTokens(used);
  const overviewLimit = limit === null ? null : formatContextLimitTokens(limit);
  const displayCacheRate = cacheRate === null ? null : formatContextPercent(cacheRate);
  const categories = [
    ...CONTEXT_USAGE_CATEGORY_KEYS.flatMap((key) => {
      const part = snapshot?.parts[key];
      return part ? [part] : [];
    }),
    ...Object.values(snapshot?.parts ?? {}).filter((part) => !getContextUsageCategoryDefinition(part.category)),
  ].map((part) => {
    const definition = getContextUsageCategoryDefinition(part.category);
    return {
      ...part,
      label: definition ? t(definition.labelKey) : part.category,
      color: definition ? definition.color : 'var(--color-text-secondary)',
    };
  });
  const contextMetric = rate !== null && used !== null && limit !== null ? t('chat.contextUsage.hoverMetric', {
    rate: displayRate,
    used: overviewUsed,
    limit: overviewLimit,
  }) : [
    displayRate,
    used !== null ? t('chat.contextUsage.usedTokens', { tokens: overviewUsed }) : null,
    limit !== null ? t('chat.contextUsage.windowTokens', { tokens: overviewLimit }) : null,
  ].filter(Boolean).join(' · ');
  const tooltipStyle = anchor ? getPopoverStyle(anchor, tooltipWidth, TOOLTIP_GAP, TOOLTIP_ALIGN_OFFSET) : undefined;
  const detailStyle = anchor ? getPopoverStyle(anchor, detailWidth, DETAIL_GAP) : undefined;

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="context-usage-trigger"
        aria-label={displayRate === null ? t('chat.contextUsage.usageTitle') : t('chat.contextUsage.ariaLabel', { rate: displayRate })}
        aria-haspopup="dialog"
        aria-expanded={detailOpen}
        aria-describedby={tooltipOpen ? 'context-usage-tooltip' : undefined}
        data-testid="chat-panel-context-usage-trigger"
        onMouseEnter={() => {
          updateAnchor();
          setIsHovered(true);
        }}
        onMouseLeave={() => setIsHovered(false)}
        onFocus={() => {
          updateAnchor();
          setIsFocused(true);
        }}
        onBlur={() => setIsFocused(false)}
        onClick={openDetail}
      >
        <svg className="context-usage-ring" viewBox="0 0 12 12" aria-hidden="true">
          <circle className="context-usage-ring__track" cx="6" cy="6" r="5" pathLength="100" />
          {ringPercent !== null && (
            <circle
              className="context-usage-ring__value"
              cx="6"
              cy="6"
              r="5"
              pathLength="100"
              strokeDasharray={`${ringPercent} ${100 - ringPercent}`}
            />
          )}
        </svg>
      </button>

      {tooltipOpen &&
        anchor &&
        createPortal(
          <div
            ref={tooltipRef}
            id="context-usage-tooltip"
            className="context-usage-tooltip"
            role="tooltip"
            style={tooltipStyle}
            data-testid="chat-panel-context-usage-tooltip"
          >
            {contextMetric && <div className="context-usage-tooltip__row">
              <span>{t('chat.contextUsage.title')}</span>
              <strong>{contextMetric}</strong>
            </div>}
            {!contextMetric && tokenRows.length > 0 && <div className="context-usage-tooltip__row">
              <span>{t('chat.contextUsage.cumulativeTitle')}</span>
            </div>}
            {displayCacheRate !== null && (
              <div className="context-usage-tooltip__row">
                <span>{t('chat.contextUsage.kvCacheHitRate')}</span>
                <strong>{displayCacheRate}</strong>
              </div>
            )}
          </div>,
          document.body,
        )}

      {detailOpen &&
        anchor &&
        createPortal(
          <div
            ref={dialogRef}
            className="context-usage-detail"
            role="dialog"
            aria-modal="false"
            aria-labelledby="context-usage-detail-title"
            style={detailStyle}
            data-testid="chat-panel-context-usage-detail"
          >
            <div className="context-usage-detail__header">
              <h2 id="context-usage-detail-title">{t(contextMetric ? 'chat.contextUsage.detailTitle' : 'chat.contextUsage.usageTitle')}</h2>
              <button
                type="button"
                className="context-usage-detail__close"
                aria-label={t('chat.contextUsage.close')}
                onClick={() => closeDetail(true)}
                data-testid="chat-panel-context-usage-close"
              >
                <X size={16} strokeWidth={2} aria-hidden="true" />
              </button>
            </div>

            <div className="context-usage-detail__content">
              {contextMetric && <div className="context-usage-detail__metric">
                <strong>{contextMetric}</strong>
              </div>}

              {categories.some((category) => category.percentage_of_window !== null) && <div className="context-usage-breakdown" aria-hidden="true">
                {categories
                  .filter((category) => category.percentage_of_window !== null)
                  .map((category) => (
                    <span
                      key={category.category}
                      className="context-usage-breakdown__segment"
                      style={{
                        width: `${category.percentage_of_window! * 100}%`,
                        backgroundColor: category.color,
                      }}
                    />
                  ))}
              </div>}

              {categories.length > 0 ? (
                <div className="context-usage-category-list">
                  {categories.map((category) => (
                    <div className="context-usage-category" key={category.category}>
                      <span
                        className="context-usage-category__dot"
                        style={{ backgroundColor: category.color }}
                        aria-hidden="true"
                      />
                      <span className="context-usage-category__label">{category.label}</span>
                      <strong>{formatContextTokens(category.tokens)}</strong>
                    </div>
                  ))}
                </div>
              ) : null}

              {displayCacheRate !== null && (
                <div className="context-usage-detail__kv">
                  <span>{t('chat.contextUsage.kvCacheHitRate')}</span>
                  <strong>{displayCacheRate}</strong>
                </div>
              )}

              {tokenRows.length > 0 && (
                <div className="context-usage-token-totals" data-testid="chat-panel-context-usage-token-totals">
                  <div
                    className="context-usage-token-totals__title"
                    data-testid="chat-panel-context-usage-token-totals-title"
                  >
                    {t(tokenUsageSnapshot?.scope === 'native' ? 'chat.contextUsage.nativeTitle' : 'chat.contextUsage.cumulativeTitle')}
                  </div>
                  <div className="context-usage-token-totals__table">
                    <span />
                    <span data-testid="chat-panel-context-usage-input-column-label">
                      {tokenRows.some(([, usage]) => usage.input_tokens !== null) && t('chat.contextUsage.inputTokens')}
                    </span>
                    <span className="context-usage-token-totals__separator" aria-hidden="true" />
                    <span data-testid="chat-panel-context-usage-output-column-label">
                      {tokenRows.some(([, usage]) => usage.output_tokens !== null) && t('chat.contextUsage.outputTokens')}
                    </span>
                    {tokenRows.map(([variant, usage, labelKey]) => (
                      <div
                        key={variant}
                        className="context-usage-token-category"
                        data-testid="chat-panel-context-usage-token-category"
                        data-variant={variant}
                      >
                        <div className="context-usage-token-category__label">
                          <span>{t(tokenRows.length > 1 ? labelKey : 'chat.contextUsage.tokens')}</span>
                          {usage.calls_total !== null && (
                            usage.input_calls !== null && usage.input_calls < usage.calls_total
                            || usage.output_calls !== null && usage.output_calls < usage.calls_total
                          ) && (
                            <small data-testid="chat-panel-context-usage-token-partial-status">
                              {t('chat.contextUsage.partialReported')}
                            </small>
                          )}
                        </div>
                        <span>{usage.input_tokens !== null && <strong data-variant="input" data-testid="chat-panel-context-usage-input-tokens">
                          {formatCumulativeTokens(usage.input_tokens)}
                        </strong>}</span>
                        <span className="context-usage-token-totals__separator" aria-hidden="true">{usage.input_tokens !== null && usage.output_tokens !== null ? '/' : ''}</span>
                        <span>{usage.output_tokens !== null && <strong data-variant="output" data-testid="chat-panel-context-usage-output-tokens">
                          {formatCumulativeTokens(usage.output_tokens)}
                        </strong>}</span>
                        {([
                          ['cached_input_tokens', 'chat.contextUsage.cachedInputTokens'],
                          ['cache_write_input_tokens', 'chat.contextUsage.cacheWriteInputTokens'],
                          ['reasoning_output_tokens', 'chat.contextUsage.reasoningOutputTokens'],
                          ['total_tokens', 'chat.contextUsage.totalTokens'],
                        ] as const).map(([key, label]) => usage[key] !== undefined && (
                          <div className="context-usage-token-extra" key={key} data-testid="chat-panel-context-usage-extra" data-variant={key}>
                            <span>{t(label)}</span><strong>{formatContextTokens(usage[key])}</strong>
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
