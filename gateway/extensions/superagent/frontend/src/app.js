const api = '/api/superagent/v1/tickets';
const records = document.querySelector('#tickets');
const feedback = document.querySelector('#feedback');
const pending = new WeakMap();
let rendered = '';

function node(type, text) {
  const item = document.createElement(type);
  if (text !== undefined) item.textContent = text;
  return item;
}

async function call(path = '', data) {
  const response = await fetch(api + path, {
    method: data === undefined ? 'GET' : 'POST',
    credentials: 'same-origin',
    headers: data === undefined ? {} : { 'Content-Type': 'application/json' },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  const answer = await response.json();
  if (!response.ok) throw new Error(answer.detail || '请求失败');
  return answer;
}

async function act(button, operation) {
  button.disabled = true;
  try {
    await operation();
    feedback.textContent = '';
    await refresh(true);
  } catch (error) {
    feedback.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

function submit(form, text, path) {
  const existing = pending.get(form);
  const operationId = existing && existing.text === text ? existing.id : crypto.randomUUID();
  pending.set(form, { text, id: operationId });
  return call(path, { text, operation_id: operationId }).then(() => {
    pending.delete(form);
    form.reset();
  });
}

document.querySelector('#new-ticket').addEventListener('submit', event => {
  event.preventDefault();
  const form = event.currentTarget;
  act(event.submitter, () => submit(form, form.elements.request.value, ''));
});

function approval(parent, route, interaction) {
  const form = node('form');
  const questions = interaction.questions;
  for (const question of questions) {
    const label = node('label', question.question);
    const input = question.options?.length ? node('select') : node('input');
    input.required = true;
    if (input instanceof HTMLSelectElement) {
      input.multiple = question.multiSelect === true;
      if (!input.multiple) {
        const placeholder = node('option', '请选择');
        placeholder.value = '';
        placeholder.disabled = true;
        placeholder.selected = true;
        input.append(placeholder);
      }
    }
    for (const option of question.options || []) {
      const choice = node('option', option.label);
      choice.value = option.value ?? option.label;
      input.append(choice);
    }
    label.append(input);
    form.append(label);
  }
  const button = node('button', '提交审批答复');
  button.type = 'submit';
  form.append(button);
  form.addEventListener('submit', event => {
    event.preventDefault();
    const answers = questions.map((question, index) => ({
      question: question.question,
      selected_options: question.options?.length
        ? Array.from(form.elements[index].selectedOptions, option => option.value)
        : [],
      custom_input: question.options?.length ? '' : form.elements[index].value,
    }));
    act(button, () => call(`${route}/interactions/${encodeURIComponent(interaction.id)}/answer`, { answers }));
  });
  parent.append(form);
}

function drawTicket(item) {
  const card = node('article');
  const ticket = item.ticket;
  const states = { routing: '正在路由', ignore: '已忽略', uncertain: '待核对', not_allowed: '无法准入' };
  if (!ticket) {
    card.append(node('h2', states[item.status] || item.status));
    if (item.route?.reason) card.append(node('p', item.route.reason));
    return card;
  }
  card.append(node('h2', ticket.title));
  const stages = { person: '待人工处理', working: '执行中', idle: '等待跟进', ended: '已结束' };
  const outcomes = { completed: '已完成', stopped: '已停止', dropped: '已结束' };
  let status = ticket.uncertain ? '待核对' : outcomes[ticket.outcome] || stages[ticket.stage.stage];
  if (ticket.stop === 'done') status = '已确认停妥';
  if (ticket.stop === 'queued' || ticket.stop === 'claimed') status = '正在确认停妥';
  card.append(node('p', status));
  if (item.route?.reason) card.append(node('p', item.route.reason));
  const report = ticket.assignments.at(-1)?.report;
  if (report && !ticket.interaction) card.append(node('p', report.summary));
  if (ticket.session_id) card.append(node('p', `平台会话 ${ticket.session_id}`));
  const route = `/${encodeURIComponent(ticket.id)}`;
  if (ticket.interaction) approval(card, route, ticket.interaction);
  if (!ticket.uncertain && ticket.outcome !== 'stopped') {
    const follow = node('form');
    const label = node('label', '跟进工单');
    const text = node('textarea');
    text.rows = 2;
    text.required = true;
    text.maxLength = 12000;
    label.append(text);
    const button = node('button', '发送跟进');
    button.type = 'submit';
    follow.append(label, button);
    follow.addEventListener('submit', event => {
      event.preventDefault();
      act(button, () => submit(follow, text.value, `${route}/follow`));
    });
    card.append(follow);
  }
  if (!ticket.outcome || (ticket.stop === 'uncertain' && ticket.session_id)) {
    const stop = node('button', ticket.stop === 'uncertain' ? '重试停止' : '停止执行');
    stop.type = 'button';
    stop.addEventListener('click', () => act(stop, () => call(`${route}/stop`, {})));
    card.append(stop);
  }
  return card;
}

async function refresh(force = false) {
  try {
    const items = await call();
    const digest = JSON.stringify(items);
    if (digest === rendered || (!force && records.contains(document.activeElement) &&
        ['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement?.tagName))) return;
    rendered = digest;
    const seen = new Set();
    records.replaceChildren(...items.filter(item => {
      if (!item.ticket) return true;
      if (seen.has(item.ticket.id)) return false;
      seen.add(item.ticket.id);
      return true;
    }).map(drawTicket));
  } catch (error) {
    feedback.textContent = error.message;
  }
}

refresh();
setInterval(refresh, 1400);
