import type { WsEvent } from '../types/websocket';

/** Transport cursors only; accepted inputs are never retried on reconnect. */
export class RuntimeResume {
  private sessions = new Map<string, { instance: string; after: number; seen: Set<number>; historical: Set<string>;
    pending?: { through: number; ids: Set<string> } }>();

  observe(event: WsEvent): boolean {
    const sessionId = event.payload.session_id;
    const marker = event.payload.runtime_event as Record<string, unknown> | undefined;
    if (
      typeof sessionId !== 'string' ||
      !marker ||
      typeof marker.worker_instance !== 'string' ||
      typeof marker.sequence !== 'number'
    )
      return true;
    let cursor = this.sessions.get(sessionId);
    if (!cursor || cursor.instance !== marker.worker_instance) {
      cursor = { instance: marker.worker_instance, after: 0, seen: new Set(), historical: new Set() };
      this.sessions.set(sessionId, cursor);
    }
    if (cursor.seen.has(marker.sequence)) return false;
    cursor.seen.add(marker.sequence);
    cursor.after = Math.max(cursor.after, marker.sequence);
    if (cursor.seen.size > 4096) cursor.seen.delete(cursor.seen.values().next().value!);
    this.sessions.delete(sessionId);
    this.sessions.set(sessionId, cursor);
    while (this.sessions.size > 256) this.sessions.delete(this.sessions.keys().next().value!);
    if (marker.replayed === true) {
      if (typeof marker.dispatch_id === 'string' && cursor.historical.has(marker.dispatch_id)) return false;
      // Journal frames can outlive their dispatch records. Only the snapshot's
      // still-pending controls can become actionable again during replay.
      if (event.event === 'chat.ask_user_question' && cursor.pending && marker.sequence <= cursor.pending.through
        && !cursor.pending.ids.has(String(event.payload.request_id ?? ''))) return false;
    }
    return true;
  }

  queryFromSnapshot(sessionId: string, runtime: Record<string, unknown>) {
    const instance = typeof runtime.worker_instance === 'string' ? runtime.worker_instance : '';
    let cursor = this.sessions.get(sessionId);
    if (!cursor || cursor.instance !== instance) {
      // Finished turns are rendered by session history, not appended to the
      // active reply when a fresh page subscribes to the resident Worker.
      cursor = { instance, after: 0, seen: new Set(), historical: new Set() };
      this.sessions.set(sessionId, cursor);
      while (this.sessions.size > 256) this.sessions.delete(this.sessions.keys().next().value!);
    }
    // Live events can create the cursor before the first metadata response.
    // Reconcile every authoritative snapshot, retaining the observed cursor.
    const dispatches = Array.isArray(runtime.dispatches) ? runtime.dispatches : [];
    for (const dispatch of dispatches) {
      if (dispatch?.active === false && dispatch.terminal && typeof dispatch.dispatch_id === 'string') {
        cursor.historical.add(dispatch.dispatch_id);
      }
    }
    if (Array.isArray(runtime.dispatches) && typeof runtime.cursor === 'number') {
      const ids = new Set<string>();
      for (const dispatch of dispatches) {
        for (const interaction of Array.isArray(dispatch?.pending_interactions) ? dispatch.pending_interactions : []) {
          const id = interaction?.interaction_id ?? interaction?.control_id ?? interaction?.request_id;
          if (typeof id === 'string') ids.add(id);
        }
      }
      cursor.pending = { through: runtime.cursor, ids };
    }
    return { session_id: sessionId, runtime_resume: { worker_instance: instance, after: cursor.after } };
  }

  queries(): Array<{ session_id: string; runtime_resume: { worker_instance: string; after: number } }> {
    return Array.from(this.sessions, ([session_id, cursor]) => ({
      session_id,
      runtime_resume: { worker_instance: cursor.instance, after: cursor.after },
    }));
  }

  clear(): void {
    this.sessions.clear();
  }
}
