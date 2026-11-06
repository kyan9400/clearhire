import type { Role, Source, Stage } from '../api/types';

export const STAGE_LABEL: Record<Stage, string> = {
  new: 'New',
  screening: 'Screening',
  interview: 'Interview',
  offer: 'Offer',
  hired: 'Hired',
  rejected: 'Rejected',
};

export const SOURCE_LABEL: Record<Source, string> = {
  upload: 'Uploaded',
  portal: 'Careers portal',
  telegram: 'Telegram',
  import: 'Imported',
};

export const ROLE_LABEL: Record<Role, string> = {
  admin: 'Admin',
  recruiter: 'Recruiter',
  hiring_manager: 'Hiring manager',
};

export const LANGUAGE_NAME: Record<string, string> = {
  en: 'English',
  ru: 'Russian',
  de: 'German',
  fr: 'French',
  es: 'Spanish',
  zh: 'Chinese',
  ar: 'Arabic',
  tr: 'Turkish',
  it: 'Italian',
  uk: 'Ukrainian',
  kk: 'Kazakh',
};

/** CEFR levels as the API numbers them: 1 = A1 ... 6 = C2, 7 = native. */
export const LEVEL_NAME = ['', 'A1', 'A2', 'B1', 'B2', 'C1', 'C2', 'Native'];

/** 29 -> "2 y 5 mo", 12 -> "1 y", 4 -> "4 mo". */
export function duration(months: number | null | undefined): string {
  if (months === null || months === undefined) return '—';
  const years = Math.floor(months / 12);
  const rest = months % 12;
  if (years && rest) return `${years} y ${rest} mo`;
  if (years) return `${years} y`;
  return `${rest} mo`;
}

export function percent(value: number | null | undefined, digits = 0): string {
  return value === null || value === undefined ? '—' : `${(value * 100).toFixed(digits)}%`;
}

const DAY = 86_400_000;

export function relativeDate(iso: string, now = Date.now()): string {
  const days = Math.floor((now - Date.parse(iso)) / DAY);
  if (days <= 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 30) return `${days} days ago`;
  const months = Math.floor(days / 30);
  return months < 12 ? `${months} mo ago` : `${Math.floor(months / 12)} y ago`;
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]!.toUpperCase())
    .join('');
}
