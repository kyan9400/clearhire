import type { Redis } from 'ioredis';

import type { Lang } from './texts';

/** Where a chat is in a conversation. Kept for an hour, then forgotten. */
export interface Session {
  lang: Lang;
  mode?: 'check' | 'apply';
  vacancyId?: string;
  title?: string;
  step?: 'name' | 'email' | 'consent' | 'cv';
  fullName?: string;
  email?: string;
  /** The last CV the user sent, as a Telegram file id (the file stays on Telegram's servers). */
  cv?: { fileId: string; name: string };
}

export interface Tracked {
  applicationId: string;
  token: string; // the private status token; it never leaves Redis and this chat
  title: string;
  appliedAt: string;
}

/** The little the bot keeps: conversation state, and which chat owns which application. */
export interface Store {
  session(chat: number): Promise<Session | null>;
  saveSession(chat: number, session: Session): Promise<void>;
  clearSession(chat: number): Promise<void>;
  track(chat: number, lang: Lang, app: Tracked): Promise<void>;
  applications(chat: number): Promise<Tracked[]>;
  /** The chat that owns an application, and its language, for notifications. */
  owner(applicationId: string): Promise<{ chat: number; lang: Lang; app: Tracked } | null>;
  forget(chat: number, applicationId: string): Promise<void>;
}

const SESSION_SECONDS = 3600;

export class RedisStore implements Store {
  constructor(private readonly redis: Redis) {}

  async session(chat: number): Promise<Session | null> {
    const raw = await this.redis.get(`bot:session:${chat}`);
    return raw ? (JSON.parse(raw) as Session) : null;
  }

  async saveSession(chat: number, session: Session): Promise<void> {
    await this.redis.set(`bot:session:${chat}`, JSON.stringify(session), 'EX', SESSION_SECONDS);
  }

  async clearSession(chat: number): Promise<void> {
    await this.redis.del(`bot:session:${chat}`);
  }

  async track(chat: number, lang: Lang, app: Tracked): Promise<void> {
    await this.redis
      .multi()
      .hset(`bot:apps:${chat}`, app.applicationId, JSON.stringify(app))
      .set(`bot:owner:${app.applicationId}`, JSON.stringify({ chat, lang }))
      .exec();
  }

  async applications(chat: number): Promise<Tracked[]> {
    const all = await this.redis.hgetall(`bot:apps:${chat}`);
    return Object.values(all)
      .map((raw) => JSON.parse(raw) as Tracked)
      .sort((a, b) => b.appliedAt.localeCompare(a.appliedAt));
  }

  async owner(applicationId: string): Promise<{ chat: number; lang: Lang; app: Tracked } | null> {
    const raw = await this.redis.get(`bot:owner:${applicationId}`);
    if (!raw) return null;
    const { chat, lang } = JSON.parse(raw) as { chat: number; lang: Lang };
    const app = await this.redis.hget(`bot:apps:${chat}`, applicationId);
    return app ? { chat, lang, app: JSON.parse(app) as Tracked } : null;
  }

  async forget(chat: number, applicationId: string): Promise<void> {
    await this.redis.multi().hdel(`bot:apps:${chat}`, applicationId).del(`bot:owner:${applicationId}`).exec();
  }
}

/** For tests. */
export class MemoryStore implements Store {
  readonly sessions = new Map<number, Session>();
  readonly apps = new Map<number, Map<string, Tracked>>();
  readonly owners = new Map<string, { chat: number; lang: Lang }>();

  async session(chat: number) {
    return this.sessions.get(chat) ?? null;
  }
  async saveSession(chat: number, session: Session) {
    this.sessions.set(chat, structuredClone(session));
  }
  async clearSession(chat: number) {
    this.sessions.delete(chat);
  }
  async track(chat: number, lang: Lang, app: Tracked) {
    if (!this.apps.has(chat)) this.apps.set(chat, new Map());
    this.apps.get(chat)!.set(app.applicationId, app);
    this.owners.set(app.applicationId, { chat, lang });
  }
  async applications(chat: number) {
    return [...(this.apps.get(chat)?.values() ?? [])].sort((a, b) => b.appliedAt.localeCompare(a.appliedAt));
  }
  async owner(applicationId: string) {
    const owner = this.owners.get(applicationId);
    const app = owner && this.apps.get(owner.chat)?.get(applicationId);
    return owner && app ? { ...owner, app } : null;
  }
  async forget(chat: number, applicationId: string) {
    this.apps.get(chat)?.delete(applicationId);
    this.owners.delete(applicationId);
  }
}
