import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createInterface } from 'node:readline';
import { once } from 'node:events';
import { test } from 'node:test';

async function open(db) {
  const child = spawn(process.execPath, ['dist/main.mjs', db], { stdio: ['pipe', 'pipe', 'inherit'] });
  const lines = createInterface({ input: child.stdout })[Symbol.asyncIterator]();
  let count = 0;
  async function call(method, params = {}) {
    const id = String(++count);
    child.stdin.write(JSON.stringify({ id, method, params }) + '\n');
    const line = await lines.next();
    assert.equal(line.done, false, 'coordinator closed before responding');
    const data = JSON.parse(line.value);
    assert.equal(data.id, id);
    if (!data.ok) throw Error(data.code);
    return data.result;
  }
  await call('initialize', { members: ['alice', 'bob'] });
  return {
    call,
    async close() {
      const exit = once(child, 'exit');
      child.stdin.end();
      await exit;
    },
  };
}

const request = (operation_id, text, owner = 'alice') => ({ operation_id, text, owner });
const route = async (side, decision) => {
  const op = await side.call('claim', { kind: 'route' });
  assert.ok(op);
  await side.call('route_result', { operation_id: op.id, decision, router_session_id: 'router-one' });
  return op;
};

test('explicit Router decisions control ticket creation, attachment and revocation', async () => {
  const home = await mkdtemp(join(tmpdir(), 'superagent-test-'));
  const side = await open(join(home, 'state.sqlite'));
  const c = side.call;
  try {
    const submitted = await c('submit', request('one', 'Write the fixture'));
    assert.equal((await c('submit', request('one', 'Write the fixture'))).id, submitted.id);
    await assert.rejects(c('submit', request('one', 'Other text')), /CONFLICT/);
    await route(side, { action: 'accept', title: 'Fixture', instruction: 'Write a fixture', reason: 'New request' });
    const ticket = (await c('requests', { owner: 'alice' }))[0].ticket;
    await assert.rejects(c('ticket', { ticket_id: ticket.id, owner: 'bob' }), /NOT_FOUND/);
    await c('submit', request('two', 'Add a line to the same fixture'));
    await route(side, { action: 'attach', ticket_id: ticket.id, instruction: 'Add a line', reason: 'Same task' });
    assert.equal((await c('requests', { owner: 'alice' }))[0].ticket.id, ticket.id);
    await c('submit', request('three', 'Thanks'));
    await route(side, { action: 'ignore', reason: 'No task' });
    assert.equal((await c('requests', { owner: 'alice' }))[0].status, 'ignore');
    const work = await c('claim', { kind: 'worker' });
    assert.equal(work.kind, 'start');
    assert.equal(work.instruction, 'Write a fixture');
    await c('bound', { operation_id: work.id, session_id: 'opencode-one', project_dir: home });
    await c('report', { operation_id: work.id, report: { state: 'ready', summary: 'Done' } });
    const next = await c('claim', { kind: 'worker' });
    assert.equal(next?.session_id, 'opencode-one');
    assert.equal(next?.project_dir, home);
    await c('cancel', { owner: 'alice', ticket_id: ticket.id });
    const stop = await c('claim', { kind: 'stop' });
    assert.equal(stop?.session_id, 'opencode-one');
    await c('stopped', { operation_id: stop.id });
    await assert.rejects(c('report', { operation_id: next.id, report: { state: 'ready', summary: 'Late' } }),
      /STALE_OPERATION/);
  } finally {
    await side.close();
    await rm(home, { recursive: true, force: true });
  }
});

test('a lost execution response stays uncertain on restart and cannot be replayed', async () => {
  const home = await mkdtemp(join(tmpdir(), 'superagent-test-'));
  const db = join(home, 'state.sqlite');
  let side = await open(db);
  try {
    await side.call('submit', request('one', 'Write the fixture'));
    await route(side, { action: 'accept', title: 'Fixture', instruction: 'Write it', reason: 'New request' });
    const claimed = await side.call('claim', { kind: 'worker' });
    assert.equal(claimed?.kind, 'start');
    await side.close();
    side = await open(db);
    assert.equal(await side.call('claim', { kind: 'worker' }), null);
    assert.equal((await side.call('requests', { owner: 'alice' }))[0].ticket.uncertain, true);
  } finally {
    await side.close();
    await rm(home, { recursive: true, force: true });
  }
});

test('revocation fences dispatch and allows only stop to be retried after restart', async () => {
  const home = await mkdtemp(join(tmpdir(), 'superagent-test-'));
  const db = join(home, 'state.sqlite');
  let side = await open(db);
  try {
    await side.call('submit', request('one', 'Write the fixture'));
    await route(side, { action: 'accept', title: 'Fixture', instruction: 'Write it', reason: 'New request' });
    const work = await side.call('claim', { kind: 'worker' });
    await side.call('bound', { operation_id: work.id, session_id: 'opencode-one', project_dir: home });
    const ticket = { owner: 'alice', ticket_id: work.ticketId };
    await side.call('cancel', ticket);
    assert.equal(await side.call('dispatchable', { operation_id: work.id }), false);
    const stop = await side.call('claim', { kind: 'stop' });
    await side.close();
    side = await open(db);
    assert.equal((await side.call('ticket', ticket)).stop, 'uncertain');
    assert.equal(await side.call('claim', { kind: 'stop' }), null);
    assert.equal((await side.call('cancel', ticket)).stop, 'queued');
    const retry = await side.call('claim', { kind: 'stop' });
    assert.equal(retry.id, stop.id);
    assert.equal(retry.session_id, 'opencode-one');
    assert.equal(await side.call('claim', { kind: 'worker' }), null);
    await side.call('stopped', { operation_id: retry.id });
    assert.equal((await side.call('ticket', ticket)).stop, 'done');
  } finally {
    await side.close();
    await rm(home, { recursive: true, force: true });
  }
});
