import test, { before, after, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdir, writeFile, readFile } from 'node:fs/promises';
import { JSDOM } from 'jsdom';
import { act, createElement as h } from 'react';
import i18next from 'i18next';
import { I18nextProvider } from 'react-i18next';

let dom, root, createRoot, Gate, api, events;
let calls, disconnects, route;
const identity = { enabled: true, authenticated: true, actor_id: 'u_a', subject_id: 'u_a', authority: 'test', session_revision: 'r1', username: 'alice', auth_backend: 'builtin', execution_mode: 'user_instance' };
const response = (value, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
const tick = () => act(async () => { await new Promise(resolve => setTimeout(resolve, 5)); });
const query = (id) => document.querySelector(`[data-testid="${id}"]`);
const phase = () => query('cloud-workspace-gate')?.dataset.phase;
const click = async id => { await act(async () => query(id).click()); await tick(); };

before(async () => {
  dom = new JSDOM('<!doctype html><div id="root"></div>', { url: 'https://cloud.test', pretendToBeVisual: true });
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, HTMLElement: dom.window.HTMLElement, Node: dom.window.Node, localStorage: dom.window.localStorage, sessionStorage: dom.window.sessionStorage, IS_REACT_ACT_ENVIRONMENT: true, BroadcastChannel: undefined })) {
    Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  }
  globalThis.__cloudDisconnect = () => { disconnects += 1; return Promise.resolve(); };
  ({ createRoot } = await import('react-dom/client'));
  const result = await build({
    stdin: { contents: `export { CloudWorkspaceGate } from './src/features/cloudWorkspace/CloudWorkspaceGate'; export * from './src/features/cloudWorkspace/client'; export * from './src/services/organizationCredentialEvents';`, resolveDir: process.cwd(), loader: 'ts' },
    bundle: true, packages: 'external', platform: 'node', format: 'esm', write: false,
    loader: { '.css': 'empty' }, define: { 'import.meta.env': '{}' },
    plugins: [{ name: 'transport-boundary', setup(b) {
      b.onResolve({ filter: /services\/webClient$/ }, () => ({ path: 'transport', namespace: 'cloud-test' }));
      b.onLoad({ filter: /.*/, namespace: 'cloud-test' }, () => ({ contents: 'export const webClient = { disconnect: () => globalThis.__cloudDisconnect() };' }));
    } }],
  });
  await mkdir('node_modules/.cache/cloud-workspace', { recursive: true });
  await writeFile('node_modules/.cache/cloud-workspace/test.mjs', result.outputFiles[0].text);
  api = await import('../node_modules/.cache/cloud-workspace/test.mjs');
  Gate = api.CloudWorkspaceGate;
  await i18next.init({ lng: 'zh', resources: { zh: { translation: JSON.parse(await readFile('src/i18n/locales/zh.json', 'utf8')) } } });
});
beforeEach(() => {
  calls = []; disconnects = 0;
  route = async path => path.endsWith('/status') ? response(identity) : response({ state: 'NEW' });
  globalThis.fetch = async (url, options = {}) => { calls.push({ url, options }); return route(url, options); };
  root = createRoot(document.getElementById('root'));
});
afterEach(async () => { await act(async () => root.unmount()); localStorage.clear(); sessionStorage.clear(); });
after(() => { dom.window.close(); });
async function mount() {
  await act(async () => root.render(h(I18nextProvider, { i18n: i18next }, h(Gate, { children: footer => h('div', { 'data-testid': 'original-app' }, footer) }))));
  await tick();
}

test('explicitly absent legacy endpoint preserves original local App', async () => {
  route = async () => response({}, 404);
  await mount(); assert.ok(query('original-app')); assert.equal(calls.length, 1);
});
test('unauthenticated cloud shows login without mounting original App or creating an instance', async () => {
  route = async () => response({ enabled: true, authenticated: false, registration_enabled: false });
  await mount(); assert.ok(query('auth-login-page')); assert.equal(query('original-app'), null);
  assert.equal(query('auth-registration-toggle'), null); assert.equal(calls.length, 1);
});
test('authority failure and malformed status fail closed with explicit retry', async () => {
  route = async () => response({}, 503);
  await mount(); assert.equal(phase(), 'unavailable'); assert.ok(query('cloud-workspace-retry')); assert.equal(query('original-app'), null);
});
test('first allocation requires entry, uses no selectors, and mounts only after READY', async () => {
  await mount(); assert.equal(phase(), 'entry'); assert.equal(calls.length, 2);
  let finish;
  route = async path => path.endsWith('/ensure') ? new Promise(resolve => { finish = resolve; }) : response(identity);
  await click('cloud-workspace-enter'); assert.equal(phase(), 'preparing'); assert.equal(query('original-app'), null);
  assert.equal(calls.at(-1).options.body, '{}');
  await act(async () => finish(response({ state: 'READY' }))); await tick();
  assert.ok(query('original-app')); assert.equal(query('cloud-workspace-identity').textContent, 'AL');
  assert.equal(query('cloud-workspace-identity').getAttribute('aria-label'), 'alice');
  assert.equal(query('cloud-workspace-account').title, 'alice');
  assert.equal(query('auth-logout-button'), null);
  await click('cloud-workspace-identity');
  assert.equal(query('cloud-workspace-identity').getAttribute('aria-expanded'), 'true');
  assert.equal(query('cloud-workspace-account-name').textContent, 'alice');
  assert.ok(query('auth-logout-button'));
});
test('persisted allocation is rechecked through original ensure; failed readiness never mounts App', async () => {
  route = async path => path.endsWith('/status') ? response(identity) : path.endsWith('/ensure') ? response({}, 503) : response({ state: 'ALLOCATED' });
  await mount(); assert.equal(phase(), 'environmentError'); assert.equal(query('original-app'), null);
  route = async path => path.endsWith('/status') ? response(identity) : response({ state: 'READY' });
  await click('cloud-workspace-retry'); assert.ok(query('original-app'));
  assert.equal(calls.filter(c => c.url.endsWith('/ensure')).length, 2);
});
test('lost logout response closes old connection and exposes retry without claiming success', async () => {
  await mount(); route = async () => response({}, 503);
  await click('auth-logout-button'); assert.equal(phase(), 'logoutFailed'); assert.equal(disconnects, 1); assert.equal(query('original-app'), null);
  assert.ok(query('cloud-workspace-retry'));
});
test('account service failure on focus discards mounted App; no anonymous fallback', async () => {
  route = async path => path.endsWith('/status') ? response(identity) : response({ state: path.endsWith('/ensure') ? 'READY' : 'ALLOCATED' });
  await mount(); assert.ok(query('original-app'));
  route = async () => response({}, 503);
  await act(async () => window.dispatchEvent(new window.Event('focus'))); await tick();
  assert.equal(phase(), 'unavailable'); assert.equal(query('original-app'), null); assert.equal(disconnects, 1);
});
test('late ensure cannot mount App after logout begins', async () => {
  await mount(); let finish;
  route = async path => path.endsWith('/ensure') ? new Promise(resolve => { finish = resolve; }) : path.endsWith('/logout') ? response({}, 503) : response(identity);
  await click('cloud-workspace-enter'); await click('auth-logout-button');
  await act(async () => finish(response({ state: 'READY' }))); await tick();
  assert.equal(phase(), 'logoutFailed'); assert.equal(query('original-app'), null);
});
test('same verified account renewal retains route; another account goes to root', () => {
  const href = 'https://cloud.test/chat/session-a';
  assert.equal(api.organizationCredentialReloadUrl(identity, { ...identity, session_revision: 'r2' }, href), href);
  assert.equal(api.organizationCredentialReloadUrl(identity, { ...identity, actor_id: 'u_b', subject_id: 'u_b' }, href), 'https://cloud.test/');
});
test('account cache cleanup preserves appearance preferences', () => {
  localStorage.setItem('jiuwenclaw_selected_model', 'a'); localStorage.setItem('jiuwenswarm.goal.a', 'private'); localStorage.setItem('theme', 'light');
  sessionStorage.setItem('marketplace_oauth_access_token', 'private');
  api.clearAccountCaches(); assert.equal(localStorage.length, 1); assert.equal(localStorage.getItem('theme'), 'light'); assert.equal(sessionStorage.length, 0);
});
test('cloud request timeout aborts transport and does not imply create cancellation', async () => {
  globalThis.fetch = async (_url, { signal }) => new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(new Error('aborted'))));
  await assert.rejects(api.cloudRequest('environment/ensure', {}, 10), /aborted/);
});
test('malformed identity is rejected before requesting an environment', async () => {
  route = async () => response({ ...identity, session_revision: '' });
  await mount(); assert.equal(phase(), 'unavailable'); assert.equal(calls.length, 1);
});
test('existing login form reports wrong credentials and successful registration returns to sign-in', async () => {
  route = async path => path.endsWith('/status') ? response({ enabled: true, authenticated: false, registration_enabled: true }) : response({}, 401);
  await mount();
  const fill = async (id, value) => act(async () => {
    const input = query(id);
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(input, value);
    input.dispatchEvent(new window.Event('input', { bubbles: true }));
  });
  await fill('auth-login-username-input', 'alice'); await fill('auth-login-password-input', 'test-password');
  await act(async () => query('auth-login-form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }))); await tick();
  assert.ok(query('auth-login-error')); assert.equal(query('original-app'), null);
  assert.deepEqual(JSON.parse(calls.at(-1).options.body), { username: 'alice', password: 'test-password' });
  await click('auth-registration-toggle');
  route = async () => response({}, 201);
  await act(async () => query('auth-login-form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }))); await tick();
  assert.ok(query('auth-registration-notice')); assert.equal(query('auth-login-password-input').value, '');
  assert.equal(query('original-app'), null);
});
test('retry after a known cloud outage cannot downgrade a now-missing endpoint to local mode', async () => {
  await mount();
  route = async () => response({}, 503);
  await act(async () => window.dispatchEvent(new window.Event('focus'))); await tick();
  assert.equal(phase(), 'unavailable');
  route = async () => response({}, 404);
  await click('cloud-workspace-retry');
  assert.equal(phase(), 'unavailable'); assert.equal(query('original-app'), null);
});
