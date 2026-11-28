import { createRoot } from 'react-dom/client'
import { App } from '../vendor/panel/src/client/app.tsx'
import { en, zh } from '../vendor/panel/src/client/locales.ts'
import type { T } from '../vendor/panel/src/client/text.ts'

const language = navigator.language.startsWith('zh') ? 'zh' : 'en'
const messages: Record<string, string> = language === 'zh' ? zh : en
const translate: T = (key, values) => (messages[key] ?? key).replace(/\{(\w+)\}/g,
  (token, name) => String(values?.[name] ?? token))

document.documentElement.lang = language
const parent = window.top ?? window
createRoot(document.getElementById('superagent-panel')!).render(
  <App t={translate} deploymentForm={undefined} openSession={async id => {
    parent.location.assign('/chat/' + encodeURIComponent(id) + '?application=superagent')
  }} />,
)

const aliases = {
  'bg-base': 'surface-content',
  'bg-layer-1': 'surface-card',
  'bg-layer-2': 'surface-muted',
  'bg-layer-3': 'surface-elevated',
  'bg-mask-1': 'surface-highlight',
  'bg-module-platform': 'surface-page',
  'border-l2': 'border-default',
  'border-l3': 'border-card',
  'border-l4': 'border-strong',
  'brand-primary': 'text-link',
  'button-ghost-active-border': 'border-accent',
  'button-ghost-active-fill': 'surface-highlight',
  'button-primary-fill': 'action-primary',
  'button-primary-hover': 'action-primary-hover',
  'interactive-bg-active': 'surface-highlight',
  'interactive-bg-hover': 'surface-hover',
  'label-caption': 'text-placeholder',
  'label-dimmed': 'text-weak',
  'label-primary': 'text-primary',
  'label-primary-foreground': 'action-primary-text',
  'label-secondary': 'text-secondary',
  'label-tertiary': 'text-tertiary',
  link: 'text-link',
  'state-business-primary': 'text-link',
  'state-error-primary': 'feedback-danger',
  'state-idle-primary': 'text-secondary',
  'state-success-primary': 'feedback-success',
  'state-warn-primary': 'feedback-warning',
  'toast-bg': 'surface-popover',
  'tooltip-bg': 'surface-popover',
}
const parentRoot = parent.document.documentElement
const syncTheme = () => {
  const style = parent.getComputedStyle(parentRoot)
  for (const [alias, name] of Object.entries(aliases)) {
    const value = style.getPropertyValue('--color-' + name)
    if (value.trim()) document.documentElement.style.setProperty('--dsw-alias-' + alias, value)
  }
}
syncTheme()
if (parent !== window) {
  const observer = new MutationObserver(syncTheme)
  observer.observe(parentRoot, { attributes: true, attributeFilter: ['data-theme', 'data-color-mode'] })
  window.addEventListener('pagehide', () => observer.disconnect(), { once: true })
}
