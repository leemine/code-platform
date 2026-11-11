import assert from 'node:assert/strict';
import test from 'node:test';

globalThis.window = globalThis;
globalThis.window.location = { protocol: 'http:', host: 'localhost:18180' };

class FakeWebSocket {
  static OPEN = 1;
  static instance;

  constructor(url) {
    this.url = url;
    this.readyState = 0;
    this.listeners = new Map();
    this.sentRequests = [];
    FakeWebSocket.instance = this;
    queueMicrotask(() => {
      this.readyState = FakeWebSocket.OPEN;
      this.onopen?.();
    });
  }

  addEventListener(event, handler) {
    const handlers = this.listeners.get(event) ?? [];
    handlers.push(handler);
    this.listeners.set(event, handlers);
  }

  send(raw) {
    this.lastRequest = JSON.parse(raw);
    this.sentRequests.push(this.lastRequest);
  }

  close(code = 1000, reason = '') {
    this.readyState = 3;
    const event = { code, reason, wasClean: code === 1000 };
    this.onclose?.(event);
    for (const handler of this.listeners.get('close') ?? []) handler(event);
  }

  receive(message) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }
}

globalThis.WebSocket = FakeWebSocket;

const { webClient } = await import('../node_modules/.cache/web-client-runtime-ack/webClient.mjs');
const { attachTeamSession, resetTeamAttachments } = await import(
  '../node_modules/.cache/web-client-runtime-ack/teamAttach.mjs'
);

await webClient.connect();

function gatewayResponse(id, ok = true) {
  FakeWebSocket.instance.receive({ type: 'res', id, ok, payload: { accepted: ok } });
}

function runtimeEvent(event, requestId, payload = {}) {
  FakeWebSocket.instance.receive({
    type: 'event',
    event,
    payload: { request_id: requestId, ...payload },
  });
}

test('runtime-ack request stays pending after gateway response and resolves exact ack', async () => {
  let settled = false;
  const result = webClient
    .request('chat.send', { source: 'permission_interrupt' }, { awaitRuntimeAccepted: true, timeoutMs: 1000 })
    .finally(() => {
      settled = true;
    });
  await Promise.resolve();
  const requestId = FakeWebSocket.instance.lastRequest.id;

  gatewayResponse(requestId);
  runtimeEvent('runtime.accepted', 'other-request');
  await Promise.resolve();
  assert.equal(settled, false);

  runtimeEvent('runtime.accepted', requestId, { accepted: true });
  assert.deepEqual(await result, { request_id: requestId, accepted: true });
});

test('runtime-ack request rejects exact Host error while ordinary request keeps gateway semantics', async () => {
  const permission = webClient.request(
    'chat.send',
    { source: 'permission_interrupt' },
    { awaitRuntimeAccepted: true, timeoutMs: 1000 },
  );
  await Promise.resolve();
  const permissionId = FakeWebSocket.instance.lastRequest.id;
  gatewayResponse(permissionId);
  runtimeEvent('chat.error', permissionId, { error: 'send failed' });
  await assert.rejects(permission, /send failed/);

  const ordinary = webClient.request('chat.send', { source: 'ask_user_interrupt' });
  await Promise.resolve();
  const ordinaryId = FakeWebSocket.instance.lastRequest.id;
  gatewayResponse(ordinaryId);
  assert.deepEqual(await ordinary, { accepted: true });
});

test('abort keeps runtime-ack request rejected without waiting for Host event', async () => {
  const controller = new AbortController();
  const pending = webClient.request(
    'chat.send',
    { source: 'permission_interrupt' },
    {
      awaitRuntimeAccepted: true,
      timeoutMs: 1000,
      signal: controller.signal,
    },
  );
  await Promise.resolve();
  const requestId = FakeWebSocket.instance.lastRequest.id;
  gatewayResponse(requestId);
  controller.abort();

  await assert.rejects(pending, (error) => error.code === 'REQUEST_ABORTED');
  runtimeEvent('runtime.accepted', requestId);
  await Promise.resolve();
});

test('request identity is bound before send and runtime errors preserve their code and payload', async () => {
  let boundId;
  const socket = FakeWebSocket.instance;
  const originalSend = socket.send;
  socket.send = function (raw) {
    const outgoing = JSON.parse(raw);
    assert.equal(boundId, outgoing.id);
    originalSend.call(this, raw);
  };
  try {
    const pending = webClient.request(
      'chat.send',
      { input_mode: 'steer' },
      {
        awaitRuntimeAccepted: true,
        onRequestId: (id) => {
          boundId = id;
        },
      },
    );
    await Promise.resolve();
    runtimeEvent('chat.error', boundId, { code: 'SESSION_INPUT_DELIVERY_UNKNOWN', error: 'uncertain' });
    await assert.rejects(pending, (error) => {
      assert.equal(error.code, 'SESSION_INPUT_DELIVERY_UNKNOWN');
      assert.equal(error.payload.error, 'uncertain');
      assert.equal(error.requestId, boundId);
      return true;
    });
  } finally {
    socket.send = originalSend;
  }
});

test('legacy content wrapping an acceptance is routed as ACK, not final output', async () => {
  let finalCount = 0;
  const unsubscribe = webClient.on('chat.final', () => {
    finalCount += 1;
  });
  try {
    const pending = webClient.request('chat.send', { input_mode: 'steer' }, { awaitRuntimeAccepted: true });
    await Promise.resolve();
    const requestId = FakeWebSocket.instance.lastRequest.id;
    FakeWebSocket.instance.receive({
      type: 'content',
      payload: { event_type: 'runtime.accepted', request_id: requestId },
    });
    assert.equal((await pending).request_id, requestId);
    assert.equal(finalCount, 0);
  } finally {
    unsubscribe();
  }
});

test('timeout and disconnect reject runtime-ack requests after gateway acceptance', async () => {
  const timedOut = webClient.request(
    'chat.send',
    { source: 'permission_interrupt' },
    { awaitRuntimeAccepted: true, timeoutMs: 5 },
  );
  await Promise.resolve();
  gatewayResponse(FakeWebSocket.instance.lastRequest.id);
  await assert.rejects(timedOut, (error) => error.code === 'REQUEST_TIMEOUT');

  const disconnected = webClient.request(
    'chat.send',
    { source: 'permission_interrupt' },
    { awaitRuntimeAccepted: true, timeoutMs: 1000 },
  );
  await Promise.resolve();
  gatewayResponse(FakeWebSocket.instance.lastRequest.id);
  const closed = webClient.disconnect();
  await assert.rejects(disconnected, (error) => error.code === 'WS_CLOSED');
  await closed;
});

test('reconnect resumes the original event cursor without resubmitting input', async () => {
  await webClient.connect();
  let deltas = 0;
  let processing;
  const offDelta = webClient.on('chat.delta', () => {
    deltas += 1;
  });
  const offStatus = webClient.on('chat.processing_status', (event) => {
    processing = event.payload.is_processing;
  });
  const payload = {
    session_id: 'resume-session',
    content: 'original-output',
    runtime_event: { worker_instance: 'worker-original', sequence: 17, dispatch_id: 'original-dispatch' },
  };
  try {
    runtimeEvent('chat.delta', 'original-request', payload);
    runtimeEvent('chat.delta', 'original-request', payload);
    assert.equal(deltas, 1);
    await webClient.disconnect();
    await webClient.connect();
    await new Promise((resolve) => setTimeout(resolve, 0));
    const query = FakeWebSocket.instance.lastRequest;
    assert.equal(query.method, 'session.get_metadata');
    assert.deepEqual(query.params, {
      session_id: 'resume-session',
      runtime_resume: { worker_instance: 'worker-original', after: 17 },
    });
    FakeWebSocket.instance.receive({
      type: 'res',
      id: query.id,
      ok: true,
      payload: { runtime: { is_processing: false, history_required: false } },
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
    runtimeEvent('chat.delta', 'original-request', payload);
    runtimeEvent('chat.delta', 'original-request', {
      ...payload,
      runtime_event: { ...payload.runtime_event, sequence: 18, replayed: true },
    });
    assert.equal(deltas, 2);
    assert.equal(processing, false);
  } finally {
    offDelta();
    offStatus();
    await webClient.disconnect();
  }
});

test('a fresh page subscribes to the execution discovered in session metadata', async () => {
  const fresh = new webClient.constructor();
  await fresh.connect();
  const socket = FakeWebSocket.instance;
  const sent = [];
  const originalSend = socket.send;
  socket.send = function (raw) {
    sent.push(JSON.parse(raw));
    originalSend.call(this, raw);
  };
  let processing;
  const off = fresh.on('chat.processing_status', (event) => {
    processing = event.payload.is_processing;
  });
  try {
    const pending = fresh.request('session.get_metadata', { session_id: 'fresh-session' });
    await Promise.resolve();
    socket.receive({
      type: 'res',
      id: socket.lastRequest.id,
      ok: true,
      payload: {
        runtime: { worker_instance: 'existing-worker', is_processing: true },
      },
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
    const subscription = socket.lastRequest;
    assert.deepEqual(subscription.params, {
      session_id: 'fresh-session',
      runtime_resume: { worker_instance: 'existing-worker', after: 0 },
    });
    socket.receive({
      type: 'res',
      id: subscription.id,
      ok: true,
      payload: {
        runtime: { worker_instance: 'existing-worker', is_processing: true, history_required: false },
      },
    });
    await pending;
    assert.equal(processing, true);
    assert.deepEqual(
      sent.map((request) => request.method),
      ['session.get_metadata', 'session.get_metadata'],
    );
  } finally {
    off();
    await fresh.disconnect();
  }
});

test('pending reconnect recovery preserves processing and retries only the original cursor with a bound', async () => {
  const fresh = new webClient.constructor();
  await fresh.connect();
  let processing = true;
  const snapshots = [];
  const sent = [];
  const offStatus = fresh.on('chat.processing_status', ({ payload }) => {
    processing = payload.is_processing;
  });
  const offSnapshot = fresh.on('runtime.snapshot', ({ payload }) => {
    snapshots.push(payload);
  });
  FakeWebSocket.instance.receive({
    type: 'event',
    event: 'chat.delta',
    payload: {
      session_id: 'pending-session',
      runtime_event: { worker_instance: 'original-worker', sequence: 27 },
    },
  });
  await fresh.disconnect();
  const originalSend = FakeWebSocket.prototype.send;
  FakeWebSocket.prototype.send = function (raw) {
    originalSend.call(this, raw);
    const query = JSON.parse(raw);
    sent.push(query);
    queueMicrotask(() =>
      this.receive({
        type: 'res',
        id: query.id,
        ok: true,
        payload: {
          runtime: { recovery_pending: true, recovery_reason: 'snapshot_timeout', retry_after_ms: 1 },
        },
      }),
    );
  };
  try {
    await fresh.connect();
    await new Promise((resolve) => setTimeout(resolve, 350));
    assert.equal(processing, true);
    assert.equal(snapshots.length, 3);
    assert.deepEqual(
      sent.map(({ method, params }) => ({ method, params })),
      Array.from({ length: 3 }, () => ({
        method: 'session.get_metadata',
        params: { session_id: 'pending-session', runtime_resume: { worker_instance: 'original-worker', after: 27 } },
      })),
    );
    assert.ok(snapshots.every((snapshot) => snapshot.recovery_pending === true));
  } finally {
    FakeWebSocket.prototype.send = originalSend;
    offStatus();
    offSnapshot();
    await fresh.disconnect();
  }
});

test('fresh metadata pending recovery reaches the later running snapshot without clearing processing', async () => {
  const fresh = new webClient.constructor();
  await fresh.connect();
  const socket = FakeWebSocket.instance;
  const originalSend = socket.send;
  const sent = [];
  let processing = true;
  const snapshots = [];
  const offStatus = fresh.on('chat.processing_status', ({ payload }) => {
    processing = payload.is_processing;
  });
  const offSnapshot = fresh.on('runtime.snapshot', ({ payload }) => {
    snapshots.push(payload);
    assert.equal(processing, true);
  });
  socket.send = function (raw) {
    originalSend.call(this, raw);
    const query = JSON.parse(raw);
    sent.push(query);
    const runtime =
      sent.length < 3
        ? { recovery_pending: true, worker_instance: 'existing-worker', retry_after_ms: 1 }
        : { is_processing: true, worker_instance: 'existing-worker', cursor: 2048 };
    queueMicrotask(() =>
      this.receive({ type: 'res', id: query.id, ok: true, payload: { is_processing: true, runtime } }),
    );
  };
  try {
    await fresh.request('session.get_metadata', { session_id: 'fresh-pending' });
    assert.equal(processing, true);
    assert.equal(snapshots.length, 2);
    assert.equal(snapshots[0].recovery_pending, true);
    assert.equal(snapshots[1].cursor, 2048);
    assert.deepEqual(
      sent.map(({ method }) => method),
      Array(3).fill('session.get_metadata'),
    );
    assert.deepEqual(
      sent.slice(1).map(({ params }) => params),
      Array.from({ length: 2 }, () => ({
        session_id: 'fresh-pending',
        runtime_resume: { worker_instance: 'existing-worker', after: 0 },
      })),
    );
  } finally {
    socket.send = originalSend;
    offStatus();
    offSnapshot();
    await fresh.disconnect();
  }
});

test('disconnect during pending recovery prevents another query on the replacement socket', async () => {
  const fresh = new webClient.constructor();
  await fresh.connect();
  FakeWebSocket.instance.receive({
    type: 'event',
    event: 'chat.delta',
    payload: {
      session_id: 'disconnect-session',
      runtime_event: { worker_instance: 'original-worker', sequence: 9 },
    },
  });
  await fresh.disconnect();
  const originalSend = FakeWebSocket.prototype.send;
  const sent = [];
  let releaseSnapshot;
  const snapshot = new Promise((resolve) => {
    releaseSnapshot = resolve;
  });
  const off = fresh.on('runtime.snapshot', releaseSnapshot);
  FakeWebSocket.prototype.send = function (raw) {
    originalSend.call(this, raw);
    const query = JSON.parse(raw);
    sent.push(query);
    queueMicrotask(() =>
      this.receive({
        type: 'res',
        id: query.id,
        ok: true,
        payload: {
          runtime: { recovery_pending: true, retry_after_ms: 1 },
        },
      }),
    );
  };
  try {
    await fresh.connect();
    await snapshot;
    await fresh.disconnect();
    await new Promise((resolve) => setTimeout(resolve, 150));
    assert.equal(sent.length, 1);
  } finally {
    FakeWebSocket.prototype.send = originalSend;
    off();
    await fresh.disconnect();
  }
});

test('late callbacks from a replaced socket preserve current requests, processing and the recovery cursor', async () => {
  const fresh = new webClient.constructor();
  await fresh.connect();
  const oldSocket = FakeWebSocket.instance;
  const oldClose = oldSocket.close;
  // Model a close handshake that finishes after disconnect's 800ms fallback.
  oldSocket.close = function () {
    this.readyState = 2;
  };
  await fresh.disconnect();
  await fresh.connect();
  const currentSocket = FakeWebSocket.instance;
  let processing = true;
  const off = fresh.on('chat.processing_status', ({ payload }) => {
    processing = payload.is_processing;
  });
  try {
    currentSocket.receive({
      type: 'event',
      event: 'chat.delta',
      payload: {
        session_id: 'socket-generation',
        runtime_event: { worker_instance: 'current-worker', sequence: 23 },
      },
    });
    const pending = fresh.request('config.get');
    await Promise.resolve();
    const currentRequest = currentSocket.lastRequest;
    oldSocket.onopen?.();
    oldSocket.receive({
      type: 'event',
      event: 'chat.processing_status',
      payload: {
        session_id: 'socket-generation',
        is_processing: false,
        runtime_event: { worker_instance: 'old-worker', sequence: 999 },
      },
    });
    oldSocket.onerror?.();
    oldClose.call(oldSocket);
    assert.equal(fresh.getState(), 'ready');
    assert.equal(processing, true);
    assert.equal(currentSocket.lastRequest.id, currentRequest.id);
    currentSocket.receive({ type: 'res', id: currentRequest.id, ok: true, payload: { current_socket: true } });
    assert.deepEqual(await pending, { current_socket: true });
    await fresh.disconnect();
    await fresh.connect();
    await new Promise((resolve) => setTimeout(resolve, 0));
    const resumed = FakeWebSocket.instance.lastRequest;
    assert.equal(resumed.method, 'session.get_metadata');
    assert.deepEqual(resumed.params, {
      session_id: 'socket-generation',
      runtime_resume: { worker_instance: 'current-worker', after: 23 },
    });
    FakeWebSocket.instance.receive({
      type: 'res',
      id: resumed.id,
      ok: true,
      payload: {
        runtime: { is_processing: true, worker_instance: 'current-worker' },
      },
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
  } finally {
    off();
    await fresh.disconnect();
  }
});

test('replaced pending connections reject only their own promise on late lifecycle callbacks', async () => {
  for (const callback of ['onopen', 'onerror', 'onclose']) {
    const fresh = new webClient.constructor();
    const pendingConnect = fresh.connect();
    const rejected = assert.rejects(pendingConnect, (error) => error.code === 'WS_CLOSED');
    const oldSocket = FakeWebSocket.instance;
    const lateCallback = oldSocket[callback];
    oldSocket.onopen = undefined;
    await fresh.disconnect();
    await fresh.connect();
    try {
      lateCallback({ code: 1000, reason: 'replaced', wasClean: true });
      await rejected;
      assert.equal(fresh.getState(), 'ready', callback);
      const currentSocket = FakeWebSocket.instance;
      const pending = fresh.request('config.get');
      await Promise.resolve();
      currentSocket.receive({ type: 'res', id: currentSocket.lastRequest.id, ok: true, payload: { callback } });
      assert.deepEqual(await pending, { callback });
    } finally {
      await fresh.disconnect();
    }
  }
});

test('team attachment is fire-and-forget and resets only for reconnect', async () => {
  await webClient.connect();
  resetTeamAttachments();
  const socket = FakeWebSocket.instance;
  const initialCount = socket.sentRequests.length;

  await attachTeamSession('team-session-1', 'team.work.normal');
  assert.equal(socket.sentRequests.length, initialCount + 1);
  assert.deepEqual(socket.lastRequest.params, {
    session_id: 'team-session-1',
    query: '',
    mode: 'team.work.normal',
    attach_only: true,
  });
  assert.equal(socket.lastRequest.is_stream, true);

  await attachTeamSession('team-session-1', 'team.work.normal');
  assert.equal(socket.sentRequests.length, initialCount + 1);

  resetTeamAttachments();
  await attachTeamSession('team-session-1', 'team.work.normal');
  assert.equal(socket.sentRequests.length, initialCount + 2);
});


test('fresh metadata replay leaves completed history out of the active reply and reuses observed cursors', async () => {
  const fresh = new webClient.constructor();
  await fresh.connect();
  const socket = FakeWebSocket.instance;
  const originalSend = socket.send;
  const rendered = [];
  const sent = [];
  const off = fresh.on('chat.delta', ({ payload }) => rendered.push(payload.content));
  const runtime = { worker_instance: 'replay-worker', is_processing: true, dispatches: [
    { dispatch_id: 'finished', active: false, terminal: { event_type: 'chat.final' } },
    { dispatch_id: 'active', active: true, terminal: null },
  ] };
  socket.send = function (raw) {
    originalSend.call(this, raw);
    const query = JSON.parse(raw);
    sent.push(query);
    queueMicrotask(() => {
      this.receive({ type: 'res', id: query.id, ok: true, payload: { runtime } });
      if (query.params.runtime_resume) {
        for (const [sequence, dispatch_id, content] of [[1, 'finished', 'OLD'], [2, 'active', 'CURRENT']]) {
          this.receive({ type: 'event', event: 'chat.delta', payload: {
            session_id: 'replay-session', content,
            runtime_event: { worker_instance: 'replay-worker', sequence, dispatch_id, replayed: true },
          } });
        }
      }
    });
  };
  try {
    await fresh.request('session.get_metadata', { session_id: 'replay-session' });
    assert.deepEqual(rendered, ['CURRENT']);
    await fresh.request('session.get_metadata', { session_id: 'replay-session' });
    assert.equal(sent.at(-1).params.runtime_resume.after, 2);
    assert.deepEqual(rendered, ['CURRENT']);
    assert.ok(sent.every((item) => item.method === 'session.get_metadata'));
  } finally {
    socket.send = originalSend;
    off();
    await fresh.disconnect();
  }
});

test('history metadata returns the recovered state instead of overwriting it with the initial busy snapshot', async () => {
  const fresh = new webClient.constructor();
  await fresh.connect();
  const socket = FakeWebSocket.instance;
  try {
    const pending = fresh.request('session.get_metadata', { session_id: 'history-race' });
    await Promise.resolve();
    socket.receive({ type: 'res', id: socket.lastRequest.id, ok: true, payload: {
      session_id: 'history-race', is_processing: true,
      runtime: { worker_instance: 'worker', is_processing: true, cursor: 1 },
    } });
    await new Promise((resolve) => setTimeout(resolve, 0));
    socket.receive({ type: 'res', id: socket.lastRequest.id, ok: true, payload: {
      session_id: 'history-race', is_processing: false,
      runtime: { worker_instance: 'worker', is_processing: false, cursor: 2 },
    } });
    assert.notEqual((await pending).is_processing, true);
  } finally { await fresh.disconnect(); }
});

test('a live completion wins over a metadata response already in flight', async () => {
  const fresh = new webClient.constructor();
  await fresh.connect();
  const socket = FakeWebSocket.instance;
  const statuses = [];
  const off = fresh.on('chat.processing_status', ({ payload }) => statuses.push(payload.is_processing));
  try {
    const pending = fresh.request('session.get_metadata', { session_id: 'late-snapshot', runtime_resume: { after: 1 } });
    await Promise.resolve();
    const query = socket.lastRequest;
    socket.receive({ type: 'event', event: 'chat.processing_status', payload: { session_id: 'late-snapshot', is_processing: false } });
    socket.receive({ type: 'res', id: query.id, ok: true, payload: {
      title: 'preserve metadata', is_processing: true,
      runtime: { is_processing: true, permissions: { state: 'applied' } },
    } });
    const metadata = await pending;
    assert.equal(metadata.is_processing, undefined);
    assert.equal(metadata.runtime.is_processing, undefined);
    assert.equal(metadata.title, 'preserve metadata');
    assert.deepEqual(metadata.runtime.permissions, { state: 'applied' });
    assert.deepEqual(statuses, [false]);
  } finally { off(); await fresh.disconnect(); }
});

test('metadata updates completed dispatches even after live activity created the cursor', async () => {
  const fresh = new webClient.constructor();
  await fresh.connect();
  const socket = FakeWebSocket.instance;
  const approvals = [];
  const off = fresh.on('chat.ask_user_question', ({ payload }) => approvals.push(payload.request_id));
  const emit = (sequence, dispatch_id, request_id) => socket.receive({ type: 'event', event: 'chat.ask_user_question', payload: {
    session_id: 'controls-session', request_id, source: 'permission_interrupt',
    runtime_event: { worker_instance: 'controls-worker', sequence, dispatch_id, replayed: true },
  } });
  try {
    // A live event may create the cursor before metadata arrives.
    socket.receive({ type: 'event', event: 'chat.processing_status', payload: {
      session_id: 'controls-session', is_processing: true,
      runtime_event: { worker_instance: 'controls-worker', sequence: 20, dispatch_id: 'current' },
    } });
    const pending = fresh.request('session.get_metadata', { session_id: 'controls-session' });
    await Promise.resolve();
    socket.receive({ type: 'res', id: socket.lastRequest.id, ok: true, payload: { runtime: {
      worker_instance: 'controls-worker', is_processing: false, cursor: 21, dispatches: [
        { dispatch_id: 'approved', active: false, terminal: { event_type: 'chat.final' } },
        { dispatch_id: 'cancelled', active: false, terminal: { event_type: 'runtime.completed', state: 'cancelled' } },
        { dispatch_id: 'waiting', active: false, phase: 'waiting_for_control', terminal: { event_type: 'chat.final', final_mode: 'patch_segment' },
          pending_interactions: [{ event_type: 'chat.ask_user_question', request_id: 'still-pending' }] },
      ],
    } } });
    await pending;
    emit(1, 'approved', 'old-allowed');
    emit(2, 'cancelled', 'old-cancelled');
    // The replay journal can retain a control after its dispatch was pruned.
    emit(4, 'pruned-dispatch', 'old-pruned');
    emit(21, 'waiting', 'still-pending');
    assert.deepEqual(approvals, ['still-pending']);
    // A real new approval after the snapshot boundary must not be suppressed.
    socket.receive({ type: 'event', event: 'chat.ask_user_question', payload: {
      session_id: 'controls-session', request_id: 'new-live',
      runtime_event: { worker_instance: 'controls-worker', sequence: 22, dispatch_id: 'new' },
    } });
    assert.deepEqual(approvals, ['still-pending', 'new-live']);
    assert.deepEqual(socket.sentRequests.map(({ method }) => method), ['session.get_metadata']);
  } finally {
    off();
    await fresh.disconnect();
  }
});

test('reconnect snapshot settles an observed dispatch before its queued approval replay', async () => {
  const fresh = new webClient.constructor();
  await fresh.connect();
  const approvals = [];
  const off = fresh.on('chat.ask_user_question', ({ payload }) => approvals.push(payload.request_id));
  FakeWebSocket.instance.receive({ type: 'event', event: 'chat.delta', payload: {
    session_id: 'reconnect-controls', runtime_event: { worker_instance: 'worker', sequence: 3, dispatch_id: 'old-turn' },
  } });
  await fresh.disconnect();
  const originalSend = FakeWebSocket.prototype.send;
  FakeWebSocket.prototype.send = function (raw) {
    originalSend.call(this, raw);
    const query = JSON.parse(raw);
    queueMicrotask(() => {
      this.receive({ type: 'res', id: query.id, ok: true, payload: { runtime: {
        worker_instance: 'worker', is_processing: false, dispatches: [
          { dispatch_id: 'old-turn', active: false, terminal: { event_type: 'chat.final' } },
        ],
      } } });
      this.receive({ type: 'event', event: 'chat.ask_user_question', payload: {
        session_id: 'reconnect-controls', request_id: 'already-answered', source: 'permission_interrupt',
        runtime_event: { worker_instance: 'worker', sequence: 4, dispatch_id: 'old-turn', replayed: true },
      } });
    });
  };
  try {
    await fresh.connect();
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.deepEqual(approvals, []);
    assert.deepEqual(FakeWebSocket.instance.lastRequest.params.runtime_resume, { worker_instance: 'worker', after: 3 });
  } finally {
    FakeWebSocket.prototype.send = originalSend;
    off();
    await fresh.disconnect();
  }
});

test('expired dispatch replay before reconnect snapshot cannot reopen completed history', async () => {
  const fresh = new webClient.constructor();
  await fresh.connect();
  const socket = FakeWebSocket.instance;
  const observed = [];
  const history = [];
  const offHistory = fresh.on('runtime.history_required', ({ payload }) => history.push(payload.session_id));
  const offs = ['chat.delta', 'chat.final', 'chat.reasoning'].map(kind => fresh.on(kind, ({ payload }) => observed.push(payload.request_id)));
  const emit = (kind, sequence, dispatch, request) => socket.receive({ type: 'event', event: kind, payload: {
    session_id: 'retained-history', request_id: request, output_phase_id: 'old-phase', content: 'retained output',
    runtime_event: { worker_instance: 'resident', sequence, dispatch_id: dispatch, replayed: true },
  } });
  try {
    const metadata = fresh.request('session.get_metadata', { session_id: 'retained-history' });
    await Promise.resolve();
    socket.receive({ type: 'res', id: socket.lastRequest.id, ok: true, payload: { runtime: {
      worker_instance: 'resident', cursor: 2025, is_processing: false, history_required: false,
      dispatches: [{ dispatch_id: 'inspection', active: true, terminal: null }],
    } } });
    await metadata;
    // Captured ui-d ordering: old frames 22..50 precede the reconnect snapshot.
    emit('chat.final', 22, 'expired-first', 'completed-request');
    emit('chat.delta', 32, 'expired-second', 'completed-request');
    emit('chat.final', 50, 'expired-second', 'completed-request');
    assert.deepEqual(observed, []);
    assert.deepEqual(history, ['retained-history'], 'reload durable completion once, never resend input');
    // New execution after that snapshot must not be lost.
    emit('chat.delta', 2026, 'new-dispatch', 'new-request');
    assert.deepEqual(observed, ['new-request']);
    const active = fresh.request('session.get_metadata', { session_id: 'retained-history', runtime_resume: { after: 2026 } });
    await Promise.resolve();
    socket.receive({ type: 'res', id: socket.lastRequest.id, ok: true, payload: { runtime: {
      worker_instance: 'resident', cursor: 2050, is_processing: true,
      dispatches: [{ dispatch_id: 'new-dispatch', active: true, terminal: null }],
    } } });
    await active;
    emit('chat.delta', 2030, 'new-dispatch', 'new-request');
    assert.deepEqual(observed, ['new-request', 'new-request']);
    assert.ok(socket.sentRequests.every(request => request.method === 'session.get_metadata'));
  } finally { offHistory(); offs.forEach(off => off()); await fresh.disconnect(); }
});

const { RuntimeResume } = await import('../node_modules/.cache/web-client-runtime-ack/runtimeResume.mjs');
for (const state of ['idle', 'active', 'waiting']) {
  test(`initial ${state} snapshot selects the correct replay boundary`, () => {
    const resume = new RuntimeResume();
    const runtime = { worker_instance: 'worker', cursor: 2025, is_processing: state === 'active',
      dispatches: state === 'waiting' ? [{ dispatch_id: 'waiting', phase: 'waiting_for_control', pending_interactions: [{ request_id: 'control' }] }] : [] };
    assert.equal(resume.queryFromSnapshot('session', runtime).runtime_resume.after, state === 'idle' ? 2025 : 0);
  });
}
test('new worker and older metadata cannot inherit or regress replay boundaries', () => {
  const resume = new RuntimeResume();
  resume.queryFromSnapshot('session', {worker_instance:'old',cursor:100,is_processing:false,dispatches:[]});
  assert.equal(resume.queryFromSnapshot('session', {worker_instance:'old',cursor:50,is_processing:false,dispatches:[]}).runtime_resume.after,100);
  assert.equal(resume.queryFromSnapshot('session', {worker_instance:'new',cursor:3,is_processing:true,dispatches:[]}).runtime_resume.after,0);
});

test('an already observed empty journal still recovers output completed while offline', () => {
  const resume = new RuntimeResume();
  resume.queryFromSnapshot('session', {worker_instance:'worker',cursor:0,is_processing:false,dispatches:[]});
  assert.equal(resume.queryFromSnapshot('session', {worker_instance:'worker',cursor:50,is_processing:false,dispatches:[]}).runtime_resume.after,0);
});

const waitingSnapshot = (overrides = {}) => ({
  worker_instance: 'waiting-worker', cursor: 3351, is_processing: true, history_required: false,
  dispatches: [{ dispatch_id: 'waiting', active: false, phase: 'waiting_for_control',
    pending_interactions: [{ event_type: 'chat.ask_user_question', request_id: 'original-control',
      source: 'permission_interrupt', question: 'Original permission' }] }],
  executions: [{ state: 'waiting_for_control', waiting_control_id: 'original-control' }],
  ...overrides,
});

test('fresh waiting page restores the original control without replaying the old journal or resending input', async () => {
  const fresh = new webClient.constructor();
  await fresh.connect();
  const socket = FakeWebSocket.instance;
  const controls = [];
  const off = fresh.on('chat.ask_user_question', ({ payload }) => controls.push(payload));
  try {
    const pending = fresh.request('session.get_metadata', { session_id: 'waiting-page' });
    await Promise.resolve();
    socket.receive({ type: 'res', id: socket.lastRequest.id, ok: true, payload: { runtime: waitingSnapshot() } });
    await new Promise(resolve => setTimeout(resolve, 0));
    assert.equal(socket.lastRequest.params.runtime_resume.after, 3351);
    socket.receive({ type: 'res', id: socket.lastRequest.id, ok: true, payload: { runtime: waitingSnapshot() } });
    await pending;
    assert.deepEqual(controls.map(control => [control.request_id, control.source, control.session_id]),
      [['original-control', 'permission_interrupt', 'waiting-page']]);
    assert.deepEqual(socket.sentRequests.map(request => request.method), ['session.get_metadata', 'session.get_metadata']);
  } finally { off(); await fresh.disconnect(); }
});

for (const executions of [undefined, [], [{ state: 'running' }], [{ state: 'queued' }],
  [{ state: 'waiting_for_control', waiting_control_id: 'missing-control' }],
  [{ state: 'waiting_for_control', waiting_control_id: 'original-control' }, { state: 'running' }]]) {
  test(`incomplete or concurrent execution snapshot retains replay: ${JSON.stringify(executions)}`, () => {
    const resume = new RuntimeResume();
    assert.equal(resume.queryFromSnapshot('waiting-page', waitingSnapshot({ executions })).runtime_resume.after, 0);
    assert.equal(resume.takePendingRestore('waiting-page', waitingSnapshot({ executions })), false);
  });
}

test('live completion while subscribing cannot restore an obsolete pending control', () => {
  const resume = new RuntimeResume();
  resume.queryFromSnapshot('waiting-page', waitingSnapshot());
  resume.observe({ type: 'event', event: 'chat.request_completed', payload: {
    session_id: 'waiting-page', runtime_event: { worker_instance: 'waiting-worker', sequence: 3352, dispatch_id: 'waiting' },
  } });
  assert.equal(resume.takePendingRestore('waiting-page', waitingSnapshot()), false);
  assert.equal(resume.takePendingRestore('waiting-page', waitingSnapshot({ cursor: 3352 })), false);
});
