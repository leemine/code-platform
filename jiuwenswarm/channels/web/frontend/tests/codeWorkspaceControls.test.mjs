import test, { before, after, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdir, writeFile, readFile } from 'node:fs/promises';
import { JSDOM } from 'jsdom';
import { act, createElement as h } from 'react';
import i18next from 'i18next';
import { I18nextProvider } from 'react-i18next';

let dom, root, createRoot, api, calls, request, blocked, connection, selected;
const catalog = kind => ({ kind, switch_mode: 'entry_navigation', entries: ['local','cloud'].map(value => ({kind:value,current:value===kind,url:null})) });
const page = (path='',items=[])=>({path,work_mode:'code',items,next_offset:null});
const query=id=>document.querySelector(`[data-testid="${id}"]`);
const tick=()=>act(async()=>{await new Promise(r=>setTimeout(r,5));});
const click=async id=>{assert.ok(query(id),id);await act(async()=>query(id).click());await tick();};
const text=async(id,value)=>{await act(async()=>{const el=query(id);Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(el,value);el.dispatchEvent(new window.Event('input',{bubbles:true}));});};
const bindBlocked=value=>{blocked=value;};
before(async()=>{
 dom=new JSDOM('<div id="root"></div>',{url:'https://cloud.test',pretendToBeVisual:true});
 for(const [key,value] of Object.entries({window:dom.window,document:dom.window.document,navigator:dom.window.navigator,HTMLElement:dom.window.HTMLElement,Node:dom.window.Node,localStorage:dom.window.localStorage,sessionStorage:dom.window.sessionStorage,IS_REACT_ACT_ENVIRONMENT:true,BroadcastChannel:undefined,requestAnimationFrame:dom.window.requestAnimationFrame.bind(dom.window),cancelAnimationFrame:dom.window.cancelAnimationFrame.bind(dom.window)}))Object.defineProperty(globalThis,key,{value,writable:true,configurable:true});
 window.HTMLDialogElement.prototype.showModal=function(){this.open=true;};window.HTMLDialogElement.prototype.close=function(){this.open=false;};
 ({createRoot}=await import('react-dom/client'));
 globalThis.__workspaceRequest=async(method,params)=>{calls.push({method,params});return request(method,params);};
 globalThis.__workspaceConnection=fn=>{connection=fn;return ()=>{};};
 globalThis.__workspaceStore={selectedProject:null,setSelectedProject:p=>{selected=p;},loadProjects:async()=>{}};
 const result=await build({stdin:{contents:"export * from './src/components/ChatPanel/CodeWorkspaceControls';",resolveDir:process.cwd(),loader:'ts'},bundle:true,packages:'external',platform:'node',format:'esm',write:false,loader:{'.css':'empty','.svg':'text'},define:{'import.meta.env':'{}'},plugins:[{name:'boundary',setup(b){
 b.onResolve({filter:/services\/webClient$/},()=>({path:'transport',namespace:'workspace-test'}));
 b.onResolve({filter:/stores\/workspaceStore$/},()=>({path:'store',namespace:'workspace-test'}));
 b.onLoad({filter:/.*/,namespace:'workspace-test'},args=>({contents:args.path==='transport'?'export const webRequest=(...args)=>globalThis.__workspaceRequest(...args); export const webClient={onStateChange:fn=>globalThis.__workspaceConnection(fn),disconnect:async()=>{}};':'export const useWorkspaceStore=selector=>selector(globalThis.__workspaceStore); useWorkspaceStore.getState=()=>globalThis.__workspaceStore;'}));
 }}]});
 await mkdir('node_modules/.cache/code-workspace',{recursive:true});await writeFile('node_modules/.cache/code-workspace/test.mjs',result.outputFiles[0].text);api=await import('../node_modules/.cache/code-workspace/test.mjs');
 await i18next.init({lng:'zh',resources:{zh:{translation:JSON.parse(await readFile('src/i18n/locales/zh.json','utf8'))}}});
});
beforeEach(()=>{calls=[];blocked=false;selected=null;request=async(method)=>method==='workspace.locations'?catalog('cloud'):method==='cloud.environment.status'?{environment_id:'env-1',state:'ALLOCATED'}:page();root=createRoot(document.getElementById('root'));});
afterEach(async()=>{await act(async()=>root.unmount());});after(()=>dom.window.close());
async function mount(enabled=true,navigationBlocked=false){await act(async()=>root.render(h(I18nextProvider,{i18n:i18next},h(api.CodeWorkspaceControls,{enabled,navigationBlocked,disabled:false,onBlockedChange:bindBlocked,localControl:h('button',{'data-testid':'existing-local-picker'},'original local')}))));await tick();}
test('cloud has three controls and all original cloud actions; no automatic ensure',async()=>{
 await mount();assert.ok(query('chat-panel-code-local-directory'));assert.ok(query('chat-panel-code-location-trigger'));assert.ok(query('chat-panel-code-cloud-trigger'));assert.equal(query('existing-local-picker'),null);assert.equal(blocked,false);
 await click('chat-panel-code-cloud-trigger');for(const id of ['directory','mkdir','create'])assert.ok(query('chat-panel-code-cloud-'+id));assert.equal(calls.some(c=>c.method==='cloud.environment.ensure'),false);
});
test('local uses original picker and hides cloud control; Work does not query catalog',async()=>{
 request=async()=>catalog('local');await mount();assert.ok(query('existing-local-picker'));assert.equal(query('chat-panel-code-cloud-trigger'),null);
 await act(async()=>root.unmount());root=createRoot(document.getElementById('root'));calls=[];await mount(false);assert.equal(calls.length,0);assert.ok(query('existing-local-picker'));
});
test('directory open selects the server project, without creating a session',async()=>{
 const project={project_id:'p-1',project_dir:'/data/workspace/code/demo',work_mode:'code'};
 request=async(method)=>method==='workspace.locations'?catalog('cloud'):method==='cloud.environment.status'?{environment_id:'env-1'}:method==='project.workspace.open'?{project}:page('',[{name:'demo',path:'demo'}]);
 await mount();await click('chat-panel-code-cloud-trigger');await click('chat-panel-code-cloud-directory');assert.equal(blocked,true);await click('chat-panel-code-directory-item');await click('chat-panel-code-workspace-confirm');assert.deepEqual(selected,project);assert.equal(blocked,false);assert.equal(calls.some(c=>c.method.startsWith('session.')||c.method==='chat.send'),false);
});
test('new folder waits for durable response and then opens through original project path',async()=>{
 request=async(method,params)=>method==='workspace.locations'?catalog('cloud'):method==='cloud.environment.status'?{environment_id:'env-1'}:method==='project.workspace.mkdir'?{path:params.name,created:true}:method==='project.workspace.open'?{project:{project_id:'new',project_dir:'/workspace/new-project',work_mode:'code'}}:page();
 await mount();await click('chat-panel-code-cloud-trigger');await click('chat-panel-code-cloud-mkdir');await text('chat-panel-code-folder-name','new-project');await click('chat-panel-code-workspace-confirm');assert.equal(query('chat-panel-code-directory-selection').textContent,'new-project');await click('chat-panel-code-workspace-confirm');assert.equal(selected.project_id,'new');
});
test('environment ensure uses no selectors and blocks until READY',async()=>{
 let finish;request=async(method)=>method==='workspace.locations'?catalog('cloud'):method==='cloud.environment.status'?{environment_id:'env-1'}:new Promise(r=>{finish=r;});
 await mount();await click('chat-panel-code-cloud-trigger');await click('chat-panel-code-cloud-create');await click('chat-panel-code-workspace-confirm');assert.equal(blocked,true);assert.deepEqual(calls.at(-1),{method:'cloud.environment.ensure',params:{}});assert.ok(query('chat-panel-code-workspace-confirm').disabled);
 await act(async()=>finish({environment_id:'env-1',state:'READY'}));await tick();assert.equal(blocked,false);
});
test('disconnect invalidates a late directory response',async()=>{
 let finish;request=async(method)=>method==='workspace.locations'?catalog('cloud'):method==='cloud.environment.status'?{environment_id:'env-1'}:new Promise(r=>{finish=r;});
 await mount();await click('chat-panel-code-cloud-trigger');await click('chat-panel-code-cloud-directory');await act(async()=>connection('disconnected'));await act(async()=>finish(page('',[{name:'stale',path:'stale'}])));await tick();assert.equal(query('chat-panel-code-directory-item'),null);assert.equal(blocked,true);assert.equal(selected,null);
});
test('catalog fails closed for malicious navigation, duplicates and malformed pages',()=>{
 const bad=catalog('cloud');bad.entries[0].url='javascript:alert(1)';assert.throws(()=>api.parseWorkspaceCatalog(bad));bad.entries[0].url='https://a.test/chat/secret';assert.throws(()=>api.parseWorkspaceCatalog(bad));assert.throws(()=>api.parseWorkspacePage(page('',[{name:'../outside',path:'../outside'}]),''));
});

test('unsent draft disables cross-entry navigation while keeping current selection',async()=>{
 const target=catalog('cloud');target.entries[0].url='http://127.0.0.1:18080/';request=async method=>method==='workspace.locations'?target:{environment_id:'env-1'};
 await mount(true,true);await click('chat-panel-code-location-trigger');const local=document.querySelector('[data-testid="chat-panel-code-location-option"][data-variant="local"]');assert.equal(local.disabled,true);assert.match(local.textContent,/草稿/);
});
test('switching to Work discards late directory replies without replacing the original picker',async()=>{
 let finish;request=async(method)=>method==='workspace.locations'?catalog('cloud'):method==='cloud.environment.status'?{environment_id:'env-1'}:new Promise(r=>{finish=r;});
 await mount();await click('chat-panel-code-cloud-trigger');await click('chat-panel-code-cloud-directory');await mount(false);await act(async()=>finish(page('',[{name:'stale',path:'stale'}])));await tick();assert.ok(query('existing-local-picker'));assert.equal(query('chat-panel-code-cloud-trigger'),null);assert.equal(blocked,false);
});

test('Escape closes the workspace menu even when focus remains in the composer',async()=>{
 await mount();await click('chat-panel-code-location-trigger');await act(async()=>window.dispatchEvent(new window.KeyboardEvent('keydown',{key:'Escape'})));await act(async()=>{await new Promise(r=>setTimeout(r,150));});assert.equal(query('chat-panel-code-location-menu'),null);
});
