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
 for(const [key,value] of Object.entries({window:dom.window,document:dom.window.document,navigator:dom.window.navigator,HTMLElement:dom.window.HTMLElement,Node:dom.window.Node,Event:dom.window.Event,CustomEvent:dom.window.CustomEvent,localStorage:dom.window.localStorage,sessionStorage:dom.window.sessionStorage,IS_REACT_ACT_ENVIRONMENT:true,BroadcastChannel:undefined,requestAnimationFrame:dom.window.requestAnimationFrame.bind(dom.window),cancelAnimationFrame:dom.window.cancelAnimationFrame.bind(dom.window)}))Object.defineProperty(globalThis,key,{value,writable:true,configurable:true});
 window.HTMLDialogElement.prototype.showModal=function(){this.open=true;};window.HTMLDialogElement.prototype.close=function(){this.open=false;};
 ({createRoot}=await import('react-dom/client'));
 globalThis.fetch=async(_url, options)=>{const body=JSON.parse(options.body);calls.push({method:'bridge.'+body.operation,params:body});try{return new Response(JSON.stringify(await request('bridge.'+body.operation,body)),{status:200});}catch(error){return new Response(JSON.stringify({code:error.code}),{status:error.code==='UNAUTHORIZED'?401:409});}};
 globalThis.__workspaceRequest=async(method,params)=>{calls.push({method,params});return request(method,params);};
 globalThis.__workspaceConnection=fn=>{connection=fn;return ()=>{};};
 globalThis.__workspaceStore={codeLocation:'local',cloudProject:null,setCloudProject:p=>{globalThis.__workspaceStore.cloudProject=p;},setCodeLocation:l=>{globalThis.__workspaceStore.codeLocation=l;},selectedProject:null,setSelectedProject:p=>{selected=p;},loadProjects:async()=>{}};
 const result=await build({stdin:{contents:"export * from './src/components/ChatPanel/CodeWorkspaceControls';",resolveDir:process.cwd(),loader:'ts'},bundle:true,packages:'external',platform:'node',format:'esm',write:false,loader:{'.css':'empty','.svg':'text'},define:{'import.meta.env':'{}'},plugins:[{name:'boundary',setup(b){
 b.onResolve({filter:/services\/webClient$/},()=>({path:'transport',namespace:'workspace-test'}));
 b.onResolve({filter:/stores\/workspaceStore$/},()=>({path:'store',namespace:'workspace-test'}));
 b.onLoad({filter:/.*/,namespace:'workspace-test'},args=>({contents:args.path==='transport'?'export const webRequest=(...args)=>globalThis.__workspaceRequest(...args); export const webClient={onStateChange:fn=>globalThis.__workspaceConnection(fn),disconnect:async()=>{}};':'export const useWorkspaceStore=selector=>selector(globalThis.__workspaceStore); useWorkspaceStore.getState=()=>globalThis.__workspaceStore;'}));
 }}]});
 await mkdir('node_modules/.cache/code-workspace',{recursive:true});await writeFile('node_modules/.cache/code-workspace/test.mjs',result.outputFiles[0].text);api=await import('../node_modules/.cache/code-workspace/test.mjs');
 await i18next.init({lng:'zh',resources:{zh:{translation:JSON.parse(await readFile('src/i18n/locales/zh.json','utf8'))}}});
});
beforeEach(()=>{globalThis.__workspaceStore.codeLocation='local';globalThis.__workspaceStore.cloudProject=null;calls=[];blocked=false;selected=null;request=async(method)=>method==='workspace.locations'?catalog('cloud'):method==='cloud.environment.status'?{environment_id:'env-1',state:'ALLOCATED'}:page();root=createRoot(document.getElementById('root'));});
afterEach(async()=>{await act(async()=>root.unmount());});after(()=>dom.window.close());
async function mount(enabled=true,navigationBlocked=false){await act(async()=>root.render(h(I18nextProvider,{i18n:i18next},h(api.CodeWorkspaceControls,{enabled,navigationBlocked,disabled:false,onBlockedChange:bindBlocked,localControl:h('button',{'data-testid':'existing-local-picker'},'original local')}))));await tick();}
test('cloud has three controls and all original cloud actions; no automatic ensure',async()=>{
 await mount();assert.ok(query('chat-panel-code-local-directory'));assert.ok(query('chat-panel-code-location-trigger'));assert.ok(query('chat-panel-code-cloud-trigger'));assert.equal(query('existing-local-picker'),null);assert.equal(blocked,false);
 await click('chat-panel-code-cloud-trigger');for(const id of ['directory','mkdir','create'])assert.ok(query('chat-panel-code-cloud-'+id));assert.equal(calls.some(c=>c.method.startsWith('cloud.environment.')),false);
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

test('switching to Work discards late directory replies without replacing the original picker',async()=>{
 let finish;request=async(method)=>method==='workspace.locations'?catalog('cloud'):method==='cloud.environment.status'?{environment_id:'env-1'}:new Promise(r=>{finish=r;});
 await mount();await click('chat-panel-code-cloud-trigger');await click('chat-panel-code-cloud-directory');await mount(false);await act(async()=>finish(page('',[{name:'stale',path:'stale'}])));await tick();assert.ok(query('existing-local-picker'));assert.equal(query('chat-panel-code-cloud-trigger'),null);assert.equal(blocked,false);
});

test('Escape closes the workspace menu even when focus remains in the composer',async()=>{
 await mount();await click('chat-panel-code-location-trigger');await act(async()=>window.dispatchEvent(new window.KeyboardEvent('keydown',{key:'Escape'})));await act(async()=>{await new Promise(r=>setTimeout(r,150));});assert.equal(query('chat-panel-code-location-menu'),null);
});

async function choose(kind){await click('chat-panel-code-location-trigger');await act(async()=>document.querySelector(`[data-testid="chat-panel-code-location-option"][data-variant="${kind}"]`).click());await tick();}
test('Local/Cloud selection is immediate with a draft and does not contact the cloud or navigate',async()=>{
 request=async()=>catalog('local');await mount(true,true);const initial=calls.length;const href=window.location.href;
 await choose('cloud');assert.ok(query('chat-panel-code-cloud-trigger'));assert.equal(query('chat-panel-code-location-trigger').textContent,'云端');assert.equal(calls.length,initial);assert.equal(window.location.href,href);assert.equal(blocked,true);
 await choose('local');assert.equal(query('chat-panel-code-cloud-trigger'),null);assert.equal(blocked,false);assert.equal(calls.length,initial);
});
test('cloud selection survives a late current-host catalog',async()=>{
 let finish;request=()=>new Promise(r=>{finish=r;});await mount();await choose('cloud');await act(async()=>finish(catalog('local')));await tick();assert.equal(query('chat-panel-code-location-trigger').textContent,'云端');assert.equal(calls.length,1);
});
test('local page opens and creates cloud directories through the bridge without replacing the local project',async()=>{
 const remoteProject={project_id:'cloudp_0123456789abcdef01234567_cHJval8x',project_dir:'/cloud/code/new',work_mode:'code',name:'new'};
 request=async(method,params)=>method==='workspace.locations'?catalog('local'):method==='bridge.mkdir'?{path:params.name,created:true}:method==='bridge.open'?{project:remoteProject}:page();
 await mount();const href=window.location.href;await choose('cloud');await click('chat-panel-code-cloud-trigger');await click('chat-panel-code-cloud-mkdir');await text('chat-panel-code-folder-name','new');await click('chat-panel-code-workspace-confirm');await click('chat-panel-code-workspace-confirm');
 assert.equal(selected,null);assert.equal(window.location.href,href);assert.equal(blocked,false);assert.match(query('chat-panel-code-cloud-trigger').textContent,/new/);assert.equal(query('chat-panel-code-cloud-execution-pending'),null);
 assert.deepEqual(calls.map(row=>row.method),['workspace.locations','bridge.list','bridge.mkdir','bridge.open']);
 await choose('local');assert.equal(blocked,false);
});
test('unauthenticated directory action asks the original local login dialog and resumes only the view',async()=>{
 let loggedIn=false,complete;const listener=event=>{complete=event.detail;};window.addEventListener('jiuwenswarm-cloud-login-request',listener);
 try{
  request=async method=>{if(method==='workspace.locations')return catalog('local');if(!loggedIn)throw {code:'UNAUTHORIZED'};return page();};
  await mount();await choose('cloud');await click('chat-panel-code-cloud-trigger');await click('chat-panel-code-cloud-mkdir');assert.equal(typeof complete,'function');assert.equal(query('chat-panel-code-workspace-dialog').closest('dialog').open,false);
  loggedIn=true;await act(async()=>{window.dispatchEvent(new Event('jiuwenswarm-cloud-account'));complete(true);});await tick();assert.equal(query('chat-panel-code-workspace-dialog').dataset.variant,'folder');assert.equal(query('chat-panel-code-workspace-dialog').closest('dialog').open,true);assert.equal(calls.some(row=>row.method==='bridge.mkdir'),false);
 }finally{window.removeEventListener('jiuwenswarm-cloud-login-request',listener);}
});
test('switching back to Local cancels a pending login intention',async()=>{
 let complete;const listener=e=>{complete=e.detail;};window.addEventListener('jiuwenswarm-cloud-login-request',listener);
 try{request=async method=>{if(method==='workspace.locations')return catalog('local');throw {code:'UNAUTHORIZED'};};await mount();await choose('cloud');await click('chat-panel-code-cloud-trigger');await click('chat-panel-code-cloud-directory');await choose('local');const before=calls.length;await act(async()=>complete(true));await tick();assert.equal(calls.length,before);assert.equal(blocked,false);}finally{window.removeEventListener('jiuwenswarm-cloud-login-request',listener);}
});
test('environment selection reads status on demand and prepares only on explicit confirmation',async()=>{
 request=async method=>method==='workspace.locations'?catalog('local'):{environment_id:'env',state:method==='bridge.ensure'?'READY':'ALLOCATED'};
 await mount();await choose('cloud');await click('chat-panel-code-cloud-trigger');await click('chat-panel-code-cloud-environment');assert.equal(calls.at(-1).method,'bridge.environment');assert.equal(calls.some(row=>row.method==='bridge.ensure'),false);await click('chat-panel-code-workspace-confirm');assert.equal(calls.at(-1).method,'bridge.ensure');assert.equal(window.location.pathname,'/');
});
test('switching Local invalidates a slow cloud directory response without waiting',async()=>{
 let finish;request=async method=>method==='workspace.locations'?catalog('local'):new Promise(r=>{finish=r;});await mount();await choose('cloud');await click('chat-panel-code-cloud-trigger');await click('chat-panel-code-cloud-directory');await choose('local');assert.equal(blocked,false);await act(async()=>finish(page('',[{name:'late',path:'late'}])));await tick();assert.equal(query('chat-panel-code-directory-item'),null);assert.equal(selected,null);
});


test('folder name is editable during directory loading and cancelling rejects late replies',async()=>{
 let finish;request=async method=>method==='workspace.locations'?catalog('local'):new Promise(r=>{finish=r;});
 await mount();await choose('cloud');await click('chat-panel-code-cloud-trigger');await click('chat-panel-code-cloud-mkdir');
 assert.equal(query('chat-panel-code-folder-name').disabled,false);assert.equal(query('chat-panel-code-workspace-cancel').disabled,false);
 await text('chat-panel-code-folder-name','draft-name');assert.equal(query('chat-panel-code-workspace-confirm').disabled,true);
 await click('chat-panel-code-workspace-cancel');await act(async()=>finish(page('',[{name:'late',path:'late'}])));await tick();
 assert.equal(query('chat-panel-code-workspace-dialog').closest('dialog').open,false);assert.equal(query('chat-panel-code-directory-item'),null);
 assert.equal(calls.some(row=>row.method==='bridge.mkdir'),false);
});

test('a folder draft survives the required login without replaying create',async()=>{
 let fail,complete;const listener=e=>{complete=e.detail;};window.addEventListener('jiuwenswarm-cloud-login-request',listener);
 try{
  request=async method=>method==='workspace.locations'?catalog('local'):new Promise((_,reject)=>{fail=reject;});
  await mount();await choose('cloud');await click('chat-panel-code-cloud-trigger');await click('chat-panel-code-cloud-mkdir');await text('chat-panel-code-folder-name','keep-name');
  await act(async()=>fail({code:'UNAUTHORIZED'}));await tick();request=async()=>page();
  await act(async()=>{window.dispatchEvent(new Event('jiuwenswarm-cloud-account'));complete(true);});await tick();
  assert.equal(query('chat-panel-code-folder-name').value,'keep-name');assert.equal(calls.some(row=>row.method==='bridge.mkdir'),false);
 }finally{window.removeEventListener('jiuwenswarm-cloud-login-request',listener);}
});
