import type { CheckItem, Precheck, Vacancy } from './api';
import type { Texts } from './texts';

/** Telegram HTML: only &, < and > need escaping. */
export function esc(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/** Telegram allows 4096 characters per message; cut at a line break before that. */
export function clip(text: string, limit = 3900): string {
  if (text.length <= limit) return text;
  const cut = text.lastIndexOf('\n', limit);
  return `${text.slice(0, cut > 0 ? cut : limit)}\n…`;
}

export function duration(months: number, lang: 'en' | 'ru'): string {
  const years = Math.floor(months / 12);
  const rest = months % 12;
  if (lang === 'ru') {
    const plural = (n: number, one: string, few: string, many: string) =>
      n % 10 === 1 && n % 100 !== 11 ? one : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? few : many;
    const parts = [];
    if (years) parts.push(`${years} ${plural(years, 'год', 'года', 'лет')}`);
    if (rest) parts.push(`${rest} ${plural(rest, 'месяц', 'месяца', 'месяцев')}`);
    return parts.join(' ') || 'не найден';
  }
  const parts = [];
  if (years) parts.push(`${years} ${years === 1 ? 'year' : 'years'}`);
  if (rest) parts.push(`${rest} ${rest === 1 ? 'month' : 'months'}`);
  return parts.join(' ') || 'none found';
}

export function vacancyCard(v: Vacancy, t: Texts): string {
  const where = [v.company, v.location, v.remote ? t.remote : ''].filter(Boolean).map(esc).join(' · ');
  const list = (must: boolean) =>
    v.requirements
      .filter((r) => r.must === must)
      .map((r) => `• ${esc(r.text)}`)
      .join('\n');
  const parts = [`<b>${esc(v.title)}</b>`, where];
  const must = list(true);
  const nice = list(false);
  if (must) parts.push(`\n<b>${t.mustHave}</b>\n${must}`);
  if (nice) parts.push(`\n<b>${t.niceToHave}</b>\n${nice}`);
  return clip(parts.join('\n'));
}

function item(i: CheckItem, t: Texts): string {
  const quote = i.evidence[0];
  const line = `${t.status[i.status]} ${esc(i.text)}`;
  if (i.status !== 'met' && i.detail) return `${line}\n    <i>${esc(i.detail)}</i>`;
  if (!quote) return line;
  const [start, end] = quote.highlight;
  const q = quote.quote;
  const shown =
    start < end && end <= q.length
      ? `${esc(q.slice(0, start))}<b>${esc(q.slice(start, end))}</b>${esc(q.slice(end))}`
      : esc(q);
  return `${line}\n    <i>«${shown}»</i>`;
}

/** A CV check as a message: the summary, then each requirement with the line of the CV that shows it. */
export function checkReport(result: Precheck, t: Texts, lang: 'en' | 'ru'): string {
  const must = result.items.filter((i) => i.must);
  const nice = result.items.filter((i) => !i.must);
  const parts = [
    t.checkResult(result.must_met, result.must_total),
    t.experience(duration(result.experience_months, lang)),
  ];
  if (must.length) parts.push(`\n<b>${t.mustHave}</b>\n${must.map((i) => item(i, t)).join('\n')}`);
  if (nice.length) parts.push(`\n<b>${t.niceToHave}</b>\n${nice.map((i) => item(i, t)).join('\n')}`);
  return clip(parts.join('\n'));
}

const EMAIL = /^[^\s@<>()[\]\\,;:"]+@[^\s@<>()[\]\\,;:"]+\.[a-z]{2,}$/i;

export function looksLikeEmail(text: string): boolean {
  return text.length <= 254 && EMAIL.test(text.trim());
}
