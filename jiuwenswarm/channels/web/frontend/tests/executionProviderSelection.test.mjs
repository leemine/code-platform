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
globalThis.__providerIconGlob = () => ({});
window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
// jsdom does not provide the browser's native modal methods.
window.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
window.HTMLDialogElement.prototype.close = function () { this.open = false; };
const catalog = [
  { id: 'harness', label: 'Deepagent', available: true, modes: ['agent', 'code', 'team'], reason: null },
  { id: 'opencode-direct', label: 'OpenCode', available: true, modes: ['agent', 'code'], reason: null },
];
const respond = (rows = catalog) => async () => ({ execution_provider_catalog: JSON.stringify(rows) });
globalThis.__providerRpc = respond();
await build({
  stdin: { contents: `export { ExecutionPicker as Selector } from './src/components/ChatPanel/ExecutionPicker';
    export { default as ChatModelSelector } from './src/components/ChatPanel/ChatModelSelector';
    export { CloudRuntimePanel } from './src/features/cloudWorkspace/CloudRuntimePanel';
    export { useSessionStore } from './src/stores/sessionStore';
    export { useAuthStore } from './src/stores/authStore';
    export { resetNewConversationRuntime, registerCreatedConversation } from './src/multi-session/state/newConversationLifecycle';
    export { buildConversationModelPayload } from './src/multi-session/state/conversationModelSelection';
    export { webClient } from './src/services/webClient';
    export { refreshCloudRuntime } from './src/features/cloudWorkspace/useProjectRuntime';
    export { SETTINGS_CONFIG_CHANGED_EVENT } from './src/features/settings/services/settingsContract';
    `, loader: 'tsx', resolveDir: process.cwd() },
  bundle: true, packages: 'external', platform: 'node', format: 'esm',
  outfile: 'node_modules/.cache/execution-provider/test.mjs',
  define: { 'import.meta.env.DEV': 'false', 'import.meta.glob': 'globalThis.__providerIconGlob' },
  loader: { '.css': 'empty', '.svg': 'dataurl', '.png': 'dataurl' },
  plugins: [{ name: 'transport-and-icons', setup(builder) {
    builder.onResolve({ filter: /\.svg\?react$/ }, ({ path }) => ({ path, namespace: 'icons' }));
    builder.onLoad({ filter: /.*/, namespace: 'icons' }, () => ({ contents: 'export default function Icon() {return null}', loader: 'js' }));
  } }],
});
const { createElement, act } = await import('react');
const { createRoot } = await import('react-dom/client');
const { Selector, ChatModelSelector, CloudRuntimePanel, useSessionStore, useAuthStore, resetNewConversationRuntime, registerCreatedConversation, buildConversationModelPayload, webClient, refreshCloudRuntime, SETTINGS_CONFIG_CHANGED_EVENT } = await import('../node_modules/.cache/execution-provider/test.mjs');

webClient.request = (...args) => globalThis.__providerRpc(...args);
useAuthStore.setState({ initialized: true });

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
    globalThis.__providerRpc = respond([]);
    await act(async () => { document.querySelector('[data-testid="chat-panel-execution-retry"]').click(); });
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

test('Code project runtime decorates only its OpenCode option and preserves the Provider ID', async () => {
  const requests = [];
  globalThis.__providerRpc = async (method, params) => {
    if (method !== 'project.runtime.status') return respond()();
    requests.push(params);
    if (params.project_id === 'old-host') throw new Error('Unknown method');
    return {
      provider_id: 'opencode-direct', runtime_profile_id: 'opencode-cloud',
      display_name: 'Review sandbox', available: params.project_id !== 'paused',
    };
  };
  resetNewConversationRuntime({ mode: 'agent', selectedModelName: null, executionProvider: 'harness' });
  const root = createRoot(document.getElementById('root'));
  const trigger = () => document.querySelector('[data-testid="chat-panel-execution-trigger"]');
  const option = () => document.querySelector('[data-variant="opencode-direct"][role="menuitemradio"]');
  async function selectProject(runtimeProjectId) {
    await act(async () => root.render(createElement(Selector, { sessionId: 'new', runtimeProjectId })));
    if (trigger().getAttribute('aria-expanded') !== 'true') await act(async () => trigger().click());
  }
  try {
    await selectProject('paused');
    assert.equal(option().disabled, true);
    await selectProject('current-project');
    assert.equal(option().disabled, false);
    assert.equal(option().textContent, 'OpenCode · Review sandbox');
    await act(async () => option().click());
    assert.equal(useSessionStore.getState().getRuntime('new').executionProvider, 'opencode-direct');
    assert.equal(document.querySelector('[data-testid="chat-panel-execution-label"]').textContent, 'OpenCode · Review sandbox');
    await selectProject('old-host');
    assert.equal(option().disabled, false);
    assert.equal(option().textContent, 'OpenCode');
    await selectProject(null);
    assert.equal(option().textContent, 'OpenCode');
    assert.deepEqual(requests, [{ project_id: 'paused' }, { project_id: 'current-project' }, { project_id: 'old-host' }]);
  } finally {
    await act(async () => { root.unmount(); });
    globalThis.__providerRpc = respond();
  }
});

for (const [provider, profile, label, modelId] of [
  ['opencode-direct', 'opencode-cloud', 'OpenCode', undefined],
  ['codex-direct', 'codex-cloud', 'Codex', 'account-model'],
  ['codex-direct', 'codex-cloud', 'Codex', null],
]) test(`the original Code Provider menu selects a named ${label} device across projects`, async () => {
  const runtimeId = 'a'.repeat(32);
  const defaultDevice = {
    provider_id: 'opencode-direct', runtime_profile_id: 'opencode-cloud',
    display_name: '云端开发环境', available: true, state: 'not_created',
  };
  const device = { ...defaultDevice, provider_id: provider, runtime_profile_id: profile, runtime_id: runtimeId,
    display_name: '日常开发', state: 'ready', model_id: modelId, session_models: provider === 'codex-direct' && modelId === null };
  globalThis.__providerRpc = async (method, params) => {
    if (method === 'cloud.runtime.list') {
      assert.deepEqual(params, {});
      return { runtimes: [defaultDevice, device] };
    }
    if (method === 'project.runtime.status') return defaultDevice;
    return respond([...catalog, { id: 'codex-direct', label: 'Codex', available: true, modes: ['agent', 'code'], reason: null }])();
  };
  resetNewConversationRuntime({ mode: 'agent.code.normal', selectedModelName: null, executionProvider: 'harness' });
  const root = createRoot(document.getElementById('root'));
  const trigger = () => document.querySelector('[data-testid="chat-panel-execution-trigger"]');
  const option = () => document.querySelector(`[data-variant="${runtimeId}"][role="menuitemradio"]`);
  try {
    for (const project of ['payments', 'orders']) {
      await act(async () => root.render(createElement(Selector, { sessionId: 'new', runtimeProjectId: project })));
      await act(async () => trigger().click());
      assert.ok(option().textContent.includes(`${label} · 日常开发`));
      await act(async () => option().click());
      const selected = useSessionStore.getState().getRuntime('new');
      assert.equal(selected.executionRuntimeId, runtimeId);
      assert.equal(selected.executionProvider, provider);
      if (modelId) assert.deepEqual(selected.selectedModelSelection, { type: 'model', id: modelId });
    }
    await act(async () => {
      useSessionStore.getState().setCurrentSession({
        session_id: `device-session-${provider}`, mode: 'agent.code.normal', execution_provider: provider, runtime_id: runtimeId,
      });
      root.render(createElement(Selector, { sessionId: `device-session-${provider}` }));
    });
    assert.equal(document.querySelector('[data-testid="chat-panel-execution-binding"]').textContent, `${label} · 日常开发`);
  } finally {
    await act(async () => root.unmount());
    globalThis.__providerRpc = respond();
  }
});

test('Codex starts without a model and selects an account model in the Code composer', async () => {
  const runtimeId = 'c'.repeat(32);
  const device = { provider_id: 'codex-direct', runtime_profile_id: 'codex-cloud', runtime_id: runtimeId,
    display_name: 'Backend review', available: true, state: 'ready', session_models: true, model_id: null };
  const templates = [
    { runtime_profile_id: 'opencode-cloud', cpu: 1000, memory: 4096, available: true },
    { runtime_profile_id: 'codex-cloud', cpu: 1000, memory: 4096, available: true, default_session_models: true },
  ];
  const requests = [];
  const used = [];
  const accountModels = [
    { model_id: 'account-model', model_name: 'Account default', model_provider: 'openai' },
    { model_id: 'alternate-model', model_name: 'Account alternate', model_provider: 'openai' },
    { model_id: 'unsupported-model', model_name: 'Unsupported', model_provider: 'anthropic' },
  ];
  globalThis.__providerRpc = async (method, params) => {
    requests.push({ method, params });
    if (method === 'cloud.runtime.list') return { runtimes: [device], templates };
    if (method === 'models.list') return { models: accountModels };
    if (method === 'cloud.runtime.models') {
      return { model_ids: ['account-model', 'alternate-model'], default_model_id: 'account-model' };
    }
    return { ...device, start_failed: false };
  };
  const root = createRoot(document.getElementById('root'));
  const element = (testId) => document.querySelector(`[data-testid="${testId}"]`);
  try {
    await act(async () => root.render(createElement(CloudRuntimePanel, {
      templates, runtimes: [], remote: false, onUse: (runtime) => used.push(runtime),
    })));
    await act(async () => element('cloud-workspace-runtime-create').click());
    const codex = document.querySelector('[data-testid="cloud-workspace-runtime-profile"][data-variant="codex-cloud"]');
    assert.ok(codex);
    assert.equal(document.querySelectorAll('[data-testid="cloud-workspace-runtime-profile-resources"]').length, 2);
    await act(async () => codex.click());
    assert.equal(codex.checked, true);
    assert.equal(element('cloud-workspace-runtime-model-trigger'), null);
    assert.equal(requests.some(req => req.method === 'cloud.runtime.models' || req.method === 'models.list'), false);
    const input = element('cloud-workspace-runtime-device-name');
    await act(async () => {
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(input, 'Backend review');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await act(async () => element('cloud-workspace-runtime-create-submit').click());
    const [choice] = requests.filter(req => req.method === 'cloud.runtime.create');
    const { params } = choice;
    assert.deepEqual(Object.keys(params).sort(), ['create_token', 'display_name', 'runtime_profile_id']);
    assert.equal(params.runtime_profile_id, 'codex-cloud');
    assert.equal(params.display_name, 'Backend review');
    assert.match(params.create_token, /^[a-f0-9]{32}$/);
    await act(async () => root.render(createElement(CloudRuntimePanel, {
      templates, runtimes: [device], remote: false, onUse: (runtime) => used.push(runtime),
    })));
    assert.equal(element('cloud-workspace-runtime-provider').textContent, 'Codex');
    await act(async () => element('cloud-workspace-runtime-use').click());
    assert.deepEqual(used, [device]);
    await act(async () => {
      resetNewConversationRuntime({ mode: 'agent.code.normal', selectedModelName: null, executionProvider: 'harness' });
      useSessionStore.setState({ availableModels: accountModels, chatAvailableModels: accountModels });
      useSessionStore.getState().setExecutionProvider('new', 'codex-direct', runtimeId);
      root.render(createElement(ChatModelSelector, { sessionId: 'new' }));
    });
    const trigger = element('chat-panel-model-selector-trigger');
    assert.equal(trigger.disabled, false);
    await act(async () => trigger.click());
    const menu = element('chat-panel-model-selector-menu');
    assert.equal(menu.querySelector('[data-variant="unsupported-model"]'), null);
    const alternate = menu.querySelector('[data-variant="alternate-model"]');
    assert.ok(alternate);
    await act(async () => alternate.click());
    assert.equal(element('chat-panel-model-selector-label').textContent, 'Account alternate');
    assert.equal(useSessionStore.getState().getRuntime('new').executionRuntimeId, runtimeId);
    assert.deepEqual(useSessionStore.getState().getModelSelectionPayload('new'), {
      execution_provider: 'codex-direct', model_selection: { type: 'model', id: 'alternate-model' },
    });

    await act(async () => useSessionStore.getState().setExecutionProvider('new', 'codex-direct'));
    await act(async () => element('chat-panel-model-selector-trigger').click());
    const defaultRuntimeMenu = element('chat-panel-model-selector-menu');
    assert.equal(defaultRuntimeMenu.querySelector('[data-variant="unsupported-model"]'), null);
    await act(async () => defaultRuntimeMenu.querySelector('[data-variant="alternate-model"]').click());
    assert.equal(element('chat-panel-model-selector-label').textContent, 'Account alternate');
    assert.ok(!useSessionStore.getState().getRuntime('new').executionRuntimeId);
    assert.deepEqual(useSessionStore.getState().getModelSelectionPayload('new'), {
      execution_provider: 'codex-direct', model_selection: { type: 'model', id: 'alternate-model' },
    });

    const localFetch = globalThis.fetch;
    const directRpc = globalThis.__providerRpc;
    const desktop = window.jiuwenDesktop;
    try {
      window.jiuwenDesktop = { apiBase: 'http://localhost' };
      globalThis.fetch = async () => ({
        ok: true, json: async () => ({ enabled: true, authenticated: true, kind: 'local' }),
      });
      globalThis.__providerRpc = async (method, params) => {
        if (method === 'cloud.runtime.list' && !params.execution_target) throw new Error('Local runtime catalog unavailable');
        return directRpc(method, params);
      };
      const priorRequests = requests.length;
      await act(async () => refreshCloudRuntime());
      assert.ok(requests.slice(priorRequests).some(req =>
        req.method === 'cloud.runtime.list' && req.params.execution_target === 'cloud'));
      assert.equal(requests.slice(priorRequests).some(req => req.method === 'cloud.runtime.models'), false);
      await act(async () => element('chat-panel-model-selector-trigger').click());
      assert.ok(element('chat-panel-model-selector-menu').querySelector('[data-variant="unsupported-model"]'));
    } finally {
      globalThis.fetch = localFetch;
      globalThis.__providerRpc = directRpc;
      window.jiuwenDesktop = desktop;
    }
  } finally {
    await act(async () => root.unmount());
    globalThis.__providerRpc = respond();
  }
});

test('legacy Codex templates keep the account model picker in the runtime dialog', async () => {
  const runtimeId = 'c'.repeat(32);
  const device = { provider_id: 'codex-direct', runtime_profile_id: 'codex-cloud', runtime_id: runtimeId,
    display_name: 'Backend review', available: true, state: 'ready', model_id: 'alternate-model' };
  const templates = [
    { runtime_profile_id: 'opencode-cloud', cpu: 1000, memory: 4096, available: true },
    { runtime_profile_id: 'codex-cloud', cpu: 1000, memory: 1024, available: true, supports_model_selection: true },
  ];
  const requests = [];
  const used = [];
  globalThis.__providerRpc = async (method, params) => {
    requests.push({ method, params });
    if (method === 'models.list') {
      return { models: [
        { model_id: 'account-model', model_name: 'Account default', model_provider: 'openai' },
        { model_id: 'alternate-model', model_name: 'Account alternate', model_provider: 'openai' },
        { model_id: 'unsupported-model', model_name: 'Unsupported', model_provider: 'anthropic' },
      ] };
    }
    if (method === 'cloud.runtime.models') {
      return { model_ids: ['account-model', 'alternate-model'], default_model_id: 'account-model' };
    }
    return { ...device, start_failed: false };
  };
  const root = createRoot(document.getElementById('root'));
  const element = (testId) => document.querySelector(`[data-testid="${testId}"]`);
  try {
    await act(async () => root.render(createElement(CloudRuntimePanel, {
      templates, runtimes: [], remote: false, onUse: (runtime) => used.push(runtime),
    })));
    await act(async () => element('cloud-workspace-runtime-create').click());
    const codex = document.querySelector('[data-testid="cloud-workspace-runtime-profile"][data-variant="codex-cloud"]');
    assert.ok(codex);
    await act(async () => codex.click());
    assert.equal(element('cloud-workspace-runtime-model-label').textContent, 'Account default');
    await act(async () => element('cloud-workspace-runtime-model-trigger').click());
    const menu = element('cloud-workspace-runtime-model-menu');
    assert.ok(menu.closest('dialog'));
    assert.equal(menu.querySelector('[data-variant="unsupported-model"]'), null);
    const alternate = menu.querySelector('[data-variant="alternate-model"]');
    assert.ok(alternate);
    await act(async () => alternate.click());
    assert.equal(element('cloud-workspace-runtime-model-label').textContent, 'Account alternate');
    const input = element('cloud-workspace-runtime-device-name');
    await act(async () => {
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(input, 'Backend review');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await act(async () => element('cloud-workspace-runtime-create-submit').click());
    const [choice] = requests.filter(req => req.method === 'cloud.runtime.create');
    const { params } = choice;
    assert.deepEqual(Object.keys(params).sort(), ['create_token', 'display_name', 'model_id', 'runtime_profile_id']);
    assert.equal(params.runtime_profile_id, 'codex-cloud');
    assert.equal(params.display_name, 'Backend review');
    assert.equal(params.model_id, 'alternate-model');
    assert.match(params.create_token, /^[a-f0-9]{32}$/);
    await act(async () => root.render(createElement(CloudRuntimePanel, {
      templates, runtimes: [device], remote: false, onUse: (runtime) => used.push(runtime),
    })));
    assert.equal(element('cloud-workspace-runtime-provider').textContent, 'Codex');
    await act(async () => element('cloud-workspace-runtime-use').click());
    assert.deepEqual(used, [device]);
  } finally {
    await act(async () => root.unmount());
    globalThis.__providerRpc = respond();
  }
});
