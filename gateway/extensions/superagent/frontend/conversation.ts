import type { ManagedConversation } from '../../../../jiuwenswarm/channels/web/frontend/src/applicationPlugins/managedConversation';
import type { AskUserQuestionPayload, UserAnswer } from '../../../../jiuwenswarm/channels/web/frontend/src/types';

interface TicketSnapshot {
  id: string;
  session_id: string;
  interaction: { id: string; source: string; questions: AskUserQuestionPayload['questions'] } | null;
}

export const applicationPluginId = 'superagent';

const base = '/api/superagent/v1';
const known = new Set<string>();

async function call<T>(path: string, method = 'GET', body?: object, signal?: AbortSignal): Promise<T | null> {
  const response = await fetch(base + path, {
    credentials: 'same-origin',
    cache: 'no-store',
    method,
    signal,
    ...(body && { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  });
  const payload = response.headers.get('content-type')?.includes('application/json') ? await response.json() : null;
  if (method === 'GET' && (response.status === 404 || payload?.detail === 'PROJECT_NOT_ALLOWED' ||
    (response.ok && payload === null))) {
    return null;
  }
  if (!response.ok || payload === null) throw new Error(payload?.detail || 'APPLICATION_CONVERSATION_FAILED');
  return payload as T;
}

export async function applicationPluginConversation(sessionId: string): Promise<ManagedConversation | null> {
  const path = '/sessions/' + encodeURIComponent(sessionId);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 2500);
  const expected = known.has(sessionId) || (typeof window !== 'undefined'
    && window.location.pathname === '/chat/' + encodeURIComponent(sessionId)
    && new URLSearchParams(window.location.search).get('application') === applicationPluginId);
  let ticket: TicketSnapshot | null;
  try {
    ticket = await call<TicketSnapshot>(path, 'GET', undefined, controller.signal);
  } catch (error) {
    if (expected) throw error;
    return null;
  } finally {
    clearTimeout(timeout);
  }
  if (!ticket || ticket.session_id !== sessionId || !ticket.id) {
    if (expected) throw new Error('MANAGED_CONVERSATION_UNAVAILABLE');
    return null;
  }
  known.add(sessionId);
  const ticketPath = '/tickets/' + encodeURIComponent(ticket.id);
  return {
    async follow(text, operationId) {
      await call(ticketPath + '/follow', 'POST', { text, operation_id: operationId });
    },
    async pending(signal) {
      const snapshot = await call<TicketSnapshot>(path, 'GET', undefined, signal);
      if (!snapshot || snapshot.id !== ticket.id || snapshot.session_id !== sessionId) {
        throw new Error('MANAGED_CONVERSATION_UNAVAILABLE');
      }
      const pending = snapshot.interaction;
      return pending ? {
        request_id: pending.id, source: pending.source, questions: pending.questions,
        applicationManaged: true,
      } : null;
    },
    async answer(requestId, answers: UserAnswer[]) {
      await call(ticketPath + '/interactions/' + encodeURIComponent(requestId) + '/answer', 'POST', {
        answers: answers.map(({ question, selected_options, custom_input, card_id }) => ({
          question, selected_options, custom_input: custom_input ?? '', card_id,
        })),
      });
    },
  };
}
