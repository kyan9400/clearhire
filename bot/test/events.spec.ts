import type { InlineKeyboard } from 'grammy';

import { BotConfig } from '../src/config';
import { handleEvent } from '../src/events';
import { clip, duration, esc, looksLikeEmail } from '../src/format';
import { MemoryStore } from '../src/store';
import { APP_ID } from './harness';

function setup() {
  const store = new MemoryStore();
  const sent: { chat: number; text: string; keyboard?: InlineKeyboard }[] = [];
  const deps = {
    store,
    recruiterChats: [-100],
    consoleUrl: 'https://console.test',
    send: async (chat: number, text: string, keyboard?: InlineKeyboard) => void sent.push({ chat, text, keyboard }),
  };
  return { store, sent, deps };
}

describe('notifications', () => {
  it('tells the candidate when their application moves, in their language', async () => {
    const { store, sent, deps } = setup();
    await store.track(42, 'ru', { applicationId: APP_ID, token: 't', title: 'Аналитик <данных>', appliedAt: '' });
    await handleEvent('application.stage_changed', { application: APP_ID, stage: 'interview' }, deps);
    await handleEvent('application.stage_changed', { application: APP_ID, stage: 'rejected' }, deps);
    expect(sent.map((s) => s.chat)).toEqual([42, 42]);
    expect(sent[0]!.text).toBe('Ваш отклик на <b>Аналитик &lt;данных&gt;</b>: <b>собеседование</b>.');
    expect(sent[1]!.text).toContain('решила не продолжать');
  });

  it('stays silent about applications from elsewhere, and about the first stage', async () => {
    const { store, sent, deps } = setup();
    await handleEvent('application.stage_changed', { application: 'someone-else', stage: 'offer' }, deps);
    await store.track(42, 'en', { applicationId: APP_ID, token: 't', title: 'Data Analyst', appliedAt: '' });
    await handleEvent('application.stage_changed', { application: APP_ID, stage: 'new' }, deps);
    expect(sent).toEqual([]);
  });

  it('tells the candidate and the recruiters when a CV has been read', async () => {
    const { store, sent, deps } = setup();
    await store.track(42, 'en', { applicationId: APP_ID, token: 't', title: 'Data Analyst', appliedAt: '' });
    const event = {
      application: APP_ID,
      vacancy: 'v-1',
      title: 'Data Analyst',
      source: 'telegram',
      must_met: 3,
      must_total: 4,
    };
    await handleEvent('application.scored', event, deps);
    expect(sent.map((s) => s.chat)).toEqual([42, -100]);
    expect(sent[0]!.text).toContain('3 of 4 must-haves found');
    expect(sent[1]!.text).toContain('(telegram) · 3/4 must-haves');
    expect(JSON.stringify(sent[1]!.keyboard)).toContain('https://console.test/vacancies/v-1');
  });

  it('asks for a readable file when a CV could not be read', async () => {
    const { store, sent, deps } = setup();
    await store.track(42, 'en', { applicationId: APP_ID, token: 't', title: 'Data Analyst', appliedAt: '' });
    await handleEvent('application.cv_failed', { application: APP_ID, title: 'Data Analyst' }, deps);
    expect(sent[0]!.text).toContain('could not read the CV');
  });
});

describe('formatting', () => {
  it('escapes HTML, clips long messages and counts in Russian', () => {
    expect(esc('<b>R&D</b>')).toBe('&lt;b&gt;R&amp;D&lt;/b&gt;');
    expect(clip('a\n'.repeat(3000)).length).toBeLessThanOrEqual(3902);
    expect(duration(13, 'ru')).toBe('1 год 1 месяц');
    expect(duration(26, 'ru')).toBe('2 года 2 месяца');
    expect(duration(60, 'ru')).toBe('5 лет');
    expect(duration(0, 'en')).toBe('none found');
  });

  it('accepts e-mail addresses and nothing else', () => {
    expect(looksLikeEmail('maria@example.com')).toBe(true);
    expect(looksLikeEmail('maria at example')).toBe(false);
    expect(looksLikeEmail('a@b')).toBe(false);
  });
});

describe('configuration', () => {
  const env = {
    TELEGRAM_BOT_TOKEN: '1:x', CLEARHIRE_API_URL: 'http://api:8000/', CLEARHIRE_BOT_SECRET: 's'.repeat(40),
    REDIS_URL: 'redis://redis', CAREERS_URL: 'https://c', CONSOLE_URL: 'https://k', RECRUITER_CHAT_IDS: ' -100, 42 ',
  }; // prettier-ignore

  it('reads the environment', () => {
    const config = BotConfig.fromEnv(env);
    expect(config.apiUrl).toBe('http://api:8000');
    expect(config.recruiterChats).toEqual([-100, 42]);
  });

  it('refuses a missing token, a short secret or a bad chat id', () => {
    expect(() => BotConfig.fromEnv({ ...env, TELEGRAM_BOT_TOKEN: '' })).toThrow('TELEGRAM_BOT_TOKEN');
    expect(() => BotConfig.fromEnv({ ...env, CLEARHIRE_BOT_SECRET: 'short' })).toThrow('32 characters');
    expect(() => BotConfig.fromEnv({ ...env, RECRUITER_CHAT_IDS: 'abc' })).toThrow('not a chat id');
  });
});
