import { quoteParts } from '../vacancy/match-panel';
import { niceMax } from './bar-chart';
import { duration, initials, percent, relativeDate } from './format';

describe('format', () => {
  it('writes durations in years and months', () => {
    expect(duration(29)).toBe('2 y 5 mo');
    expect(duration(12)).toBe('1 y');
    expect(duration(4)).toBe('4 mo');
    expect(duration(null)).toBe('—');
  });

  it('writes shares as percentages', () => {
    expect(percent(0.251)).toBe('25%');
    expect(percent(null)).toBe('—');
  });

  it('writes dates relative to now', () => {
    const now = Date.parse('2026-11-06T12:00:00Z');
    expect(relativeDate('2026-11-06T08:00:00Z', now)).toBe('today');
    expect(relativeDate('2026-11-05T08:00:00Z', now)).toBe('yesterday');
    expect(relativeDate('2026-10-27T12:00:00Z', now)).toBe('10 days ago');
    expect(relativeDate('2026-06-01T12:00:00Z', now)).toBe('5 mo ago');
  });

  it('takes initials from the first two words', () => {
    expect(initials('Анна Смирнова')).toBe('АС');
    expect(initials('Candidate 8F3A')).toBe('C8');
  });
});

describe('quoteParts', () => {
  const evidence = {
    quote: 'Built Kafka consumers for payments.',
    page: 1,
    section: 'experience',
    source: 'skill',
  };

  it('marks the highlighted span', () => {
    expect(quoteParts({ ...evidence, highlight: [6, 11] })).toEqual([
      { text: 'Built ', mark: false },
      { text: 'Kafka', mark: true },
      { text: ' consumers for payments.', mark: false },
    ]);
  });

  it('keeps the quote whole when nothing is highlighted', () => {
    expect(quoteParts({ ...evidence, highlight: [0, 0] })).toEqual([
      { text: evidence.quote, mark: false },
    ]);
  });
});

describe('niceMax', () => {
  it('rounds up to 1, 2 or 5 times a power of ten', () => {
    expect(niceMax(7)).toBe(10);
    expect(niceMax(13)).toBe(20);
    expect(niceMax(180)).toBe(200);
    expect(niceMax(420)).toBe(500);
    expect(niceMax(1)).toBe(1);
  });
});
