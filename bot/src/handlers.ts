import { Bot, Context, InlineKeyboard } from 'grammy';

import { ApiError, ClearhireApi, CvFile } from './api';
import { checkReport, esc, looksLikeEmail, vacancyCard } from './format';
import { Session, Store } from './store';
import { Lang, T, Texts, langOf } from './texts';

export const MAX_FILE_BYTES = 10 * 1024 * 1024;
const PAGE = 8;

/** Fetches a file the user sent: in production from Telegram's file servers. */
export type Download = (fileId: string) => Promise<Uint8Array>;

export interface Deps {
  api: ClearhireApi;
  store: Store;
  download: Download;
  careersUrl: string;
  log?: (message: string, error?: unknown) => void;
}

interface Turn {
  ctx: Context;
  chat: number;
  user: number;
  lang: Lang;
  t: Texts;
  session: Session;
}

async function turn(ctx: Context, deps: Deps): Promise<Turn | null> {
  const chat = ctx.chat?.id;
  const user = ctx.from?.id;
  if (chat === undefined || user === undefined || ctx.chat?.type !== 'private') return null; // candidates use private chats
  const stored = await deps.store.session(chat);
  const lang = stored?.lang ?? langOf(ctx.from?.language_code);
  return { ctx, chat, user, lang, t: T[lang], session: stored ?? { lang } };
}

const html = { parse_mode: 'HTML' as const, link_preview_options: { is_disabled: true } };

export function register(bot: Bot, deps: Deps): void {
  const { api, store } = deps;
  const log = deps.log ?? ((message: string, error?: unknown) => console.error(message, error));
  errorBoundary(bot, log);

  async function showJobs(x: Turn, page: number, edit: boolean): Promise<void> {
    const all = await api.vacancies();
    if (!all.length) {
      await x.ctx.reply(x.t.noJobs);
      return;
    }
    const keyboard = new InlineKeyboard();
    for (const v of all.slice(page * PAGE, (page + 1) * PAGE)) {
      keyboard.text(v.company ? `${v.title} · ${v.company}` : v.title, `job:${v.id}`).row();
    }
    if (page > 0) keyboard.text(x.t.back, `jobs:${page - 1}`);
    if ((page + 1) * PAGE < all.length) keyboard.text(x.t.more, `jobs:${page + 1}`);
    const text = x.t.jobsTitle(all.length);
    if (edit) await x.ctx.editMessageText(text, { ...html, reply_markup: keyboard });
    else await x.ctx.reply(text, { ...html, reply_markup: keyboard });
  }

  async function showJob(x: Turn, id: string, edit: boolean): Promise<void> {
    const v = await api.vacancy(id);
    if (!v) {
      await x.ctx.reply(x.t.jobNotFound);
      return;
    }
    const keyboard = new InlineKeyboard()
      .text(x.t.checkCv, `check:${v.id}`)
      .text(x.t.apply, `apply:${v.id}`)
      .row()
      .url(x.t.openSite, `${deps.careersUrl}/jobs/${v.id}`)
      .row()
      .text(x.t.back, 'jobs:0');
    const text = vacancyCard(v, x.t);
    if (edit) await x.ctx.editMessageText(text, { ...html, reply_markup: keyboard });
    else await x.ctx.reply(text, { ...html, reply_markup: keyboard });
  }

  async function startApply(x: Turn, id: string): Promise<void> {
    const v = await api.vacancy(id);
    if (!v) {
      await x.ctx.reply(x.t.jobNotFound);
      return;
    }
    const session: Session = {
      lang: x.lang,
      mode: 'apply',
      vacancyId: v.id,
      title: v.title,
      step: 'name',
      cv: x.session.cv,
    };
    await store.saveSession(x.chat, session);
    const name = [x.ctx.from?.first_name, x.ctx.from?.last_name].filter(Boolean).join(' ').trim();
    const keyboard = new InlineKeyboard();
    if (name.length >= 2) keyboard.text(x.t.useName(name), 'name:use').row();
    keyboard.text(x.t.cancel, 'cancel');
    await x.ctx.reply(x.t.askName(esc(v.title)), { ...html, reply_markup: keyboard });
  }

  async function setName(x: Turn, name: string): Promise<void> {
    if (name.length < 2 || name.length > 200) {
      await x.ctx.reply(x.t.badName);
      return;
    }
    await store.saveSession(x.chat, { ...x.session, fullName: name, step: 'email' });
    await x.ctx.reply(x.t.askEmail, { reply_markup: new InlineKeyboard().text(x.t.cancel, 'cancel') });
  }

  async function askCv(x: Turn, session: Session): Promise<void> {
    const keyboard = new InlineKeyboard();
    if (session.cv) keyboard.text(x.t.useChecked(session.cv.name), 'cv:use').row();
    keyboard.text(x.t.cancel, 'cancel');
    await x.ctx.reply(x.t.askCv, { reply_markup: keyboard });
  }

  async function submit(x: Turn, session: Session): Promise<void> {
    if (!session.vacancyId || !session.fullName || !session.email || !session.cv) return askCv(x, session);
    await x.ctx.reply(x.t.sending);
    const file: CvFile = { name: session.cv.name, data: await deps.download(session.cv.fileId) };
    const telegram = x.ctx.from?.username;
    const applied = await api.apply(
      session.vacancyId,
      file,
      { fullName: session.fullName, email: session.email, telegram },
      x.user,
    );
    await store.track(x.chat, x.lang, {
      applicationId: applied.application_id,
      token: applied.status_token,
      title: session.title ?? '',
      appliedAt: new Date().toISOString(),
    });
    await store.saveSession(x.chat, { lang: x.lang });
    await x.ctx.reply(x.t.applied(esc(session.title ?? '')), html);
  }

  async function check(x: Turn, cv: CvFile): Promise<void> {
    await x.ctx.reply(x.t.reading);
    const result = await api.precheck(x.session.vacancyId!, cv, x.user);
    const keyboard = new InlineKeyboard().text(x.t.applyWithThis, `apply:${x.session.vacancyId}`);
    await x.ctx.reply(checkReport(result, x.t, x.lang), { ...html, reply_markup: keyboard });
  }

  async function showStatus(x: Turn): Promise<void> {
    const tracked = await store.applications(x.chat);
    const lines: string[] = [];
    const keyboard = new InlineKeyboard();
    for (const app of tracked) {
      const status = await api.status(app.token);
      if (!status) {
        await store.forget(x.chat, app.applicationId); // erased, or the demo was reset
        continue;
      }
      const must = status.items.filter((i) => i.must);
      const met = must.filter((i) => i.status === 'met').length;
      const cv = status.cv_read ? x.t.cvRead(met, must.length) : x.t.cvPending;
      lines.push(`• <b>${esc(status.vacancy)}</b>: ${x.t.stage[status.stage] ?? status.stage}\n   ${cv}`);
      keyboard.text(x.t.erase(status.vacancy).slice(0, 60), `erase:${app.applicationId}`).row();
    }
    if (!lines.length) {
      await x.ctx.reply(x.t.noApplications);
      return;
    }
    await x.ctx.reply(`${x.t.applicationsTitle}\n\n${lines.join('\n\n')}`, { ...html, reply_markup: keyboard });
  }

  // ---- commands

  bot.command('start', async (ctx) => {
    const x = await turn(ctx, deps);
    if (!x) return;
    const payload = typeof ctx.match === 'string' ? ctx.match.trim() : '';
    if (payload.startsWith('job_')) return showJob(x, payload.slice(4), false);
    await ctx.reply(x.t.welcome, html);
  });
  bot.command('help', async (ctx) => {
    const x = await turn(ctx, deps);
    if (x) await ctx.reply(x.t.help, html);
  });
  bot.command('jobs', async (ctx) => {
    const x = await turn(ctx, deps);
    if (x) await showJobs(x, 0, false);
  });
  bot.command('status', async (ctx) => {
    const x = await turn(ctx, deps);
    if (x) await showStatus(x);
  });
  bot.command('cancel', async (ctx) => {
    const x = await turn(ctx, deps);
    if (!x) return;
    await store.saveSession(x.chat, { lang: x.lang });
    await ctx.reply(x.session.mode ? x.t.cancelled : x.t.nothingToCancel);
  });
  // works in groups too, so a recruiters' team chat can find its id
  bot.command('whoami', async (ctx) => {
    if (ctx.chat) await ctx.reply(T[langOf(ctx.from?.language_code)].whoami(ctx.chat.id), html);
  });

  // ---- buttons

  bot.callbackQuery(/^jobs:(\d+)$/, async (ctx) => {
    await ctx.answerCallbackQuery();
    const x = await turn(ctx, deps);
    if (x) await showJobs(x, Number(ctx.match[1]), true);
  });
  bot.callbackQuery(/^job:([0-9a-f-]{36})$/, async (ctx) => {
    await ctx.answerCallbackQuery();
    const x = await turn(ctx, deps);
    if (x) await showJob(x, ctx.match[1]!, true);
  });
  bot.callbackQuery(/^check:([0-9a-f-]{36})$/, async (ctx) => {
    await ctx.answerCallbackQuery();
    const x = await turn(ctx, deps);
    if (!x) return;
    const v = await api.vacancy(ctx.match[1]!);
    if (!v) return void (await ctx.reply(x.t.jobNotFound));
    await store.saveSession(x.chat, { lang: x.lang, mode: 'check', vacancyId: v.id, title: v.title, cv: x.session.cv });
    await ctx.reply(x.t.sendCv(esc(v.title)), html);
  });
  bot.callbackQuery(/^apply:([0-9a-f-]{36})$/, async (ctx) => {
    await ctx.answerCallbackQuery();
    const x = await turn(ctx, deps);
    if (x) await startApply(x, ctx.match[1]!);
  });
  bot.callbackQuery('name:use', async (ctx) => {
    await ctx.answerCallbackQuery();
    const x = await turn(ctx, deps);
    if (!x || x.session.step !== 'name') return;
    await setName(x, [ctx.from.first_name, ctx.from.last_name].filter(Boolean).join(' ').trim());
  });
  bot.callbackQuery('consent:yes', async (ctx) => {
    await ctx.answerCallbackQuery();
    const x = await turn(ctx, deps);
    if (!x || x.session.step !== 'consent') return;
    const session: Session = { ...x.session, step: 'cv' };
    await store.saveSession(x.chat, session);
    await askCv(x, session);
  });
  bot.callbackQuery('cv:use', async (ctx) => {
    await ctx.answerCallbackQuery();
    const x = await turn(ctx, deps);
    if (x && x.session.step === 'cv') await submit(x, x.session);
  });
  bot.callbackQuery('cancel', async (ctx) => {
    await ctx.answerCallbackQuery();
    const x = await turn(ctx, deps);
    if (!x) return;
    await store.saveSession(x.chat, { lang: x.lang });
    await ctx.reply(x.t.cancelled);
  });
  bot.callbackQuery(/^erase:([0-9a-f-]{36})$/, async (ctx) => {
    await ctx.answerCallbackQuery();
    const x = await turn(ctx, deps);
    if (!x) return;
    const keyboard = new InlineKeyboard().text(x.t.eraseYes, `erase!:${ctx.match[1]}`).row().text(x.t.cancel, 'cancel');
    await ctx.reply(x.t.eraseConfirm, { reply_markup: keyboard });
  });
  bot.callbackQuery(/^erase!:([0-9a-f-]{36})$/, async (ctx) => {
    await ctx.answerCallbackQuery();
    const x = await turn(ctx, deps);
    if (!x) return;
    const app = (await store.applications(x.chat)).find((a) => a.applicationId === ctx.match[1]);
    if (!app) return void (await ctx.reply(x.t.gone));
    await api.withdraw(app.token, x.user);
    await store.forget(x.chat, app.applicationId);
    await ctx.editMessageText(x.t.erased);
  });

  // ---- files and text

  bot.on(['message:document', 'message:photo'], async (ctx) => {
    const x = await turn(ctx, deps);
    if (!x) return;
    const document = ctx.message.document;
    const photo = ctx.message.photo?.at(-1); // the largest size
    const fileId = document?.file_id ?? photo?.file_id;
    const size = document?.file_size ?? photo?.file_size ?? 0;
    if (!fileId) return;
    if (size > MAX_FILE_BYTES) return void (await ctx.reply(x.t.tooBig));
    if (!x.session.mode || !x.session.vacancyId) return void (await ctx.reply(x.t.unexpectedFile, html));
    const cv = { fileId, name: document?.file_name ?? 'cv-photo.jpg' };
    const session: Session = { ...x.session, cv };
    await store.saveSession(x.chat, session);
    if (session.mode === 'check') {
      await check({ ...x, session }, { name: cv.name, data: await deps.download(fileId) });
    } else if (session.step === 'cv') {
      await submit(x, session);
    } else {
      await ctx.reply(session.step === 'email' ? x.t.askEmail : x.t.askName(esc(session.title ?? '')), html);
    }
  });

  bot.on('message:text', async (ctx) => {
    const x = await turn(ctx, deps);
    if (!x) return;
    const text = ctx.message.text.trim();
    if (x.session.mode === 'apply' && x.session.step === 'name') return setName(x, text);
    if (x.session.mode === 'apply' && x.session.step === 'email') {
      if (!looksLikeEmail(text)) return void (await ctx.reply(x.t.badEmail));
      await store.saveSession(x.chat, { ...x.session, email: text, step: 'consent' });
      const keyboard = new InlineKeyboard().text(x.t.agree, 'consent:yes').row().text(x.t.cancel, 'cancel');
      await ctx.reply(x.t.askConsent(`${deps.careersUrl}/how-we-hire#data`), { ...html, reply_markup: keyboard });
      return;
    }
    if (x.session.mode === 'apply' && x.session.step === 'cv') return askCv(x, x.session);
    if (x.session.mode === 'check') return void (await ctx.reply(x.t.sendCv(esc(x.session.title ?? '')), html));
    await ctx.reply(x.t.unexpectedText);
  });

  // last resort: errors the boundary above could not report (e.g. the reply itself failed)
  bot.catch((error) => log(`update ${error.ctx.update.update_id} failed`, error.error));
}

/** Registered before every handler: a failure becomes a readable reply instead of silence. */
function errorBoundary(bot: Bot, log: (message: string, error?: unknown) => void): void {
  bot.use(async (ctx, next) => {
    try {
      await next();
    } catch (cause) {
      log(`update ${ctx.update.update_id} failed`, cause);
      const lang = langOf(ctx.from?.language_code);
      const readable = cause instanceof ApiError && cause.status < 500 && cause.status !== 404;
      await ctx.reply(readable ? esc(cause.message) : T[lang].error, html).catch(() => undefined);
    }
  });
}
