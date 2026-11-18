import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/' });
for (const [key,value] of Object.entries({window:dom.window,document:dom.window.document,
  localStorage:dom.window.localStorage,sessionStorage:dom.window.sessionStorage,CustomEvent:dom.window.CustomEvent,BroadcastChannel:undefined,IS_REACT_ACT_ENVIRONMENT:true}))
  Object.defineProperty(globalThis,key,{configurable:true,value});
const { createRoot } = await import('react-dom/client');
dom.window.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
dom.window.HTMLDialogElement.prototype.close=function(){this.open=false;};
await build({stdin:{contents:`export { CloudEnvironmentDialog } from './src/components/ChatPanel/CloudEnvironmentDialog'; export { webClient } from './src/services/webClient';`,resolveDir:process.cwd()},bundle:true,packages:'external',platform:'node',format:'esm',loader:{'.svg':'empty','.css':'empty'},define:{'import.meta.env':'{}'},outfile:'node_modules/.cache/cloud-environment/fixture.mjs'});
const {CloudEnvironmentDialog,webClient}=await import('../node_modules/.cache/cloud-environment/fixture.mjs');
const root=createRoot(document.getElementById('root'));const states=new Set();
webClient.onStateChange=fn=>{states.add(fn);return()=>states.delete(fn);};
const find=id=>document.querySelector(`[data-testid="chat-panel-${id}"]`);
const click=async id=>act(async()=>find(id).click());
const render=async props=>act(async()=>root.render(React.createElement(CloudEnvironmentDialog,{open:true,remote:true,mode:'agent',onClose:()=>{},...props})));
const unmount=async()=>act(async()=>root.render(null));
const catalog=kind=>({options:[],default_profile_id:null,execution_entry:{kind,instance_id:kind},execution_targets:[{id:'local',label:'Local',online:true},{id:'cloud',label:'Cloud',online:true}],execution_target:kind});
function github(method,params){return {execution_target:'cloud',...({
  'project.github.status':{configured:true,state:'connected',can_import:true},
  'project.github.accounts':{items:[{id:1,account:'owner'}],has_more:false},
  'project.github.repositories':{items:[{id:2,full_name:'owner/repo',default_branch:'main'}],has_more:false},
  'project.github.resolve':{branch:{name:'main',commit:'a'.repeat(40)}},
  'project.github.branches':{items:[{name:'main',commit:'a'.repeat(40)}],has_more:false},
}[method])};}

test('closed dialog makes no startup requests; physical local has an honest no-cloud state',async()=>{
 let calls=0;webClient.request=async()=>{calls++;return {options:[],default_profile_id:null};};
 await render({open:false});assert.equal(calls,0);await render({open:true});
 assert.equal(calls,1);assert.equal(find('cloud-environment-status').dataset.variant,'notConnected');
 assert.equal(find('project-github-connect'),null);assert.equal(find('cloud-environment-prepare').disabled,true);await unmount();
});

for(const kind of ['local','cloud'])test(`${kind} entry supports the same cloud GitHub selection flow without creating tasks`,async()=>{
 const calls=[];webClient.request=async(method,params)=>{calls.push([method,params]);return method==='federation.instances'?catalog(kind):github(method,params);};
 await render({remote:kind==='local'});
 assert.equal(find('project-github-toggle'),null,'embedded in creation, no second accordion');
 await act(async()=>{const e=find('project-github-account');e.value='1';e.dispatchEvent(new dom.window.Event('change',{bubbles:true}));});
 await click('project-github-repository');assert.match(find('project-github-branch-toggle').textContent,/main/);
 assert.equal(find('cloud-environment-source').textContent,'owner/repo · main');
 assert.equal(find('cloud-environment-name').value,'repo');
 assert.equal(find('project-github-management').open,false);
 assert.equal(find('project-github-accounts-next').hidden,true);
 assert.equal(find('project-github-branch'),null);
 assert.equal(find('cloud-environment-prepare').disabled,false);
 assert.ok(calls.every(([method,params])=>method.startsWith('project.github.') && (kind==='local' ? params.execution_target==='cloud' : params.execution_target===undefined)));
 await unmount();
});

test('failed service lookup can retry and late results after close are discarded',async()=>{
 webClient.request=async()=>{throw Error('unavailable');};await render();assert.equal(find('cloud-environment-status').dataset.variant,'failed');
 let finish;webClient.request=()=>new Promise(resolve=>{finish=resolve;});await click('cloud-environment-retry');await render({open:false});
 await act(async()=>finish(catalog('cloud')));assert.equal(find('project-github-account'),null);await unmount();
});

test('account invalidation closes the draft and fences pending service discovery',async()=>{
 let finish,closed=0;webClient.request=()=>new Promise(resolve=>{finish=resolve;});await render({onClose:()=>{closed++;}});
 await act(async()=>window.dispatchEvent(new dom.window.Event('jiuwen:organization-credentials-changed')));
 await act(async()=>finish(catalog('cloud')));assert.equal(closed,1);assert.equal(find('project-github-account'),null);await unmount();
});

test('disconnect closes the draft and prevents old GitHub results from becoming visible',async()=>{
 let finish,closed=0;let first=true;webClient.request=()=>{if(first){first=false;return Promise.resolve({execution_target:'cloud'});}return new Promise(resolve=>{finish=resolve;});};
 await render({onClose:()=>{closed++;}});await act(async()=>{for(const fn of [...states])fn('closed');});
 await act(async()=>finish({execution_target:'cloud',configured:true,state:'connected',login:'stale-owner'}));
 assert.equal(closed,1);assert.doesNotMatch(document.body.textContent,/stale-owner/);await unmount();
});


test('prepare is explicit and ready only selects a project, never sends or creates a session',async()=>{
 const calls=[];let selected=null;let closed=0;
 webClient.request=async(method,params)=>{calls.push([method,params]);
  if(method==='federation.instances')return catalog('cloud');
  if(method==='project.environment.prepare')return {execution_target:'cloud',operation_id:params.operation_id,state:'ready',project:{project_id:'p1',name:'repo',project_dir:'/managed/repo'}};
  return github(method,params);};
 await render({preferredTarget:'cloud',onPrepared:(p,target)=>{selected=[p,target];},onClose:()=>{closed++;}});
 await act(async()=>{const e=find('project-github-account');e.value='1';e.dispatchEvent(new dom.window.Event('change',{bubbles:true}));});
 await click('project-github-repository');
 assert.match(find('project-github-branch-toggle').textContent,/main/);
 assert.equal(calls.some(([m])=>m==='project.environment.prepare'),false);
 await click('cloud-environment-prepare');assert.equal(selected,null);
 await click('cloud-environment-use');
 assert.equal(selected[0].project_id,'p1');assert.equal(selected[1],'cloud');assert.equal(closed,1);
 assert.equal(calls.some(([m])=>m==='session.create'||m==='chat.send'),false);
 await unmount();
});


test('refresh restores only the scoped operation, retry retains ID and choosing again uses a new intent',async()=>{
 sessionStorage.setItem('swarm.environment.operation.cloud','a'.repeat(32));
 const calls=[];
 webClient.request=async(method,params)=>{
  calls.push([method,params]);
  if(method==='federation.instances')return catalog('cloud');
  if(method==='project.environment.status'||method==='project.environment.prepare')return {
   execution_target:'cloud',operation_id:params.operation_id,state:'failed',selection:{name:'repo',account_id:1,repository_id:2,branch:'main'}};
  return github(method,params);
 };
 await render({preferredTarget:'cloud'});
 assert.equal(find('cloud-environment-preparation').dataset.variant,'failed');
 await click('cloud-environment-prepare');
 assert.equal(calls.find(([m])=>m==='project.environment.prepare')[1].operation_id,'a'.repeat(32));
 await click('cloud-environment-reselect');
 assert.equal(sessionStorage.getItem('swarm.environment.operation.cloud'),null);
 assert.equal(find('cloud-environment-preparation').dataset.variant,'idle');
 await unmount();
});


test('code-ready environments can be selected without an LFS banner or automatic task', async()=>{
 const {default:i18n}=await import('i18next');
 const {initReactI18next}=await import('react-i18next');
 const {readFile}=await import('node:fs/promises');
 const zh=JSON.parse(await readFile('src/i18n/locales/zh.json','utf8'));
 await i18n.use(initReactI18next).init({lng:'zh',resources:{zh:{translation:zh}}});
 sessionStorage.setItem('swarm.environment.operation.cloud','b'.repeat(32));
 const calls=[];let selected=null;
 webClient.request=async(method,params)=>{
  calls.push(method);
  if(method==='federation.instances')return catalog('cloud');
  if(method==='project.environment.status')return {execution_target:'cloud',operation_id:params.operation_id,
   state:'ready',project:{project_id:'p1',name:'repo',repository_source:{lfs_mode:'deferred',lfs:[{path:'demo.mp4'}]}}};
  return github(method,params);
 };
 await render({preferredTarget:'cloud',onPrepared:p=>{selected=p;}});
 assert.equal(find('cloud-environment-error'),null);
 assert.doesNotMatch(document.body.textContent,/LFS|未能下载/);
 assert.equal(find('cloud-environment-preparation').dataset.variant,'ready');
 await click('cloud-environment-use');assert.equal(selected.project_id,'p1');
 assert.equal(sessionStorage.getItem('swarm.environment.operation.cloud'),null);
 await render({open:false,preferredTarget:'cloud'});
 await render({open:true,preferredTarget:'cloud'});
 assert.equal(find('cloud-environment-preparation').dataset.variant,'idle','consumed ready state must not block a new environment');
 assert.notEqual(find('project-github-account'),null);

 assert.equal(calls.some(m=>m==='session.create'||m==='chat.send'),false);
 await unmount();sessionStorage.clear();
});

test('unsupported target permits repository discovery but disables preparation',async()=>{
 webClient.request=async(method,params)=>({...github(method,params),...(method==='project.github.status'?{can_import:false}:{})});
 await render();
 await act(async()=>{const e=find('project-github-account');e.value='1';e.dispatchEvent(new dom.window.Event('change',{bubbles:true}));});
 await click('project-github-repository');
 assert.equal(find('cloud-environment-prepare').disabled,true);
 assert.ok(find('project-github-import-unavailable'));
 await unmount();
});


test('official gh short code uses only GitHub device URL and cancel clears the attempt', async()=>{
 const calls=[];
 webClient.request=async(method,params)=>{
  calls.push(method);
  if(method==='project.github.status')return {execution_target:'cloud',configured:true,state:'disconnected',can_import:true};
  if(method==='project.github.begin')return {execution_target:'cloud',flow:'device',device:{attempt_id:'a'.repeat(32),user_code:'ABCD-EFGH',verification_uri:'https://github.com/login/device',expires_at:Date.now()/1000+900,retry_after:10}};
  if(method==='project.github.disconnect')return {execution_target:'cloud',state:'disconnected'};
  throw Error('unexpected '+method);
 };
 await render({preferredTarget:'cloud'});
 await click('project-github-connect');
 assert.equal(find('project-github-device-code').textContent,'ABCD-EFGH');
 assert.equal(find('project-github-authorize').href,'https://github.com/login/device');
 assert.equal(find('project-github-connect').disabled,true);
 await click('project-github-disconnect');
 assert.equal(find('project-github-device-code'),null);
 assert.ok(calls.includes('project.github.disconnect'));
 assert.equal(calls.some(m=>m==='project.environment.prepare'),false);
 await unmount();
});

const choose = async(id,value)=>act(async()=>{const element=find(id);element.value=value;element.dispatchEvent(new dom.window.Event('change',{bubbles:true}));});

test('closing before the prepare reply does not leave recovery permanently busy',async()=>{
 sessionStorage.clear();let finish;
 webClient.request=async(method,params)=>{
  if(method==='project.environment.prepare')return new Promise(resolve=>{finish=resolve;});
  if(method==='project.environment.status')return {execution_target:'cloud',operation_id:params.operation_id,state:'failed',
   selection:{name:'repo',account_id:1,repository_id:2,branch:'main'}};
  return github(method,params);
 };
 await render();await choose('project-github-account','1');await click('project-github-repository');
 await click('cloud-environment-prepare');assert.equal(find('cloud-environment-prepare').disabled,true);
 await render({open:false});await render({open:true});
 assert.equal(find('cloud-environment-preparation').dataset.variant,'failed');
 assert.equal(find('cloud-environment-prepare').disabled,false);
 await act(async()=>finish({execution_target:'cloud',state:'accepted'}));
 assert.equal(find('cloud-environment-preparation').dataset.variant,'failed');
 await unmount();sessionStorage.clear();
});

test('replacing a GitCode connection immediately clears the previous repository selection',async()=>{
 window.open=()=>null;
 webClient.request=async(method)=>{
  if(method.startsWith('project.github.'))return github(method,{});
  const values={
   'project.gitcode.status':{configured:true,state:'connected',can_import:true},
   'project.gitcode.accounts':{items:[{id:'user',account:'owner'}],has_more:false},
   'project.gitcode.repositories':{items:[{id:2,full_name:'owner/repo',default_branch:'main'}],has_more:false},
   'project.gitcode.resolve':{branch:{name:'main',commit:'a'.repeat(40)}}
  };
  return {execution_target:'cloud',...values[method]};
 };
 await render();await choose('cloud-environment-provider','gitcode');
 await choose('project-gitcode-account','user');await click('project-gitcode-repository');
 assert.equal(find('cloud-environment-prepare').disabled,false);
 await click('project-gitcode-connect');
 assert.ok(find('project-gitcode-token'));
 assert.equal(find('cloud-environment-source'),null);
 assert.equal(find('cloud-environment-prepare').disabled,true);
 await unmount();
});

test('GitCode token connection, selection and prepare preserve provider and never persist the token',async()=>{
 sessionStorage.clear();let connected=false,opened='';const calls=[];
 window.open=(url)=>{opened=url;return null;};
 webClient.request=async(method,params)=>{
  calls.push([method,params]);
  if(method.startsWith('project.github.'))return github(method,params);
  if(method==='project.gitcode.status')return {execution_target:'cloud',configured:true,state:connected?'connected':'disconnected',can_import:true};
  if(method==='project.gitcode.connect'){assert.equal(params.access_token,'synthetic-token');connected=true;return {execution_target:'cloud',state:'connected'};}
  if(method==='project.gitcode.accounts')return {execution_target:'cloud',items:[{id:'opaque-user-id',account:'gitcode-user'}],has_more:false};
  if(method==='project.gitcode.repositories')return {execution_target:'cloud',items:[{id:2,full_name:'gitcode-user/repo',default_branch:'main'}],has_more:false};
  if(method==='project.gitcode.resolve'){assert.equal(params.full_name,'gitcode-user/repo');return {execution_target:'cloud',branch:{name:'main',commit:'a'.repeat(40)}};}
  if(method==='project.environment.prepare')return {execution_target:'cloud',provider:'gitcode',operation_id:params.operation_id,state:'failed',selection:params};
  throw Error(method);
 };
 await render();await choose('cloud-environment-provider','gitcode');
 assert.equal(find('project-github-account'),null);
 await click('project-gitcode-connect');assert.equal(opened,'https://gitcode.com/setting/token-classic/create');
 const input=find('project-gitcode-token');assert.equal(input.type,'password');
 await act(async()=>{Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(input,'synthetic-token');input.dispatchEvent(new window.Event('input',{bubbles:true}));});
 await act(async()=>find('project-gitcode-token-form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true})));
 assert.ok(find('project-gitcode-token') === null, 'token form must be cleared after connecting');
 assert.equal(JSON.stringify({...sessionStorage,...localStorage}).includes('synthetic-token'),false);
 await choose('project-gitcode-account','opaque-user-id');await click('project-gitcode-repository');
 await click('cloud-environment-prepare');
 const prepared=calls.find(([method])=>method==='project.environment.prepare')[1];
 assert.equal(prepared.provider,'gitcode');assert.equal(prepared.account_id,'opaque-user-id');assert.equal(prepared.full_name,'gitcode-user/repo');
 assert.equal(sessionStorage.getItem('swarm.environment.operation.cloud.gitcode'),prepared.operation_id);
 assert.equal(sessionStorage.getItem('swarm.environment.operation.cloud'),null);
 await click('cloud-environment-reselect');await choose('cloud-environment-provider','github');
 assert.ok(find('project-github-account'));assert.equal(find('project-gitcode-account'),null);
 assert.equal(calls.some(([method])=>method==='chat.send'||method==='session.create'),false);
 await unmount();sessionStorage.clear();
});

test('switching providers discards a late GitHub response and token drafts are removed on account change',async()=>{
 let late,first=true;
 webClient.request=async(method)=>{
  if(method==='project.github.status'){if(first){first=false;return {execution_target:'cloud'};}return new Promise(resolve=>{late=resolve;});}
  return {execution_target:'cloud',configured:true,state:'disconnected',can_import:true};
 };
 await render();await choose('cloud-environment-provider','gitcode');
 await act(async()=>late({execution_target:'cloud',configured:true,state:'connected',login:'old-github-account',can_import:true}));
 assert.doesNotMatch(document.body.textContent,/old-github-account/);
 await click('project-gitcode-connect');assert.ok(find('project-gitcode-token'));
 await act(async()=>window.dispatchEvent(new window.Event('jiuwen:organization-credentials-changed')));
 assert.ok(find('project-gitcode-token') === null, 'token form must be cleared after connecting');
 await unmount();
});
