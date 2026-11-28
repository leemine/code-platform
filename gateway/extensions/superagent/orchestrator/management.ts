import { latestAssignment, threadKey, ticketStage, type Decision, type Ticket, type Trigger }
  from './vendor/superagent/src/core/index.ts'
import type { Store, Operation } from './sqlite.ts'

type Binding = { session_id: string }
type Params = Record<string, unknown>

const preview = (text: string) => text.slice(0, 240)
const hostSource = (id: string) => ({
  id, title: { zh: 'WorkSwarm Web', en: 'WorkSwarm Web' }, installed: true,
  enabled: true, state: 'ready', health: [], fields: [], filtered: [],
})

function paginate<T>(items: T[], params: Params) {
  const offset = Math.min(1_000_000, Math.max(0, Number(params.offset) || 0))
  const limit = Math.min(100, Math.max(1, Number(params.limit) || 30))
  return { items: items.slice(offset, offset + limit), next_offset: offset + limit < items.length ? offset + limit : null }
}

export function managementView(store: Store, owner: string, params: Params, source: string) {
  const tickets = store.tickets.list().filter(ticket => ticket.mandate.actor.id === owner)
  const triggers = store.list<Trigger>('trigger').filter(trigger => trigger.actor.id === owner)
  const triggerIds = new Set(triggers.map(trigger => trigger.id))
  const threadKeys = new Set(triggers.flatMap(trigger => trigger.threads.map(threadKey)))
  const decisions = store.list<Decision>('decision').filter(decision =>
    decision.triggerIds.some(id => triggerIds.has(id))).reverse()
  const operations = store.list<Operation>('operation')
  const ownIds = new Set(tickets.map(ticket => ticket.id))
  const workers = operations.filter(operation => operation.ticketId && ownIds.has(operation.ticketId)
    && ['start', 'deliver'].includes(operation.kind))
  const load = {
    running: workers.some(operation => operation.state === 'claimed') ? 1 : 0,
    queued: workers.filter(operation => operation.state === 'queued').length,
    maxWorkers: 1,
  }
  const actor = { source, id: owner, name: owner }
  const row = (ticket: Ticket) => {
    const stage = ticketStage(ticket)
    const attention = ticket.attention
    const report = latestAssignment(ticket)?.report
    return {
      id: ticket.id, title: ticket.title, ...stage,
      state: ticket.ended ? 'ended' : 'open', ended: ticket.ended,
      attention, note: attention ? { text: attention.question, error: false } : undefined,
      strength: ticket.mandate.strength, assignments: ticket.assignments.length,
      undelivered: ticket.undelivered.length, inputs: ticket.inputs.length,
      summary: report?.summary ?? '', createdAt: ticket.createdAt, updatedAt: ticket.updatedAt,
      sessionId: store.get<Binding>('binding', ticket.id)?.session_id ?? '',
      actions: { retry: false, stop: !ticket.ended },
      threads: threadRecords.filter(thread => thread.subscriptions.includes(ticket.id)).map(thread => ({
        key: thread.key, source, facts: {},
        title: preview(triggers.find(trigger => trigger.threads.some(ref => threadKey(ref) === thread.key))
          ?.text ?? thread.key),
      })),
    }
  }
  const threadRecords = store.threads.list().filter(thread => threadKeys.has(thread.key))
  const threads = threadRecords.map(thread => {
    const messages = triggers.filter(trigger => trigger.threads.some(ref => threadKey(ref) === thread.key))
    const last = messages.at(-1)
    const related = tickets.filter(ticket => thread.subscriptions.includes(ticket.id)).map(row)
    return {
      key: thread.key, title: preview(messages[0]?.text ?? thread.key), source,
      lastAt: thread.lastAt ?? thread.createdAt, createdAt: thread.createdAt,
      stage: thread.evaluating ? 'evaluating' : thread.pending.length ? 'queued'
        : related.some(ticket => ticket.state === 'open') ? 'subscribed' : related.length ? 'dormant' : 'unsubscribed',
      tickets: related, subscriptions: related.length, facts: {}, pending: thread.pending.length,
      latest: last && { actor, human: true, at: last.at, preview: preview(last.text) },
      evaluating: thread.evaluating && { ...thread.evaluating, triggers: thread.evaluating.triggerIds.length },
    }
  }).reverse()
  const decisionRows = decisions.map(item => {
    const trigger = triggers.find(value => item.triggerIds.includes(value.id))
    const route = trigger && store.get<{ reason: string }>('router_decision', trigger.id)
    return {
      ...item, outcome: item.kind, reason: route?.reason ?? item.reason, thread: item.threadKey,
      threadTitle: threads.find(thread => thread.key === item.threadKey)?.title,
      rules: [], preview: trigger ? preview(trigger.text) : '',
      ticketTitle: tickets.find(ticket => ticket.id === item.ticketId)?.title,
    }
  })
  const triggerRow = (trigger: Trigger) => {
    const disposition = store.triggers.disposition(trigger.id)
    const decision = decisionRows.find(item => item.triggerIds.includes(trigger.id))
    const thread = threads.find(item => item.key === threadKey(trigger.threads[0]!))
    const fanout = disposition?.fanout.filter(id => ownIds.has(id)) ?? []
    return {
      id: trigger.id, source, actor, human: true, at: trigger.at, text: trigger.text,
      preview: preview(trigger.text), threads: trigger.threads.map(threadKey), threadTitle: thread?.title,
      actions: { requeue: false },
      disposition: {
        fanout, handbacks: [], queued: thread?.stage === 'queued', evaluating: thread?.stage === 'evaluating',
        delivered: fanout.length > 0, filtered: disposition?.filtered, decision,
      },
    }
  }
  const ticketRows = tickets.map(row)

  switch (params.view) {
    case 'state':
      return { load, paused: false, health: {}, setup: { machine: {}, accounts: null, problem: null, feishuProblem: null } }
    case 'overview': {
      const dayAgo = new Date(Date.now() - 86_400_000).toISOString()
      const recent = triggers.filter(trigger => trigger.at >= dayAgo)
      const judged = decisions.filter(decision => decision.at >= dayAgo)
      return {
        problems: [], person: ticketRows.filter(ticket => ticket.stage === 'person'),
        executor: { ...load, idle: ticketRows.filter(ticket => ticket.stage === 'idle').length },
        flow: { received: recent.length, filtered: 0, triggers: recent.length,
          judged: judged.length, accepted: judged.filter(decision => decision.kind === 'accept').length,
          evaluating: threads.filter(thread => thread.stage === 'evaluating').length, dropped: 0 },
      }
    }
    case 'sources':
      return [{ ...hostSource(source), dropped: [],
        stats: { received: triggers.length, filtered: 0, lastAt: triggers.at(-1)?.at } }]
    case 'tickets':
      return paginate(ticketRows.filter(ticket => params.state === 'open'
        ? ticket.state === 'open' : ticket.stage === params.state), params)
    case 'ticket': {
      const ticket = tickets.find(item => item.id === params.id)
      if (!ticket) return null
      return {
        ...row(ticket), environment: [], assignments: ticket.assignments, paused: false, channels: [],
        threads: threads.filter(thread => thread.tickets.some(item => item.id === ticket.id)),
        decision: decisionRows.find(item => item.id === ticket.decisionId),
        mandate: { ...ticket.mandate, actor }, basis: { legacy: false, facts: [] },
        inputs: ticket.inputs.slice().reverse().map(input => ({
          ...input, delivered: !ticket.undelivered.includes(input.id),
          trigger: input.kind === 'trigger' && triggers.find(trigger => trigger.id === input.triggerId)
            ? triggerRow(triggers.find(trigger => trigger.id === input.triggerId)!) : undefined,
        })),
      }
    }
    case 'threads':
      return paginate(threads.filter(item => params.filter === 'all'
        || params.filter === 'recent' && Date.parse(item.lastAt) >= Date.now() - 86_400_000
        || params.filter === 'evaluating' && ['queued', 'evaluating'].includes(item.stage)
        || params.filter === item.stage), params)
    case 'thread': {
      const thread = threads.find(item => item.key === params.id)
      if (!thread) return null
      return {
        ...thread, context: [], correlated: [], earlier: null,
        decisions: decisionRows.filter(item => item.thread === thread.key),
        timeline: triggers.filter(trigger => trigger.threads.some(ref => thread.key === threadKey(ref))).map(triggerRow),
      }
    }
    case 'decisions': {
      const kinds = typeof params.kind === 'string' ? params.kind.split(',') : []
      return paginate(decisionRows.filter(item => (!kinds.length || kinds.includes(item.outcome))
        && (params.window !== '24h' || Date.parse(item.at) >= Date.now() - 86_400_000)), params)
    }
    case 'search': {
      const query = typeof params.q === 'string' ? params.q.trim().toLowerCase() : ''
      const matches = (...items: string[]) => query && items.some(item => item.toLowerCase().includes(query))
      return {
        tickets: ticketRows.filter(item => matches(item.id, item.title)).slice(0, 10),
        threads: threads.filter(item => matches(item.key, item.title)).slice(0, 10),
        items: triggers.filter(item => matches(item.id, item.text)).reverse().slice(0, 20).map(triggerRow),
      }
    }
    default:
      return null
  }
}
