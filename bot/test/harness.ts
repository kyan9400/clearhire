import { Bot } from 'grammy';
import type { Update } from 'grammy/types';

import { ClearhireApi } from '../src/api';
import { register } from '../src/handlers';
import { MemoryStore } from '../src/store';

export const VACANCY_ID = '3f1e0c55-8a3b-4f7e-9a7b-0f6c2d9e1a42';
export const APP_ID = '7c9e6679-7425-40de-944b-e07fc1f90ae7';
export const SECRET = 's'.repeat(40);

export const vacancy = (id = VACANCY_ID, title = 'Data Analyst') => ({
  id,
  title,
  company: 'Quartz Media',
  location: 'Moscow',
  remote: true,
  language: 'en',
  description: 'Analyse product metrics',
  created_at: '2026-10-01T00:00:00Z',
  requirements: [
    { id: 'r1', text: '3+ years of SQL', kind: 'skill', must: true },
    { id: 'r2', text: 'Hands-on Tableau', kind: 'skill', must: false },
  ],
});

export const precheck = {
  must_met: 1,
  must_total: 1,
  qualified: true,
  experience_months: 90,
  skills: ['SQL', 'Tableau'],
  items: [
    {
      requirement_id: 'r1', text: '3+ years of SQL', must: true, status: 'met', detail: 'SQL: 7 years',
      evidence: [{ quote: 'wrote SQL in ClickHouse', highlight: [6, 9], page: 1, section: 'experience', source: 'skill' }],
    },
    { requirement_id: 'r2', text: 'Hands-on Tableau', must: false, status: 'missing', detail: 'Tableau: not found', evidence: [] },
  ],
}; // prettier-ignore

export interface Call {
  method: string;
  payload: Record<string, unknown>;
}

export interface ApiRequest {
  method: string;
  path: string;
  headers: Record<string, string>;
  form?: Record<string, string>;
}

/** A bot wired to fakes: outgoing Telegram calls are recorded, the careers API is scripted. */
export function harness(routes: Record<string, (req: ApiRequest) => unknown> = {}) {
  const calls: Call[] = [];
  const requests: ApiRequest[] = [];
  const store = new MemoryStore();
  const bot = new Bot('123:test', {
    botInfo: {
      id: 1, is_bot: true, first_name: 'Clearhire', username: 'clearhire_bot', can_join_groups: false,
      can_read_all_group_messages: false, supports_inline_queries: false, can_connect_to_business: false,
      has_main_web_app: false, has_topics_enabled: false, allows_users_to_create_topics: false,
    } as never,
  }); // prettier-ignore
  bot.api.config.use(async (_prev, method, payload) => {
    calls.push({ method, payload: payload as Record<string, unknown> });
    const result = method === 'sendMessage' || method === 'editMessageText' ? { message_id: calls.length, date: 0, chat: { id: 0, type: 'private' } } : true;
    return { ok: true, result } as never;
  }); // prettier-ignore

  const fetchImpl = (async (url: string, init: RequestInit) => {
    const path = new URL(url).pathname;
    const form: Record<string, string> = {};
    if (init.body instanceof FormData) {
      for (const [key, value] of init.body.entries())
        form[key] = typeof value === 'string' ? value : `<file ${(value as File).name}>`;
    }
    const req: ApiRequest = {
      method: init.method ?? 'GET',
      path,
      headers: init.headers as Record<string, string>,
      form,
    };
    requests.push(req);
    const route = routes[`${req.method} ${path}`];
    if (!route) return new Response(JSON.stringify({ detail: 'not found' }), { status: 404 });
    const body = route(req);
    if (body instanceof Response) return body;
    return body === undefined ? new Response(null, { status: 204 }) : Response.json(body);
  }) as typeof fetch;

  register(bot, {
    api: new ClearhireApi('http://api', SECRET, fetchImpl),
    store,
    careersUrl: 'https://careers.test',
    download: async () => new TextEncoder().encode('Maria Petrova\nSQL, Python'),
    log: () => undefined,
  });

  let updateId = 0;
  const from = (lang = 'en') => ({
    id: 42,
    is_bot: false,
    first_name: 'Maria',
    last_name: 'Petrova',
    username: 'maria_p',
    language_code: lang,
  });
  const chat = { id: 42, type: 'private' as const, first_name: 'Maria' };
  const message = (extra: Record<string, unknown>, lang?: string) =>
    bot.handleUpdate({
      update_id: ++updateId,
      message: { message_id: updateId, date: 0, chat, from: from(lang), ...extra },
    } as Update);

  return {
    bot, calls, requests, store,
    text: (text: string, lang?: string) =>
      message({ text, ...(text.startsWith('/') ? { entities: [{ type: 'bot_command', offset: 0, length: text.split(' ')[0]!.length }] } : {}) }, lang),
    document: (name = 'cv.pdf', size = 2048) => message({ document: { file_id: 'file-1', file_unique_id: 'u1', file_name: name, file_size: size } }),
    tap: (data: string, lang?: string) =>
      bot.handleUpdate({ update_id: ++updateId, callback_query: { id: String(updateId), from: from(lang), chat_instance: 'c', data,
        message: { message_id: 1, date: 0, chat, text: 'x' } } } as Update),
    sent: () => calls.filter((c) => c.method === 'sendMessage' || c.method === 'editMessageText'),
    last: () => {
      const all = calls.filter((c) => c.method === 'sendMessage' || c.method === 'editMessageText');
      return all[all.length - 1]!.payload as { text: string; reply_markup?: { inline_keyboard: { text: string; callback_data?: string; url?: string }[][] } };
    },
  }; // prettier-ignore
}

export function buttons(payload: {
  reply_markup?: { inline_keyboard: { text: string; callback_data?: string; url?: string }[][] };
}) {
  return (payload.reply_markup?.inline_keyboard ?? []).flat();
}
