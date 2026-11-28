import { createInterface } from 'node:readline'
import { z } from 'zod'
import { managementView } from './management.ts'
import { Engine, key, latestAssignment, ticketStage, type Ticket, type Trigger, type WorkerReport }
  from './vendor/superagent/src/core/index.ts'
import { SettingsSchema, settingsPolicy } from './vendor/superagent/src/policy.ts'
import { Store, type Operation } from './sqlite.ts'

const source = 'superagent-web'
const Identifier = z.string().min(1).max(160)
const Text = z.string().trim().min(1).max(12_000)
const Decision = z.discriminatedUnion('action', [
  z.object({ action: z.literal('accept'), title: z.string().trim().min(1).max(140),
    instruction: Text, reason: z.string().trim().min(1).max(1000) }).strict(),
  z.object({ action: z.literal('attach'), ticket_id: Identifier, instruction: Text,
    reason: z.string().trim().min(1).max(1000) }).strict(),
  z.object({ action: z.literal('ignore'), reason: z.string().trim().min(1).max(1000) }).strict(),
])
const Report = z.object({ state: z.enum(['ready', 'blocked', 'failed']), summary: Text,
  question: z.string().trim().min(1).max(1000).optional() }).strict()
type Args = Record<string, unknown>
type RequestRecord = { owner: string, triggerId: string, ticketId?: string, digest: string,
  explicitFollow?: boolean, topicId?: string, citation?: unknown }
type Topic = { owner: string, triggerId: string }
const Evidence = z.object({ citation: z.unknown(), content: z.string().max(8000) }).strict()
type Binding = { session_id: string, project_dir: string, owner: string }

class Refusal extends Error {
  constructor(readonly code: string) { super(code) }
}

const store = new Store(process.argv[2]!)
const scope = { scope: () => ({ listened: true as const, observed: false }) }
let members: string[] = []
let configured = false

const engine = new Engine({
  repo: store, outbox: store.outbox, scope,
  policy: () => settingsPolicy(SettingsSchema.parse({
    eval: { mode: 'off' },
    policy: { sources: { [source]: { allowed: members.map(id => ({ id })) } } },
  }), scope),
  assessor: {
    request(candidate) {
      store.queue({ id: key('route', candidate.evalId), kind: 'route',
        evalId: candidate.evalId, triggerId: candidate.triggers[0]!.id })
    },
  },
  executor: {
    start(ticket, assignment) {
      store.queue({ id: key('start', assignment.id), kind: 'start',
        ticketId: ticket.id, assignmentId: assignment.id })
    },
    deliver(ticket, assignment) {
      const ids = [...ticket.undelivered]
      if (ids.length) store.queue({ id: key('deliver', assignment.id, ...ids), kind: 'deliver',
        ticketId: ticket.id, assignmentId: assignment.id, inputIds: ids })
    },
    stop(ticket, assignment) {
      if (ticket.ended?.by !== 'human') return
      store.queue({ id: key('stop', assignment.id), kind: 'stop',
        ticketId: ticket.id, assignmentId: assignment.id })
    },
  },
  prepareTicket: (ticket, decision) => ({
    ...ticket, execution: { name: ticket.id, directory: '', assignment: decision.note ?? decision.title },
  }),
})

function user(value: unknown): string {
  const owner = Identifier.parse(value)
  if (!members.includes(owner)) throw new Refusal('FORBIDDEN')
  return owner
}

function ownedTicket(id: string, owner: string): Ticket {
  const ticket = store.tickets.get(id)
  if (!ticket || ticket.mandate.actor.id !== owner) throw new Refusal('NOT_FOUND')
  return ticket
}

function ticketOperations(id: string) {
  return store.list<Operation>('operation').filter(operation => operation.ticketId === id)
}

function projection(ticket: Ticket) {
  const operations = ticketOperations(ticket.id)
  const binding = store.get<Binding>('binding', ticket.id)
  const stop = operations.findLast(operation => operation.kind === 'stop')
  return {
    id: ticket.id, title: ticket.title, stage: ticketStage(ticket), outcome: ticket.ended?.outcome,
    assignments: ticket.assignments, attention: ticket.attention, session_id: binding?.session_id,
    report: latestAssignment(ticket)?.report, ended: ticket.ended,
    uncertain: operations.some(operation => operation.state === 'uncertain'),
    stop: stop?.state,
  }
}

function requestProjection(record: RequestRecord) {
  const triggerId = record.triggerId
  const disposition = store.triggers.disposition(triggerId)
  const decision = disposition?.decisionId ? store.decisions.get(disposition.decisionId) : undefined
  const ticketId = record.ticketId ?? decision?.ticketId
  const route = store.get<{ action: string, reason: string }>('router_decision', triggerId)
  const ticket = ticketId ? ownedTicket(ticketId, record.owner) : undefined
  const uncertainty = store.list<Operation>('operation').some(operation =>
    operation.triggerId === triggerId && operation.state === 'uncertain')
  return {
    id: triggerId, route, ticket: ticket ? projection(ticket) : undefined,
    status: uncertainty ? 'uncertain' : route?.action ?? decision?.kind ?? 'routing',
  }
}

function receive(params: Args, follow: boolean) {
  const owner = user(params.owner)
  const requestId = Identifier.parse(params.operation_id)
  const text = Text.parse(params.text)
  const ticketId = follow ? Identifier.parse(params.ticket_id) : undefined
  const triggerId = key('request', owner, requestId)
  const topicId = Identifier.optional().parse(params.topic_id)
  const evidence = Evidence.optional().parse(params.evidence)
  const ruling = Identifier.optional().parse(params.attention_id)
  const digest = topicId || evidence || ruling
    ? key('payload', ticketId ?? '', text, topicId ?? '', JSON.stringify(evidence ?? null), ruling ?? '')
    : key('payload', ticketId ?? '', text)
  const prior = store.get<RequestRecord>('request', triggerId)
  if (prior) {
    if (prior.digest !== digest) throw new Refusal('CONFLICT')
    return requestProjection(prior)
  }
  const ticket = ticketId ? ownedTicket(ticketId, owner) : undefined
  if (ticket?.ended?.by === 'human') throw new Refusal('TICKET_STOPPED')
  if (ticket && projection(ticket).uncertain) throw new Refusal('EXECUTION_UNCERTAIN')
  if (ruling && (!ticket?.attention || ticket.attention.id !== ruling
      || latestAssignment(ticket)?.report?.state !== 'blocked')) throw new Refusal('STALE_INTERACTION')
  if (ruling) {
    if (store.get('ruling', ruling)) throw new Refusal('STALE_INTERACTION')
    store.put('ruling', ruling, { ticketId, triggerId, choice: params.choice })
  }
  // Explicit follow-ups use a private Core thread dedicated to this Ticket.
  // The first input attaches it before evaluation. Later inputs fan out only to it.
  const thread = ticket ? key('worker-thread', owner, ticket.id) : triggerId
  const trigger: Trigger = {
    id: triggerId, source, threads: [{ source, id: thread }], actor: { source, id: owner },
    human: true, addressed: 'direct', text, at: new Date().toISOString(),
    channel: { source, thread, address: { messageId: triggerId } }, meta: {},
  }
  const record = { owner, triggerId, ticketId, digest, explicitFollow: follow,
    topicId, citation: evidence?.citation }
  store.put('request', triggerId, record)
  if (evidence) store.put('reference', triggerId, evidence.content)
  engine.receive(trigger)
  if (ticket) {
    if (!store.triggers.disposition(triggerId)?.fanout.includes(ticket.id)) {
      engine.attach(ticket.id, triggerId)
    }
  } else engine.evaluateDue()
  return requestProjection(record)
}

function settle(operation: Operation, state: Operation['state'] = 'done') {
  store.put('operation', operation.id, { ...operation, state })
}

function activeTicket(operation: Operation) {
  const ticket = store.tickets.get(operation.ticketId ?? '')
  return ticket && !ticket.ended && latestAssignment(ticket)?.id === operation.assignmentId ? ticket : undefined
}

function claim(kind: string) {
  if (kind === 'route') engine.evaluateDue()
  const all = store.list<Operation>('operation')
  if (kind === 'worker' && all.some(operation => ['start', 'deliver'].includes(operation.kind)
      && ['claimed', 'uncertain'].includes(operation.state))) return null
  for (const operation of all) {
    const matches = kind === 'worker' ? ['start', 'deliver'].includes(operation.kind) : operation.kind === kind
    if (!matches || operation.state !== 'queued') continue
    if (kind === 'route') {
      const candidate = engine.candidate(operation.triggerId!)
      if (!candidate || operation.evalId !== candidate.evalId) { settle(operation); continue }
      const trigger = store.triggers.get(operation.triggerId!)!
      if (!members.includes(trigger.actor.id)) { settle(operation); continue }
      if (store.get<RequestRecord>('request', trigger.id)?.explicitFollow) {
        engine.decide(trigger.id, { kind: 'ignore', evalId: candidate.evalId,
          reason: 'Explicit follow-up stays with its original Ticket' })
        settle(operation)
        continue
      }
      const tickets = store.tickets.list().filter(ticket => ticket.mandate.actor.id === trigger.actor.id
        && ticket.ended?.by !== 'human').slice(0, 20).map(ticket => ({ id: ticket.id, title: ticket.title }))
      engine.candidateDelivered(candidate.evalId)
      settle(operation, 'claimed')
      return { ...operation, owner: trigger.actor.id, text: trigger.text, tickets }
    }
    const ticket = kind === 'stop' ? store.tickets.get(operation.ticketId!) : activeTicket(operation)
    if (!ticket) { settle(operation); continue }
    const binding = store.get<Binding>('binding', ticket.id)
    const owner = ticket.mandate.actor.id
    if (kind === 'stop') {
      if (!binding) {
        const start = all.find(item => item.ticketId === ticket.id && item.kind === 'start'
          && ['claimed', 'uncertain'].includes(item.state))
        if (start?.state === 'uncertain') { settle(operation, 'uncertain'); continue }
        if (start) continue
      }
      settle(operation, 'claimed')
      return { ...operation, owner, session_id: binding?.session_id }
    }
    if (!members.includes(owner)) { settle(operation, 'uncertain'); return null }
    const origin = store.triggers.get(ticket.origin.triggerId)
    const inputIds = (operation.inputIds ?? []).filter(id => ticket.undelivered.includes(id))
    const inputs = ticket.inputs.flatMap(input => inputIds.includes(input.id) && input.kind === 'trigger'
      ? [{ text: store.triggers.get(input.triggerId)?.text ?? '', note: input.note, reference: store.get<string>('reference', input.triggerId) }] : [])
    if (operation.kind === 'deliver' && (!binding || inputs.length === 0)) { settle(operation); continue }
    settle(operation, 'claimed')
    return {
      ...operation, inputIds, owner, session_id: binding?.session_id, project_dir: binding?.project_dir,
      title: ticket.title,
      instruction: ticket.execution?.assignment, original: origin?.text,
      reference: origin && store.get<string>('reference', origin.id), inputs,
    }
  }
  return null
}

function boundTicket(sessionId: string, owner: string) {
  const id = store.get<string>('session_ticket', sessionId)
    ?? store.tickets.list().find(ticket =>
      store.get<Binding>('binding', ticket.id)?.session_id === sessionId)?.id
  if (!id) throw new Refusal('NOT_FOUND')
  return ownedTicket(id, owner)
}

function topics(owner: string, topicId?: string) {
  const records = store.list<RequestRecord>('request').filter(record => record.owner === owner)
  return store.list<Topic>('topic').filter(topic => topic.owner === owner)
    .flatMap(topic => {
      const root = store.get<RequestRecord>('request', topic.triggerId)!
      if (topicId && root.topicId !== topicId) return []
      const route = requestProjection(root)
      const messages = records.filter(record => record.topicId === root.topicId
          || (route.ticket && record.explicitFollow && record.ticketId === route.ticket.id && !record.topicId))
        .map(record => {
          const trigger = store.triggers.get(record.triggerId)!
          return { id: trigger.id, text: trigger.text, at: trigger.at, citation: record.citation }
        })
      const ticket = route.ticket && store.tickets.get(route.ticket.id)
      const topicsTriggers = new Set(messages.map(message => message.id))
      const relatedInputs = ticket?.inputs.filter(input => input.kind === 'trigger'
        && topicsTriggers.has(input.triggerId)).map(input => input.id) ?? []
      const reports = ticket ? ticketOperations(ticket.id).flatMap(operation => {
        if (!operation.report) return []
        const matches = operation.kind === 'start' ? topicsTriggers.has(ticket.origin.triggerId)
          : operation.inputIds?.some(id => relatedInputs.includes(id))
        return matches ? [{ id: operation.id, ...operation.report }] : []
      }) : []
      return [{ id: root.topicId, messages, reports, ticket: route.ticket, route: route.route,
        status: route.status, citation: root.citation,
        ruling: route.ticket?.attention && store.get('ruling', route.ticket.attention.id) }]
    }).slice(-100)
}

function workbenchMessage(params: Args) {
  const owner = user(params.owner)
  const topicId = Identifier.parse(params.topic_id)
  const known = store.get<Topic>('topic', key('topic', owner, topicId))
  if (params.is_follow === true) {
    if (!known) throw new Refusal('NOT_FOUND')
    const root = store.get<RequestRecord>('request', known.triggerId)!
    const ticket = requestProjection(root).ticket
    if (!ticket?.session_id) throw new Refusal('CONFLICT')
    return receive({ ...params, ticket_id: ticket.id }, true)
  }
  const result = receive(params, false)
  if (known && known.triggerId !== result.id) throw new Refusal('CONFLICT')
  if (!known) store.put('topic', key('topic', owner, topicId), { owner, triggerId: result.id })
  return result
}

function dispatch(method: string, params: Args) {
  if (method === 'initialize') {
    if (configured) throw new Refusal('ALREADY_CONFIGURED')
    members = z.array(Identifier).min(1).parse(params.members)
    for (const operation of store.list<Operation>('operation')) {
      if (operation.state !== 'claimed') continue
      if (operation.kind === 'route') settle(operation, 'queued')
      else settle(operation, 'uncertain')
    }
    configured = true
    return { api_version: 1 }
  }
  if (!configured) throw new Refusal('NOT_CONFIGURED')
  if (method === 'submit' || method === 'follow') return receive(params, method === 'follow')
  if (method === 'managed_session') {
    return projection(boundTicket(Identifier.parse(params.session_id), user(params.owner)))
  }
  if (method === 'workbench_message') return workbenchMessage(params)
  if (method === 'workbench_ruling') {
    z.enum(['published', 'exception']).parse(params.choice)
    const [topic] = topics(user(params.owner), Identifier.parse(params.topic_id))
    if (!topic || topic.ticket?.id !== Identifier.parse(params.ticket_id)) throw new Refusal('NOT_FOUND')
    if (!z.object({ assetId: Identifier }).safeParse(topic.citation).success) {
      throw new Refusal('STALE_INTERACTION')
    }
    return receive(params, true)
  }
  if (method === 'workbench_topics') return topics(user(params.owner), Identifier.optional().parse(params.topic_id))
  if (method === 'management') return managementView(store, user(params.owner), params, source)
  if (method === 'requests') {
    const owner = user(params.owner)
    return store.list<RequestRecord>('request').filter(request => request.owner === owner)
      .reverse().slice(0, 50).map(requestProjection)
  }
  if (method === 'ticket') return projection(ownedTicket(Identifier.parse(params.ticket_id), user(params.owner)))
  if (method === 'cancel') {
    const ticket = ownedTicket(Identifier.parse(params.ticket_id), user(params.owner))
    if (!ticket.ended) engine.stopTicket(ticket.id)
    else if (ticket.ended.by === 'human' && store.get<Binding>('binding', ticket.id)) {
      const stop = ticketOperations(ticket.id).findLast(item => item.kind === 'stop')
      if (stop?.state === 'uncertain') settle(stop, 'queued')
    }
    return projection(ownedTicket(ticket.id, ticket.mandate.actor.id))
  }
  if (method === 'claim') return claim(z.enum(['route', 'worker', 'stop']).parse(params.kind))
  const operation = store.get<Operation>('operation', Identifier.parse(params.operation_id))
  if (!operation || operation.state !== 'claimed') throw new Refusal('STALE_OPERATION')
  if (method === 'uncertain') { settle(operation, 'uncertain'); return null }
  if (method === 'stopped' && operation.kind === 'stop') {
    settle(operation)
    for (const old of ticketOperations(operation.ticketId!)) {
      if (['start', 'deliver'].includes(old.kind) && old.state !== 'done') settle(old)
    }
    return null
  }
  if (method === 'route_result' && operation.kind === 'route') {
    const triggerId = operation.triggerId!
    const current = engine.candidate(triggerId)
    if (!current || current.evalId !== operation.evalId) { settle(operation); return null }
    const router = Decision.parse(params.decision)
    const request = store.get<RequestRecord>('request', triggerId)!
    user(request.owner)
    if (request.explicitFollow) throw new Refusal('CONFLICT')
    let ticketId: string | undefined
    if (router.action === 'attach') {
      const target = ownedTicket(router.ticket_id, request.owner)
      if (projection(target).uncertain) throw new Refusal('EXECUTION_UNCERTAIN')
      ticketId = engine.attach(target.id, triggerId, router.instruction).id
    } else if (router.action === 'accept') {
      ticketId = engine.decide(triggerId, { kind: 'accept', evalId: current.evalId,
        title: router.title, scope: router.title, reason: { code: 'explicitRouted' }, note: router.instruction }).ticketId
      if (!ticketId) throw new Refusal('ROUTE_REJECTED')
    } else {
      engine.decide(triggerId, { kind: 'ignore', evalId: current.evalId, reason: router.reason })
    }
    if (ticketId) store.put('request', triggerId, { ...request, ticketId })
    store.put('router_decision', triggerId, { action: router.action, reason: router.reason, router_session_id: Identifier.parse(params.router_session_id) })
    settle(operation)
    return null
  }
  const ticket = activeTicket(operation)
  if (method === 'dispatchable' && ['start', 'deliver'].includes(operation.kind)) {
    if (!ticket) settle(operation)
    return Boolean(ticket)
  }
  if (method === 'bound' && operation.kind === 'start') {
    const id = operation.ticketId!
    const existing = store.get<Binding>('binding', id)
    const sessionId = Identifier.parse(params.session_id)
    const projectDir = z.string().min(1).max(4096).parse(params.project_dir)
    if (existing && (existing.session_id !== sessionId || existing.project_dir !== projectDir)) {
      throw new Refusal('SESSION_CONFLICT')
    }
    const stored = store.tickets.get(id)!
    const previous = store.get<string>('session_ticket', sessionId)
    if (previous && previous !== id) throw new Refusal('SESSION_CONFLICT')
    store.put('session_ticket', sessionId, id)
    store.put('binding', id, { session_id: sessionId, project_dir: projectDir, owner: stored.mandate.actor.id })
    if (ticket) engine.assignmentStarted(ticket.id, operation.assignmentId!)
    return Boolean(ticket)
  }
  if (!ticket) { settle(operation); return null }
  const assignmentId = operation.assignmentId!
  if (method === 'delivered' && operation.kind === 'deliver') {
    engine.inputsDelivered(ticket.id, assignmentId, operation.inputIds ?? [])
    engine.inputsRead(ticket.id, operation.inputIds ?? [])
    return null
  }
  if (method === 'waiting') {
    engine.report(ticket.id, { state: 'progress', summary: 'Waiting for the platform interaction',
      question: z.string().min(1).max(1000).parse(params.question) })
    return null
  }
  if (method === 'report') {
    const report: WorkerReport = Report.parse(params.report)
    engine.turnEnded(ticket.id, assignmentId)
    // A newer input queued during this turn still belongs to this Ticket.
    const next = report.state === 'ready' && ticket.undelivered.length
      ? { state: 'waiting' as const, summary: report.summary }
      : report
    const updated = engine.report(ticket.id, next)
    const final = updated.assignments.find(assignment => assignment.id === assignmentId)?.report
    store.put('operation', operation.id, { ...operation, state: 'done',
      report: final && { state: report.state, summary: report.summary, at: final.at } })
    return null
  }
  if (method === 'started_with_inputs' && operation.kind === 'start') {
    engine.assignmentStarted(ticket.id, assignmentId)
    settle(operation)
    return null
  }
  throw new Refusal('UNKNOWN_METHOD')
}

const wire = z.object({ id: Identifier, method: Identifier, params: z.record(z.string(), z.unknown()) }).strict()
for await (const line of createInterface({ input: process.stdin, crlfDelay: Infinity })) {
  let id: string | undefined
  try {
    const message = wire.parse(JSON.parse(line))
    id = message.id
    const result = store.atomic(() => dispatch(message.method, message.params))
    process.stdout.write(JSON.stringify({ id, ok: true, result }) + '\n')
  } catch (error) {
    const code = error instanceof Refusal ? error.code : error instanceof z.ZodError ? 'BAD_REQUEST' : 'CORE_REFUSED'
    process.stdout.write(JSON.stringify({ id, ok: false, code }) + '\n')
  }
}
store.db.close()
