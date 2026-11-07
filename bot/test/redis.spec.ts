import { Redis } from 'ioredis';

import { EventConsumer, GROUP, STREAM } from '../src/events';
import { RedisStore } from '../src/store';
import { APP_ID } from './harness';

// Against a real Redis (CI starts one): REDIS_TEST_URL=redis://localhost:6379/15 npm test
const url = process.env.REDIS_TEST_URL;
const live = url ? describe : describe.skip;

live('with Redis', () => {
  let redis: Redis;

  beforeEach(async () => {
    redis = new Redis(url!, { maxRetriesPerRequest: null });
    await redis.flushdb();
  });
  afterEach(() => redis.disconnect());

  it('keeps sessions for an hour and tracks who owns which application', async () => {
    const store = new RedisStore(redis);
    await store.saveSession(42, { lang: 'ru', mode: 'apply', step: 'email' });
    expect(await store.session(42)).toEqual({ lang: 'ru', mode: 'apply', step: 'email' });
    expect(await redis.ttl('bot:session:42')).toBeGreaterThan(3500);
    await store.track(42, 'ru', { applicationId: APP_ID, token: 'tok', title: 'Аналитик', appliedAt: '2026-11-07' });
    expect((await store.owner(APP_ID))?.chat).toBe(42);
    await store.forget(42, APP_ID);
    expect(await store.owner(APP_ID)).toBeNull();
    expect(await store.applications(42)).toEqual([]);
  });

  it('handles each stream event once, and picks up unacknowledged ones after a restart', async () => {
    const store = new RedisStore(redis);
    await store.track(42, 'en', { applicationId: APP_ID, token: 'tok', title: 'Data Analyst', appliedAt: '' });
    const sent: string[] = [];
    const deps = {
      store,
      recruiterChats: [],
      consoleUrl: 'https://k',
      send: async (_: number, text: string) => void sent.push(text),
    };

    // an event that a previous run read but never acknowledged (it crashed)
    await redis.xgroup('CREATE', STREAM, GROUP, '$', 'MKSTREAM');
    await redis.xadd(
      STREAM,
      '*',
      'kind',
      'application.stage_changed',
      'data',
      JSON.stringify({ application: APP_ID, stage: 'interview' }),
    );
    await redis.xreadgroup('GROUP', GROUP, 'old-run', 'COUNT', 1, 'STREAMS', STREAM, '>');
    await redis.xclaim(STREAM, GROUP, 'bot-test', 0, (await redis.xrange(STREAM, '-', '+'))[0]![0]);

    const consumer = new EventConsumer(redis.duplicate(), deps, 'bot-test', () => undefined);
    await consumer.start();
    await redis.xadd(
      STREAM,
      '*',
      'kind',
      'application.stage_changed',
      'data',
      JSON.stringify({ application: APP_ID, stage: 'offer' }),
    );
    for (let i = 0; i < 50 && sent.length < 2; i++) await new Promise((r) => setTimeout(r, 100));
    consumer.stop();

    expect(sent).toEqual([
      'Your application for <b>Data Analyst</b> is now: <b>interview</b>.',
      'Your application for <b>Data Analyst</b> is now: <b>offer</b>.',
    ]);
    const pending = (await redis.xpending(STREAM, GROUP)) as [number, ...unknown[]];
    expect(pending[0]).toBe(0);
  });
});
