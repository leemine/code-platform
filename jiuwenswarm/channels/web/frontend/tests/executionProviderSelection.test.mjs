import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';

const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', { url: 'http://localhost' });
for (const key of ['window', 'document', 'navigator', 'HTMLElement', 'Element', 'Node', 'MutationObserver', 'Event', 'MouseEvent', 'KeyboardEvent', 'localStorage']) {
  Object.defineProperty(globalThis, key, { value: dom.window[key], configurable: true });
}
globalThis.getComputedStyle = dom.window.getComputedStyle;
globalThis.requestAnimationFrame = (fn) => setTimeout(fn, 0);
globalThis.cancelAnimationFrame = clearTimeout;
globalThis.ResizeObserver = class { observe() {} disconnect() {} unobserve() {} };
window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const catalog = [
  { id: 'harness', label: 'Deepagent', available: true, modes: ['agent', 'code', 'team'], reason: null },
  { id: 'opencode-direct', label: 'OpenCode', available: true, modes: ['agent', 'code'], reason: null },
];
const respond = (rows = catalog) => async () => ({ execution_provider_catalog: JSON.stringify(rows) });
globalThis.__providerRpc = respond();
await build({
  stdin: { contents: `export { ExecutionPicker as Selector } from './src/components/ChatPanel/ExecutionPicker';
    export { useSessionStore } from './src/stores/sessionStore';
    export { resetNewConversationRuntime, registerCreatedConversation } from './src/multi-session/state/newConversationLifecycle';
    export { buildConversationModelPayload } from './src/multi-session/state/conversationModelSelection';
    export { webClient } from './src/services/webClient';
    export { SETTINGS_CONFIG_CHANGED_EVENT } from './src/features/settings/services/settingsContract';
    `, loader: 'tsx', resolveDir: process.cwd() },
  bundle: true, packages: 'external', platform: 'node', format: 'esm',
  outfile: 'node_modules/.cache/execution-provider/test.mjs',
  define: { 'import.meta.env.DEV': 'false' }, loader: { '.css': 'empty', '.svg': 'dataurl', '.png': 'dataurl' },
  plugins: [{ name: 'transport-and-icons', setup(builder) {
    builder.onResolve({ filter: /\.svg\?react$/ }, ({ path }) => ({ path, namespace: 'icons' }));
    builder.onLoad({ filter: /.*/, namespace: 'icons' }, () => ({ contents: 'export default function Icon() {return null}', loader: 'js' }));
  } }],
});
const { createElement, act } = await import('react');
const { createRoot } = await import('react-dom/client');
const { Selector, useSessionStore, resetNewConversationRuntime, registerCreatedConversation, buildConversationModelPayload, webClient, SETTINGS_CONFIG_CHANGED_EVENT } = await import('../node_modules/.cache/execution-provider/test.mjs');

webClient.request = (...args) => globalThis.__providerRpc(...args);

test('external Provider reuses the existing Swarm model selection', () => {
  assert.deepEqual(buildConversationModelPayload({ executionProvider: 'opencode-direct', selectedModelName: 'native-model', selectedModelSelection: { type: 'model', id: 'native-id' } }), { execution_provider: 'opencode-direct', model_selection: { type: 'model', id: 'native-id' } });
  assert.deepEqual(buildConversationModelPayload({ executionProvider: 'harness', selectedModelName: 'native-model' }), { model_name: 'native-model' });
});

test('UI chooses Provider for new conversation and locks existing conversation', async () => {
  resetNewConversationRuntime({ mode: 'agent', selectedModelName: null, executionProvider: 'harness' });
  const root = createRoot(document.getElementById('root'));
  try {
    await act(async () => { root.render(createElement(Selector, { sessionId: 'new' })); });
    const trigger = document.querySelector('[data-testid="chat-panel-execution-trigger"]');
    assert.equal(trigger.disabled, false);
    await act(async () => { trigger.click(); });
    const option = [...document.querySelectorAll('[role="menuitemradio"]')].find((node) => node.textContent.includes('OpenCode'));
    assert.ok(option, 'OpenCode option is rendered');
    await act(async () => { option.click(); });
    assert.equal(useSessionStore.getState().getRuntime('new').executionProvider, 'opencode-direct');
    registerCreatedConversation('bound-session', { mode: 'agent', selectedModelName: null, executionProvider: 'opencode-direct' });
    assert.deepEqual(useSessionStore.getState().getModelSelectionPayload('bound-session'), { execution_provider: 'opencode-direct' });
    await act(async () => { root.render(createElement(Selector, { sessionId: 'bound-session' })); });
    assert.equal(document.querySelector('[data-testid="chat-panel-execution-trigger"]'), null);
    assert.equal(document.querySelector('[data-testid="chat-panel-execution-binding"]').textContent, 'OpenCode');
    // A refreshed session restores the server's durable Provider binding.
    await act(async () => { useSessionStore.getState().setCurrentSession({ session_id: 'restored-session', mode: 'agent', execution_provider: 'opencode-direct' }); });
    assert.equal(useSessionStore.getState().getRuntime('restored-session').executionProvider, 'opencode-direct');
    await act(async () => { useSessionStore.getState().setExecutionProvider('new', 'harness'); });
    assert.equal(useSessionStore.getState().getRuntime('bound-session').executionProvider, 'opencode-direct');
  } finally { await act(async () => { root.unmount(); }); }
});


test('new plugin is selectable without a frontend branch; disabled modes cannot be selected', async () => {
  globalThis.__providerRpc = respond([...catalog,
    { id: 'example', label: 'Example engine', available: true, modes: ['agent'], reason: null },
    { id: 'code-only', label: 'Code only', available: true, modes: ['code'], reason: null },
    { id: 'broken', label: 'Broken', available: false, modes: [], reason: 'unavailable' },
  ]);
  resetNewConversationRuntime({ mode: 'agent', selectedModelName: null, executionProvider: 'harness' });
  const root = createRoot(document.getElementById('root'));
  try {
    await act(async () => { root.render(createElement(Selector, { sessionId: 'new' })); });
    await act(async () => { document.querySelector('[data-testid="chat-panel-execution-trigger"]').click(); });
    const option = (id) => document.querySelector(`[data-testid="chat-panel-execution-option"][data-variant="${id}"]`);
    assert.equal(option('code-only').disabled, true);
    assert.equal(option('broken').disabled, true);
    assert.equal(option('harness').getAttribute('aria-checked'), 'true');
    await act(async () => { option('example').click(); });
    assert.equal(useSessionStore.getState().getRuntime('new').executionProvider, 'example');
    assert.equal(document.querySelector('[data-testid="chat-panel-execution-label"]').textContent, 'Example engine');
    // Refresh must not silently reset a selection when its plugin disappears.
    globalThis.__providerRpc = respond();
    await act(async () => { window.dispatchEvent(new Event(SETTINGS_CONFIG_CHANGED_EVENT)); });
  } finally { await act(async () => { root.unmount(); }); globalThis.__providerRpc = respond(); }
});

test('catalog failure offers retry; keyboard Escape closes the existing menu', async () => {
  resetNewConversationRuntime({ mode: 'agent', selectedModelName: null, executionProvider: 'harness' });
  useSessionStore.getState().setExecutionProvider('new', 'example');
  globalThis.__providerRpc = async () => { throw new Error('offline'); };
  const root = createRoot(document.getElementById('root'));
  try {
    await act(async () => { root.render(createElement(Selector, { sessionId: 'new' })); });
    await act(async () => { document.querySelector('[data-testid="chat-panel-execution-trigger"]').click(); });
    assert.ok(document.querySelector('[data-testid="chat-panel-execution-retry"]'));
    globalThis.__providerRpc = respond();
    await act(async () => { document.querySelector('[data-testid="chat-panel-execution-retry"]').click(); });
    await act(async () => { document.querySelector('[data-testid="chat-panel-execution-trigger"]').click(); });
    assert.ok(document.querySelector('[data-testid="chat-panel-execution-unavailable"]'));
    assert.equal(useSessionStore.getState().getRuntime('new').executionProvider, 'example');
    await act(async () => { document.querySelector('[data-testid="chat-panel-execution-menu"]').dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); });
    assert.equal(document.querySelector('[data-testid="chat-panel-execution-menu"]'), null);
  } finally { await act(async () => { root.unmount(); }); globalThis.__providerRpc = respond(); }
});
