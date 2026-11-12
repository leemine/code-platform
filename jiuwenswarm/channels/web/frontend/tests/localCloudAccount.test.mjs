import test, { before, after, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdir, writeFile, readFile } from 'node:fs/promises';
import { JSDOM } from 'jsdom';
import { act, createElement as h } from 'react';
import i18next from 'i18next';
import { I18nextProvider } from 'react-i18next';
let dom, root, createRoot, api, handler, calls;
const query = id => document.querySelector(`[data-testid="cloud-workspace-local-account-${id}"]`);
const tick = () => act(async () => { await new Promise(resolve => setTimeout(resolve, 10)); });
const click = async id => { assert.ok(query(id), id); await act(async () => query(id).click()); await tick(); };
const identity = kind => ({ enabled: true, authenticated: true, kind, username: 'test-user', scope: ['authority', 'account'] });
const empty = { items: [], sources: [], selection: [], account_complete: false, status: { state: 'current' }, version: 'one', total: 0, next_offset: null };
before(async () => {
  dom = new JSDOM('<div id="root"></div>', { url: 'https://cloud.test', pretendToBeVisual: true });
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, HTMLElement: dom.window.HTMLElement, Node: dom.window.Node, localStorage: dom.window.localStorage, sessionStorage: dom.window.sessionStorage, Event: dom.window.Event, IS_REACT_ACT_ENVIRONMENT: true, BroadcastChannel: undefined, requestAnimationFrame: dom.window.requestAnimationFrame.bind(dom.window), cancelAnimationFrame: dom.window.cancelAnimationFrame.bind(dom.window) })) Object.defineProperty(globalThis, key, { value, writable: true, configurable: true });
  window.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  window.HTMLDialogElement.prototype.close = function () { this.open = false; };
  ({ createRoot } = await import('react-dom/client'));
  const result = await build({ stdin: { contents: "export * from './src/features/cloudWorkspace/LocalCloudAccount'; export * from './src/features/cloudWorkspace/localCloudAccountClient';", resolveDir: process.cwd(), loader: 'tsx' }, bundle: true, packages: 'external', platform: 'node', format: 'esm', write: false, loader: { '.css': 'empty', '.svg': 'dataurl' }, define: { 'import.meta.env': '{}' } });
  await mkdir('node_modules/.cache/local-cloud-account', { recursive: true });
  await writeFile('node_modules/.cache/local-cloud-account/test.mjs', result.outputFiles[0].text);
  api = await import('../node_modules/.cache/local-cloud-account/test.mjs');
  await i18next.init({ lng: 'zh', resources: { zh: { translation: JSON.parse(await readFile('src/i18n/locales/zh.json', 'utf8')) } } });
});
beforeEach(() => {
  localStorage.clear(); calls = [];
  handler = async action => action === 'status' ? identity('local') : action === 'choices' ? { projects: [{ native_id: 'project-one', name: 'Original project' }] } : empty;
  globalThis.fetch = async (url, options) => {
    const action = url.split('/').at(-1), body = options.body ? JSON.parse(options.body) : undefined;
    calls.push({ action, body, options });
    const value = await handler(action, body);
    return { ok: !value.httpStatus, status: value.httpStatus || 200, json: async () => value };
  };
  root = createRoot(document.getElementById('root'));
});
afterEach(async () => { await act(async () => root.unmount()); });
after(() => dom.window.close());
async function mount() { await act(async () => root.render(h(I18nextProvider, { i18n: i18next }, h(api.LocalCloudAccount)))); await tick(); }


test('login transport uses the same-origin session and never stores credentials', async () => {
  await api.localCloudAccountRequest('login', { username: 'test-user', password: 'test-secret' });
  assert.deepEqual(calls[0].body, { username: 'test-user', password: 'test-secret' });
  assert.equal(calls[0].options.credentials, 'same-origin');
  assert.equal(calls[0].options.headers['X-Jiuwen-Sync'], '1');
  assert.equal(localStorage.length, 0);
});

test('account footer logs out without exposing or calling inventory operations', async () => {
  let loggedIn = true;
  handler = async action => {
    if (action === 'logout') { loggedIn = false; return { authenticated: false }; }
    return { ...identity('local'), authenticated: loggedIn, cloud_origin: 'https://cloud.test' };
  };
  await mount(); assert.equal(query('trigger').textContent, 'test-user');
  await click('trigger'); assert.match(query('identity').textContent, /test-user/);
  assert.equal(document.body.textContent.includes('同步项目目录'), false);
  await click('logout'); assert.ok(query('form')); assert.equal(query('identity'), null);
  assert.ok(calls.every(row => ['status', 'logout'].includes(row.action)));
});

test('an account change discards a late previous identity response', async () => {
  let finish, first = true;
  handler = async () => first ? new Promise(resolve => { finish = resolve; }) : { enabled: true, authenticated: false, kind: 'local' };
  await mount(); first = false;
  await act(async () => api.notifyLocalCloudAccountChange()); await tick();
  await act(async () => finish(identity('local'))); await tick();
  assert.equal(query('trigger').textContent, '登录云账号');
});

test('unavailable service offers retry while an absent optional service stays hidden', async () => {
  handler = async () => { throw new Error('unavailable'); };
  await mount(); await click('trigger'); assert.ok(query('error')); assert.ok(query('retry'));
  handler = async () => ({ enabled: false }); await click('retry'); assert.equal(query('trigger'), null);
  assert.ok(calls.every(row => row.action === 'status'));
});
