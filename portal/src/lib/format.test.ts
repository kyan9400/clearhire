import { describe, expect, it } from 'vitest';

import { errorMessage, isUuid } from './api';
import { ago, duration, parseDescription, quoteParts, steps } from './format';

describe('parseDescription', () => {
  it('turns headings, bullets and paragraphs into blocks and drops a repeated title', () => {
    const text =
      'Senior Python Developer\nWe build payments.\nFor banks.\n\nRequirements:\n- Python\n• SQL\n1. English B2\nNice to have:\n- Go';
    expect(parseDescription(text, 'Senior Python Developer')).toEqual([
      { kind: 'paragraph', text: 'We build payments. For banks.' },
      { kind: 'heading', text: 'Requirements' },
      { kind: 'list', items: ['Python', 'SQL', 'English B2'] },
      { kind: 'heading', text: 'Nice to have' },
      { kind: 'list', items: ['Go'] },
    ]);
  });

  it('keeps Russian text and long lines with a colon as paragraphs', () => {
    const long = 'Мы ищем человека, который будет отвечать за платёжную систему и её надёжность:';
    expect(parseDescription(`Требования:\n— Python\n${long}`)).toEqual([
      { kind: 'heading', text: 'Требования' },
      { kind: 'list', items: ['Python'] },
      { kind: 'paragraph', text: long },
    ]);
  });
});

describe('formatting', () => {
  it('writes durations and relative dates', () => {
    expect(duration(0)).toBe('none found');
    expect(duration(13)).toBe('1 year 1 month');
    expect(duration(74)).toBe('6 years 2 months');
    const now = new Date('2026-11-07T12:00:00Z');
    expect(ago('2026-11-07T08:00:00Z', now)).toBe('today');
    expect(ago('2026-11-06T08:00:00Z', now)).toBe('yesterday');
    expect(ago('2026-10-24T08:00:00Z', now)).toBe('2 weeks ago');
    expect(ago('2026-08-01T08:00:00Z', now)).toBe('3 months ago');
  });

  it('places an application on the progress bar', () => {
    expect(steps('received')).toEqual(['current', 'todo', 'todo', 'todo', 'todo']);
    expect(steps('interview')).toEqual(['done', 'done', 'current', 'todo', 'todo']);
    expect(steps('hired')).toEqual(['done', 'done', 'done', 'done', 'done']);
    expect(steps('closed')).toEqual(['todo', 'todo', 'todo', 'todo', 'todo']);
  });

  it('splits a quote around the highlighted words, ignoring bad offsets', () => {
    expect(quoteParts('built Kafka consumers', [6, 11])).toEqual(['built ', 'Kafka', ' consumers']);
    expect(quoteParts('short', [3, 40])).toEqual(['short', '', '']);
  });
});

describe('api helpers', () => {
  it('reads FastAPI error bodies', () => {
    expect(errorMessage({ detail: 'vacancy not found' }, 404)).toBe('vacancy not found');
    expect(errorMessage({ detail: [{ loc: ['body', 'email'], msg: 'invalid' }] }, 422)).toBe('email: invalid');
    expect(errorMessage(null, 429)).toMatch(/too many/i);
    expect(errorMessage(null, 500)).toMatch(/500/);
  });

  it('only sends real ids to the API', () => {
    expect(isUuid('3f1e0c55-8a3b-4f7e-9a7b-0f6c2d9e1a42')).toBe(true);
    expect(isUuid('../../admin')).toBe(false);
  });
});
