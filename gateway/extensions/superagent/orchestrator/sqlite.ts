import { DatabaseSync } from 'node:sqlite'
import { latestAssignment, type Decision, type OutboundMessage, type Repositories, type Thread,
  type Ticket, type Trigger, type TriggerDisposition } from './vendor/superagent/src/core/index.ts'

interface Operation {
  id: string
  kind: 'route' | 'start' | 'deliver' | 'stop'
  triggerId?: string
  evalId?: string
  ticketId?: string
  assignmentId?: string
  inputIds?: string[]
  state: 'queued' | 'claimed' | 'uncertain' | 'done'
}

export class Store implements Repositories {
  readonly db: DatabaseSync
  private depth = 0

  constructor(path: string) {
    this.db = new DatabaseSync(path)
    this.db.exec(`
      PRAGMA journal_mode=WAL;
      PRAGMA synchronous=FULL;
      CREATE TABLE IF NOT EXISTS record (
        ordinal INTEGER PRIMARY KEY,
        kind TEXT NOT NULL,
        key TEXT NOT NULL,
        value TEXT NOT NULL,
        UNIQUE(kind, key)
      );
    `)
  }

  atomic<T>(work: () => T): T {
    const name = `superagent_${++this.depth}`
    this.db.exec(`SAVEPOINT ${name}`)
    try {
      const result = work()
      this.db.exec(`RELEASE ${name}`)
      return result
    } catch (error) {
      this.db.exec(`ROLLBACK TO ${name}; RELEASE ${name}`)
      throw error
    } finally {
      this.depth--
    }
  }

  get<T>(kind: string, id: string): T | undefined {
    const row = this.db.prepare('SELECT value FROM record WHERE kind=? AND key=?').get(kind, id)
    return row ? JSON.parse(String(row.value)) as T : undefined
  }

  put(kind: string, id: string, value: unknown): void {
    this.db.prepare(`
      INSERT INTO record(kind, key, value) VALUES(?, ?, ?)
      ON CONFLICT(kind, key) DO UPDATE SET value=excluded.value
    `).run(kind, id, JSON.stringify(value))
  }

  list<T>(kind: string): T[] {
    return this.db.prepare('SELECT value FROM record WHERE kind=? ORDER BY ordinal').all(kind)
      .map(row => JSON.parse(String(row.value)) as T)
  }

  readonly triggers = {
    get: (id: string) => this.get<Trigger>('trigger', id),
    save: (trigger: Trigger) => this.put('trigger', trigger.id, trigger),
    disposition: (id: string) => this.get<TriggerDisposition>('disposition', id),
    saveDisposition: (id: string, value: TriggerDisposition) => this.put('disposition', id, value),
  }

  readonly threads = {
    get: (id: string) => this.get<Thread>('thread', id),
    save: (thread: Thread) => this.put('thread', thread.key, thread),
    list: () => this.list<Thread>('thread'),
    active: () => this.list<Thread>('thread').filter(thread => thread.pending.length > 0 || thread.evaluating),
  }

  readonly tickets = {
    get: (id: string) => this.get<Ticket>('ticket', id),
    save: (ticket: Ticket) => this.put('ticket', ticket.id, ticket),
    list: () => this.list<Ticket>('ticket').reverse(),
    open: () => this.list<Ticket>('ticket').reverse().filter(ticket => !ticket.ended),
    active: () => this.list<Ticket>('ticket').filter(ticket => ticket.undelivered.length > 0
      || ['pending', 'running'].includes(latestAssignment(ticket)?.state ?? '')),
  }

  readonly decisions = {
    get: (id: string) => this.get<Decision>('decision', id),
    save: (decision: Decision) => this.put('decision', decision.id, decision),
    byThread: (id: string) => this.list<Decision>('decision').filter(decision => decision.threadKey === id),
  }

  readonly outbox = {
    send: (message: OutboundMessage) => {
      if (!this.get('receipt', message.id)) this.put('receipt', message.id, { message, status: 'pending' })
    },
    status: (id: string) => this.get<{ status: 'pending' | 'sent' | 'dropped' }>('receipt', id)?.status,
    withdraw: (id: string) => {
      const receipt = this.get<{ message: OutboundMessage; status: string }>('receipt', id)
      if (receipt?.status === 'pending') this.put('receipt', id, { ...receipt, status: 'dropped' })
    },
  }

  queue(input: Omit<Operation, 'state'>): void {
    if (!this.get('operation', input.id)) this.put('operation', input.id, { ...input, state: 'queued' })
  }
}

export type { Operation }
