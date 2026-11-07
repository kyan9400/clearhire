import { InlineKeyboard } from 'grammy';
import type { Redis } from 'ioredis';

import { esc } from './format';
import type { Store } from './store';
import { T, recruiterAlert } from './texts';

export const STREAM = 'clearhire:events';
export const GROUP = 'telegram-bot';

/** Internal stages as the candidate sees them (the same mapping as the careers site). */
const PUBLIC_STAGE: Record<string, string> = {
  new: 'received',
  screening: 'in review',
  interview: 'interview',
  offer: 'offer',
  hired: 'hired',
  rejected: 'closed',
};

export interface Send {
  (chat: number, text: string, keyboard?: InlineKeyboard): Promise<unknown>;
}

export interface EventDeps {
  store: Store;
  send: Send;
  recruiterChats: number[];
  consoleUrl: string;
}

/** One event from the API or the worker: tell the candidate (if they applied here) and the recruiters. */
export async function handleEvent(kind: string, data: Record<string, unknown>, deps: EventDeps): Promise<void> {
  const applicationId = String(data.application ?? '');
  const owner = applicationId ? await deps.store.owner(applicationId) : null;
  const t = owner ? T[owner.lang] : null;
  const title = esc(owner?.app.title ?? String(data.title ?? ''));

  if (kind === 'application.stage_changed' && owner && t) {
    const stage = PUBLIC_STAGE[String(data.stage)] ?? String(data.stage);
    if (stage === 'received') return;
    await deps.send(owner.chat, stage === 'closed' ? t.closed(title) : t.moved(title, t.stage[stage] ?? stage));
  }
  if (kind === 'application.scored') {
    const met = typeof data.must_met === 'number' ? data.must_met : null;
    const total = typeof data.must_total === 'number' ? data.must_total : null;
    if (owner && t && met !== null && total !== null) await deps.send(owner.chat, t.scored(title, met, total));
    const link = new InlineKeyboard().url(
      'Open in the console',
      `${deps.consoleUrl}/vacancies/${String(data.vacancy ?? '')}`,
    );
    for (const chat of deps.recruiterChats) {
      await deps.send(chat, recruiterAlert(esc(String(data.title ?? '')), String(data.source ?? ''), met, total), link);
    }
  }
  if (kind === 'application.cv_failed' && owner && t) {
    await deps.send(owner.chat, t.cvFailed(title));
  }
}

/**
 * Reads the API's event stream as a consumer group, so every event is handled once even across restarts.
 * An event is acknowledged after it was handled, or after its failure was logged, so one bad event cannot
 * block the rest; events read before a crash and never acknowledged are read again at start.
 */
export class EventConsumer {
  private running = false;

  constructor(
    private readonly redis: Redis,
    private readonly deps: EventDeps,
    private readonly consumer = 'bot-1',
    private readonly log: (message: string, error?: unknown) => void = console.error,
  ) {}

  async start(): Promise<void> {
    try {
      await this.redis.xgroup('CREATE', STREAM, GROUP, '$', 'MKSTREAM');
    } catch (error) {
      if (!String(error).includes('BUSYGROUP')) throw error; // the group exists: continue where it was
    }
    this.running = true;
    void this.loop();
  }

  stop(): void {
    this.running = false;
  }

  private async loop(): Promise<void> {
    let pending = true; // first, events read before a restart and never acknowledged
    while (this.running) {
      try {
        const reply = (await this.redis.xreadgroup(
          'GROUP', GROUP, this.consumer, 'COUNT', 20, 'BLOCK', 5000, 'STREAMS', STREAM, pending ? '0' : '>',
        )) as [string, [string, string[]][]][] | null; // prettier-ignore
        const entries = reply?.[0]?.[1] ?? [];
        if (pending && !entries.length) pending = false;
        for (const [id, fields] of entries) {
          await this.handle(id, fields);
        }
      } catch (error) {
        if (!this.running) return;
        this.log('event stream read failed, retrying', error);
        await new Promise((resolve) => setTimeout(resolve, 3000));
      }
    }
  }

  private async handle(id: string, fields: string[]): Promise<void> {
    const record: Record<string, string> = {};
    for (let i = 0; i + 1 < fields.length; i += 2) record[fields[i]!] = fields[i + 1]!;
    try {
      await handleEvent(record.kind ?? '', JSON.parse(record.data ?? '{}') as Record<string, unknown>, this.deps);
    } catch (error) {
      this.log(`event ${id} (${record.kind}) failed; it is acknowledged so it cannot block the stream`, error);
    }
    await this.redis.xack(STREAM, GROUP, id);
  }
}
