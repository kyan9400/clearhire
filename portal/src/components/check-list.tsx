import type { CheckItem, Evidence, Requirement } from '@/lib/api';
import { quoteParts } from '@/lib/format';

import styles from './check-list.module.css';

const LABEL = { met: 'Found', partial: 'Partly', missing: 'Not found' } as const;
const SOURCE: Record<string, string> = {
  skill: 'named in your CV',
  implied: 'implied by a related skill',
  dates: 'from your job dates',
  language: 'from your languages',
  education: 'from your education',
  semantic: 'similar meaning',
  inferred: 'inferred',
};

function Quote({ e }: { e: Evidence }) {
  const [before, hit, after] = quoteParts(e.quote, e.highlight);
  return (
    <figure className={styles.quote}>
      <blockquote>
        {before}
        {hit && <mark>{hit}</mark>}
        {after}
      </blockquote>
      <figcaption>
        {[e.section !== 'header' && e.section, e.page && `page ${e.page}`, SOURCE[e.source] ?? e.source]
          .filter(Boolean)
          .join(' · ')}
      </figcaption>
    </figure>
  );
}

/**
 * The vacancy's requirements; once a CV has been read, each one carries what was found and the lines that
 * show it. Plain markup, so it renders on the server (status page) and in the browser (CV check) alike.
 */
export function CheckList({ requirements, items }: { requirements: Requirement[]; items?: CheckItem[] }) {
  const byId = new Map(items?.map((i) => [i.requirement_id, i]));
  const groups = [
    { title: 'Must have', list: requirements.filter((r) => r.must) },
    { title: 'Nice to have', list: requirements.filter((r) => !r.must) },
  ].filter((g) => g.list.length);

  return (
    <div className={styles.groups}>
      {groups.map((group) => (
        <section key={group.title}>
          <h3 className={styles.groupTitle}>{group.title}</h3>
          <ul className={styles.list}>
            {group.list.map((r) => {
              const item = byId.get(r.id);
              return (
                <li key={r.id} className={styles.item} data-status={item?.status ?? 'unknown'}>
                  <span className={styles.mark} aria-hidden="true">
                    {item ? { met: '✓', partial: '½', missing: '✕' }[item.status] : '•'}
                  </span>
                  <div className={styles.body}>
                    <div className={styles.head}>
                      <span>{r.text}</span>
                      {item && <span className={`chip ${item.status}`}>{LABEL[item.status]}</span>}
                    </div>
                    {item?.detail && <p className={styles.detail}>{item.detail}</p>}
                    {item?.evidence.slice(0, 2).map((e, i) => (
                      <Quote key={i} e={e} />
                    ))}
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
