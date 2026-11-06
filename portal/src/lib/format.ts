import type { PublicStage } from './api';

export type Block =
  { kind: 'heading'; text: string } | { kind: 'list'; items: string[] } | { kind: 'paragraph'; text: string };

const BULLET = /^\s*(?:[-–—•*·▪]|\d{1,2}[.)])\s+/;

/**
 * Vacancy descriptions are plain text. Short lines ending in a colon become headings, runs of bulleted
 * lines become lists, everything else is a paragraph. The first line repeats the title, so it is dropped
 * when it does.
 */
export function parseDescription(text: string, title = ''): Block[] {
  const lines = text.replace(/\r\n?/g, '\n').split('\n');
  if (lines[0]?.trim().toLowerCase() === title.trim().toLowerCase() && title) lines.shift();
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  const flush = () => {
    if (paragraph.length) blocks.push({ kind: 'paragraph', text: paragraph.join(' ') });
    paragraph = [];
  };
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      flush();
      continue;
    }
    if (BULLET.test(line)) {
      flush();
      const item = line.replace(BULLET, '');
      const last = blocks.at(-1);
      if (last?.kind === 'list') last.items.push(item);
      else blocks.push({ kind: 'list', items: [item] });
    } else if (line.endsWith(':') && line.length <= 60) {
      flush();
      blocks.push({ kind: 'heading', text: line.slice(0, -1) });
    } else {
      paragraph.push(line);
    }
  }
  flush();
  return blocks;
}

export function duration(months: number): string {
  if (months <= 0) return 'none found';
  const years = Math.floor(months / 12);
  const rest = months % 12;
  const parts = [];
  if (years) parts.push(`${years} ${years === 1 ? 'year' : 'years'}`);
  if (rest) parts.push(`${rest} ${rest === 1 ? 'month' : 'months'}`);
  return parts.join(' ');
}

export function ago(iso: string, now = new Date()): string {
  const days = Math.floor((now.getTime() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 7) return `${days} days ago`;
  if (days < 30) {
    const weeks = Math.floor(days / 7);
    return `${weeks} ${weeks === 1 ? 'week' : 'weeks'} ago`;
  }
  const months = Math.floor(days / 30);
  return `${months} ${months === 1 ? 'month' : 'months'} ago`;
}

export function date(iso: string): string {
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(iso));
}

export const STAGES: { stage: PublicStage; label: string; help: string }[] = [
  { stage: 'received', label: 'Received', help: 'Your application and CV have arrived.' },
  { stage: 'in review', label: 'In review', help: 'A recruiter is reading your application.' },
  { stage: 'interview', label: 'Interview', help: 'The team would like to talk to you.' },
  { stage: 'offer', label: 'Offer', help: 'An offer is on its way.' },
  { stage: 'hired', label: 'Hired', help: 'Welcome aboard.' },
];

/** Where each step of the progress bar stands for an application at `stage`. */
export function steps(stage: PublicStage): ('done' | 'current' | 'todo')[] {
  if (stage === 'closed') return STAGES.map(() => 'todo');
  const at = STAGES.findIndex((s) => s.stage === stage);
  return STAGES.map((_, i) => (i < at ? 'done' : i === at ? (stage === 'hired' ? 'done' : 'current') : 'todo'));
}

/** Split a quote into the plain text around the supporting words, for <mark>. */
export function quoteParts(quote: string, [start, end]: [number, number]): [string, string, string] {
  if (start < 0 || end > quote.length || start >= end) return [quote, '', ''];
  return [quote.slice(0, start), quote.slice(start, end), quote.slice(end)];
}
