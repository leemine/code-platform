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
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, HTMLElement: dom.window.HTMLElement, Node: dom.window.Node, localStorage: dom.window.localStorage, sessionStorage: dom.window.sessionStorage, Event: dom.window.Event, CustomEvent: dom.window.CustomEvent, IS_REACT_ACT_ENVIRONMENT: true, BroadcastChannel: undefined, requestAnimationFrame: dom.window.requestAnimationFrame.bind(dom.window), cancelAnimationFrame: dom.window.cancelAnimationFrame.bind(dom.window) })) Object.defineProperty(globalThis, key, { value, writable: true, configurable: true });
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
  await mount(); assert.equal(query('trigger').textContent, 'TE'); assert.equal(query('trigger').getAttribute('aria-label'),'test-user');
  await click('trigger'); assert.match(query('name').textContent, /test-user/);
  assert.equal(document.body.textContent.includes('同步项目目录'), false);
  await click('menu-logout'); assert.ok(query('form')); assert.equal(query('identity'), null); assert.equal(query('trigger').getAttribute('aria-label'),'登录');
  assert.ok(calls.every(row => ['status', 'logout'].includes(row.action)));
});

test('an account change discards a late previous identity response', async () => {
  let finish, first = true;
  handler = async () => first ? new Promise(resolve => { finish = resolve; }) : { enabled: true, authenticated: false, kind: 'local' };
  await mount(); first = false;
  await act(async () => api.notifyLocalCloudAccountChange()); await tick();
  await act(async () => finish(identity('local'))); await tick();
  assert.equal(query('trigger').textContent, ''); assert.equal(query('trigger').getAttribute('aria-label'), '登录'); assert.ok(query('trigger').querySelector('svg'));
});

test('unavailable service offers retry while an absent optional service stays hidden', async () => {
  handler = async () => { throw new Error('unavailable'); };
  await mount(); await click('trigger'); assert.ok(query('error')); assert.ok(query('retry'));
  handler = async () => ({ enabled: false }); await click('retry'); assert.equal(query('trigger'), null);
  assert.ok(calls.every(row => row.action === 'status'));
});


test('workspace login request uses the original dialog and reports cancellation without navigation', async () => {
  handler = async () => ({ enabled: true, authenticated: false, kind: 'local' });
  await mount(); const result = []; const href = window.location.href;
  await act(async () => api.requestLocalCloudLogin(value => result.push(value))); await tick();
  assert.equal(query('dialog').closest('dialog').open, true);
  await click('close'); assert.deepEqual(result, [false]); assert.equal(window.location.href, href);
});

test('successful requested login closes the dialog and resumes the view once', async () => {
  let authenticated = false;
  handler = async action => { if(action === 'login') authenticated = true; return { enabled: true, authenticated, kind: 'local' }; };
  await mount(); const result = [];
  await act(async () => api.requestLocalCloudLogin(value => result.push(value))); await tick();
  for(const [id,value] of [['username','test-user'],['password','test-secret']]) await act(async()=>{const input=query(id);Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(input,value);input.dispatchEvent(new window.Event('input',{bubbles:true}));});
  await click('login'); assert.deepEqual(result, [true]); assert.equal(query('dialog').closest('dialog').open, false); assert.equal(localStorage.length, 0);
});


test('same-document credential notifications are delivered once while other tabs still invalidate', () => {
  const channels = []; const prior = globalThis.BroadcastChannel;
  globalThis.BroadcastChannel = class {
    constructor(){ channels.push(this); }
    postMessage(data){ for(const channel of channels) if(channel !== this) channel.onmessage?.({data}); }
    close(){}
  };
  let count = 0; const stop = api.onLocalCloudAccountChange(() => count++);
  try {
    api.notifyLocalCloudAccountChange(); assert.equal(count, 1);
    channels[0].onmessage({data:{type:'changed',sender:'other-document'}}); assert.equal(count, 2);
    channels[0].onmessage({data:'changed'}); assert.equal(count, 3);
  } finally { stop(); globalThis.BroadcastChannel = prior; }
});


test('a pending action can continue after another tab signs in', async () => {
  await mount(); const result=[];
  await act(async()=>api.requestLocalCloudLogin(value=>result.push(value)));await tick();
  assert.deepEqual(result,[true]);assert.equal(query('dialog').closest('dialog').open,false);assert.equal(calls.some(row=>row.action==='login'),false);
});


test('local account avatar uses the cloud style and keeps logout failure visible', async () => {
  handler = async action => { if(action==='logout') throw new Error('offline'); return identity('local'); };
  await mount(); assert.equal(query('trigger').classList.contains('cloud-workspace-avatar'),true);
  await click('trigger'); assert.equal(query('trigger').getAttribute('aria-expanded'),'true');
  await click('menu-logout'); assert.equal(query('dialog').closest('dialog').open,true); assert.ok(query('error')); assert.equal(query('trigger').textContent,'TE');
});


test('concurrent status reads share only the unfinished request and account changes invalidate it', async () => {
  let resolveOld;
  handler = () => new Promise(resolve => { resolveOld = resolve; });
  const first = api.localCloudAccountRequest('status');
  const joined = api.localCloudAccountRequest('status');
  assert.equal(first, joined);
  assert.equal(calls.length, 1);
  api.notifyLocalCloudAccountChange();
  handler = async () => ({ enabled: true, authenticated: false });
  const fresh = api.localCloudAccountRequest('status');
  assert.notEqual(fresh, first);
  assert.equal((await fresh).authenticated, false);
  resolveOld(identity('local'));
  await first;
  await api.localCloudAccountRequest('status');
  assert.equal(calls.length, 3, 'settled identities must not be cached');
});

test('failed status reads are not retained and login starts a fresh identity generation', async () => {
  handler = async () => { throw new Error('temporary failure'); };
  await assert.rejects(api.localCloudAccountRequest('status'), /temporary failure/);
  handler = async () => identity('local');
  await api.localCloudAccountRequest('status');
  await api.localCloudAccountRequest('login', { username: 'test-user', password: 'test-secret' });
  await api.localCloudAccountRequest('status');
  assert.deepEqual(calls.map(c => c.action), ['status', 'status', 'login', 'status']);
});
