/* Included by build-standalone.py inside the original prototype's module loader. */
__def('js/workbench-live.js', function (exports, __req) {
  'use strict';
  const store = __req('js/store.js');
  const { esc, icon } = __req('js/ui.js');
  const { state, emit, toast } = store;
  const project = 'pj-order';
  const rooms = new Map();
  const statuses = { received: 'queued', routing: 'queued', working: 'running', awaiting_decision: 'blocked',
    resuming: 'running', ready: 'done', ended: 'failed', failed: 'failed' };
  const choices = { published: '采纳已发布规则并恢复', exception: '保留项目例外并恢复' };
  let revision = '';
  let catalogRevision = '';
  let catalog;
  let selection = {};
  let pendingSend;
  let posting = false;
  let polling = false;
  let decision;
  let connected = false;
  const detailCache = new Map();

  function time(at) {
    return new Date(at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  function messageId() {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
    return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join('-');
  }

  async function api(path, data) {
    const response = await fetch('/workbench/' + path, { cache: 'no-store',
      headers: { 'x-workbench': '1', ...(data ? { 'content-type': 'application/json' } : {}) },
      ...(data ? { method: 'POST', body: JSON.stringify(data) } : {}) });
    if (response.redirected && new URL(response.url).pathname === '/login') throw new Error('登录已过期，请重新登录 3082');
    const payload = await response.json();
    if (!response.ok) throw new Error(payload);
    return payload;
  }

  function title(room) {
    return room.ticket?.title || room.userText || '协作室任务';
  }

  function task(room) {
    const at = Date.parse(room.messages[0].at);
    const stop = Date.parse(room.ticket?.ended?.at ?? room.ticket?.report?.at ?? room.messages.at(-1).at);
    return { id: room.ticket?.id ?? room.id, liveThread: room.id, projectId: project,
      workerId: room.expert?.id, title: title(room), status: statuses[room.phase] ?? 'queued',
      elapsed: Math.max(0, stop - at), desc: room.expert?.skill ?? 'SuperAgent 任务', reads: room.reads };
  }

  function flatten(room) {
    const root = room.messages[0];
    const workerId = room.expert?.id;
    const records = [{ id: root.id, liveThread: room.id, type: 'human', authorId: 'u-liming', text: root.text, time: time(root.at), at: root.at }];
    if (room.ticket || ['received', 'routing'].includes(room.phase)) {
      records.push({ id: 'route-' + room.id, type: 'router', state: room.ticket ? 'decided' : 'thinking',
        live: true, workerId, skill: room.expert?.skill, ticketId: room.ticket?.id,
        intervene: Boolean(room.ticket), intent: title(room), time: time(root.at), at: root.at });
    }
    const ask = room.messages.filter(message => message.kind === 'reply').at(-1)?.id;
    for (const item of room.messages.slice(1)) {
      const bot = item.by === '小需';
      const hasArtifact = bot && room.artifact && item.kind === 'reply' &&
        item.text.includes('/workbench/#' + room.id);
      let text = item.text;
      if (hasArtifact) text = text.replace(room.artifact.url, '').replace(/\s+$/, '');
      records.push({ id: item.id, liveThread: room.id, type: bot ? 'bot' : 'human',
        authorId: bot ? 'bot' : 'u-liming', via: bot ? workerId : undefined,
        taskId: item.kind === 'acknowledgement' ? room.ticket?.id : undefined,
        liveDecision: item.id === ask && room.phase === 'awaiting_decision' && workerId === 'w-review',
        liveResult: hasArtifact, text, time: time(item.at), at: item.at });
    }
    return records;
  }

  async function refresh() {
    if (polling) return;
    polling = true;
    try {
      const [data, directory] = await Promise.all([api('room?view=timeline&project=' + project), api('room?view=catalog')]);
      const next = JSON.stringify(data);
      const nextCatalog = JSON.stringify(directory);
      if (next === revision && nextCatalog === catalogRevision && connected) return;
      revision = next;
      if (nextCatalog !== catalogRevision) {
        catalogRevision = nextCatalog;
        catalog = directory;
        detailCache.clear();
        state.features = directory.assets.map(asset => ({
          ...asset, desc: asset.description, freshness: asset.freshness ?? null, lastCheck: asset.checkedAt ?? '—',
          owner: asset.owner ?? '—', version: asset.revisions[0].id, history: asset.revisions,
          useCases: directory.useCases.filter(item => item.assetId === asset.id).length,
        }));
        state.workers = directory.experts.map(expert => ({ ...expert,
          skills: [expert.skill], status: 'idle' }));
        state.liveBusinessAssets = directory.assets.filter(asset => !asset.demo && !asset.simulation).length;
        state.liveSimulationAssets = directory.assets.filter(asset => asset.simulation).length;
      }
      connected = true;
      rooms.clear();
      for (const room of data) rooms.set(room.id, room);
      state.liveConnection = 'SuperAgent 已连接';
      state.messages[project] = data.flatMap(flatten).sort((a, b) => a.at.localeCompare(b.at));
      state.tasks = data.filter(room => room.ticket).map(task);
      state.logs = data.flatMap(room => room.ticket?.report ? [{ id: room.id, time: time(room.ticket.report.at),
        at: room.ticket.report.at, workerId: room.expert?.id, text: room.ticket.report.summary,
        level: room.phase === 'failed' ? 'warn' : 'info' }] : []).sort((a, b) => b.at.localeCompare(a.at));
      state.alerts = data.filter(room => room.phase === 'awaiting_decision' && room.ticket?.attention &&
        room.messages.some(message => message.kind === 'reply')).map(room => ({
          liveThread: room.expert?.id === 'w-review' ? room.id : undefined, time: time(room.ticket.attention.at), level: 'warn',
          title: 'SuperAgent 等待人工裁定', detail: room.ticket.attention.question, resolved: false }));
      for (const worker of state.workers) {
        const tasks = state.tasks.filter(task => task.workerId === worker.id);
        const done = tasks.filter(task => task.status === 'done');
        const ended = tasks.filter(task => ['done', 'failed'].includes(task.status));
        worker.status = tasks.some(task => task.status === 'running') ? 'busy' : 'idle';
        worker.done = done.length;
        worker.success = ended.length ? Math.round(done.length * 100 / ended.length) + '%' : '—';
        worker.avg = done.length ? (done.reduce((sum, task) => sum + task.elapsed, 0) / done.length / 1000).toFixed(1) + 's' : '—';
      }
      state.stats = { intervened: state.tasks.length, doneToday: state.tasks.filter(t => t.status === 'done').length,
        dispatched: state.tasks.length };
      emit();
    } catch (error) {
      const message = 'SuperAgent 同步失败：' + error.message;
      if (state.liveConnection !== message) {
        connected = false;
        state.liveConnection = message;
        emit();
      }
    } finally {
      polling = false;
    }
  }

  function unavailable() {
    toast('该操作仍是原型功能。可在协作室发起文档任务，或从业务资产中心引用版本。', 'warn');
  }

  async function send(projectId, raw, context) {
    const text = raw?.trim();
    if (!text || posting) return;
    if (projectId !== project) {
      toast('真实验证请在「消费信贷中台 2.0」协作室发起。', 'warn');
      return;
    }
    if (!catalog) {
      toast('正在读取协作室目录，请稍后。', 'warn');
      return;
    }
    const named = text.match(/[\w.-]+/g) ?? [];
    const mentionedCase = catalog.useCases.find(item => named.includes(item.id));
    const demo = catalog.assets.find(asset => asset.demo);
    const requestedCase = mentionedCase?.id ?? selection.useCase?.id;
    const usingDemo = context?.demo && (!selection.asset || selection.asset.assetId === demo.id) &&
      (!requestedCase || catalog.useCases.some(item => item.id === requestedCase && item.assetId === demo.id));
    const asset = selection.asset ?? (usingDemo && context.demo === 'review' ? defaultRef(demo) : undefined);
    const useCaseId = requestedCase ?? (usingDemo ? relatedCases(demo.id)[0]?.id : undefined);
    const fields = { text, projectId, asset, useCaseId };
    if (!pendingSend || JSON.stringify(fields) !== pendingSend.key) {
      pendingSend = { id: messageId(), ...fields, key: JSON.stringify(fields) };
    }
    const { key, ...input } = pendingSend;
    posting = true;
    try {
      await api('messages', input);
      pendingSend = undefined;
      selection = {};
      const composer = document.getElementById('composerInput');
      if (composer?.value.trim() === text) composer.value = '';
      await refresh();
      emit();
    } catch (error) {
      toast('真实任务提交失败：' + error.message, 'warn');
    } finally {
      posting = false;
    }
  }

  async function decide(id, choice) {
    const room = rooms.get(id);
    const attentionId = room?.ticket?.attention?.id;
    if (!attentionId || !choices[choice] || posting) return;
    if (!decision || decision.attentionId !== attentionId || decision.choice !== choice) decision = {
      id: messageId(), threadId: id, ticketId: room.ticket.id, attentionId, choice };
    posting = true;
    try {
      await api('decisions', decision);
      decision = undefined;
      state.ui.modal = null;
      await refresh();
      emit();
    } catch (error) {
      toast('裁定提交失败：' + error.message, 'warn');
    } finally {
      posting = false;
    }
  }

  function modal(value) {
    const room = rooms.get(value.threadId);
    if (!room) return '';
    const isDecision = value.type === 'liveDecision';
    const ticket = room.ticket;
    const citation = room.artifact?.citation ?? room.citation;
    const body = isDecision ? ticket?.attention?.question ?? '该问题已处理。' : room.artifact?.text ?? '等待结果。';
    const actions = isDecision && room.phase === 'awaiting_decision' ? Object.entries(choices)
      .map(([choice, label]) => `<button class="btn ${choice === 'published' ? 'primary' : ''}" data-act="live-decide" data-thread="${esc(room.id)}" data-choice="${choice}">${label}</button>`).join('') : '';
    return `<div class="modal-mask" data-act="close-modal"></div><section class="modal" role="dialog" aria-modal="true" aria-label="${isDecision ? '人工裁定' : '真实任务结果'}">
      <header class="mo-head"><div><h3>${isDecision ? '人工裁定' : '真实任务结果'}</h3><p>Ticket ${esc(ticket?.id ?? '')}${citation ? ' · ' + [citation.assetId, citation.revisionId, citation.sectionId, citation.source?.label].filter(Boolean).map(esc).join(' / ') : ''}</p></div>
      <button class="icon-btn" data-act="close-modal" aria-label="关闭">${icon('x', 16)}</button></header>
      <div class="mo-body" style="white-space:pre-wrap;overflow-wrap:anywhere;max-height:50vh;overflow:auto">${esc(body)}</div>
      <footer class="mo-foot"><button class="btn ghost" data-act="close-modal">关闭</button>${actions}</footer></section>`;
  }

  function defaultRef(asset) {
    const revision = asset.revisions[0];
    return { assetId: asset.id, revisionId: revision.id, sectionId: revision.sections[0].id };
  }

  function useInChat(name, value) {
    selection[name] = value;
    state.ui.drawer = null;
    state.ui.tab = 'chat';
    location.hash = '#/project/' + project + '/chat';
    emit();
  }

  function attachments() {
    if (state.route.projectId !== project) return '';
    const { asset, useCase } = selection;
    return `<div class="quick-row">
      <button class="q" data-act="open-assets">${icon('archive', 12)} 选择资产版本</button>
      ${asset ? `<button class="q" data-act="live-remove-attachment" data-id="asset" title="移除引用">${[catalog?.assets.find(item => item.id === asset.assetId)?.name, asset.revisionId, asset.sectionId].filter(Boolean).map(esc).join(' / ')} ×</button>` : ''}
      ${useCase ? `<button class="q" data-act="live-remove-attachment" data-id="useCase" title="移除引用">${esc(useCase.id)} ×</button>` : ''}
    </div>`;
  }

  function detailKey(ids) {
    return ids.join('/');
  }

  async function preview(id, ids) {
    const drawer = state.ui.drawer;
    if (!drawer || drawer.id !== id) return;
    const key = detailKey(ids);
    drawer.evidence = { key, kind: ids.length === 1 ? 'useCase' : 'asset' };
    emit();
    if (detailCache.has(key)) return;
    const query = ids.length === 1 ? { view: 'use-case', case: ids[0] }
      : { view: 'asset', asset: id, revision: ids[1], section: ids[2] };
    try {
      detailCache.set(key, await api('room?' + new URLSearchParams(query)));
    } catch (error) {
      if (state.ui.drawer === drawer && drawer.evidence.key === key) drawer.evidence.error = error.message;
    }
    if (state.ui.drawer === drawer && drawer.evidence.key === key) emit();
  }

  function attachPreview() {
    const evidence = state.ui.drawer?.evidence;
    const item = evidence && detailCache.get(evidence.key);
    if (!item) return;
    useInChat(evidence.kind, evidence.kind === 'asset'
      ? { assetId: item.assetId, revisionId: item.revisionId, sectionId: item.sectionId }
      : { id: item.id });
  }

  function auditPreview() {
    const evidence = state.ui.drawer?.evidence;
    if (evidence?.kind !== 'asset') return;
    attachPreview();
    return send(project, '请体检此资产版本的规则完整性、来源和待复核项。');
  }

  function removeAttachment(id) {
    if (id !== 'asset' && id !== 'useCase') return;
    delete selection[id];
    emit();
  }

  function relatedCases(assetId) {
    return catalog?.useCases.filter(item => item.assetId === assetId) ?? [];
  }

  function evidencePanel(f) {
    const evidence = state.ui.drawer?.evidence;
    const selected = evidence && detailCache.get(evidence.key);
    const cases = relatedCases(f.id);
    return `<div class="dr-section"><h4>关联用例</h4>
      ${cases.map(item => `<button class="dr-uc" data-act="live-case-preview" data-id="${esc(f.id)}" data-case="${esc(item.id)}">
        <span class="uc-code">${esc(item.id)}</span><span>${esc(item.title)}</span></button>`).join('') || '<div class="dd-empty">暂无关联用例</div>'}
      </div>
      <div class="dr-section"><h4>历史版本 <em class="hs-count">${f.revisions.length} 个</em></h4>
      <div class="timeline">${f.revisions.map((rev, index) => `<div class="tl-row ${index === 0 ? 'on' : ''}">
        <span class="tl-dot"></span><div><b>${esc(rev.id)}</b>
        <em>${esc(rev.publishedAt ?? '')} ${esc(rev.source.label)}</em>
        ${rev.sections.map(section => `<button class="btn xs ghost" data-act="live-asset-preview" data-id="${esc(f.id)}"
          data-revision="${esc(rev.id)}" data-section="${esc(section.id)}">${esc(section.title)}</button>`).join('')}</div>
      </div>`).join('')}</div></div>
      ${evidence ? `<div class="dr-section"><h4>${esc(selected?.title ?? '证据预览')}</h4>
        ${selected ? `<div class="dd-note">${[selected.revisionId ?? selected.id, selected.sectionId, selected.source.label, selected.source.ref].filter(Boolean).map(esc).join(' · ')}</div>
        <p class="dr-desc" style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(selected.body)}</p>
        <button class="btn sm primary" data-act="live-attach-preview">${evidence.kind === 'asset' ? '在协作室引用此版本' : '在协作室引用此用例'}</button>
        ${evidence.kind === 'asset' ? '<button class="btn sm" data-act="live-audit-preview">体检此版本</button>' : ''}`
        : `<div class="dd-empty">${esc(evidence.error ?? '正在读取…')}</div>`}</div>` : ''}`;
  }

  function checkAsset(id) {
    state.ui.drawer = { type: 'asset', id };
    emit();
  }

  function install() {
    state.liveConnection = '正在连接 SuperAgent';
    state.features = [];
    state.workers = [];
    state.messages[project] = [];
    state.stats = { intervened: 0, doneToday: 0, dispatched: 0 };
    store.sendMessage = send;
    store.checkAsset = checkAsset;
    for (const name of ['startIntake', 'generatePrototype', 'submitReview', 'retryTask', 'applyFix']) {
      store[name] = unavailable;
    }
  }

  Object.assign(exports, { install, refresh, decide, modal, unavailable, project, attachments,
    preview, attachPreview, auditPreview, removeAttachment, relatedCases, evidencePanel });
});
