import Link from 'next/link';

import { api, type Vacancy } from '@/lib/api';
import { ago } from '@/lib/format';

import styles from './page.module.css';

export const dynamic = 'force-dynamic';

type Search = { q?: string; remote?: string; lang?: string };

function matches(v: Vacancy, { q = '', remote, lang }: Search): boolean {
  const needle = q.trim().toLowerCase();
  if (needle && ![v.title, v.company, v.location].some((field) => field.toLowerCase().includes(needle))) return false;
  if (remote === '1' && !v.remote) return false;
  if ((lang === 'en' || lang === 'ru') && v.language !== lang) return false;
  return true;
}

export default async function Home({ searchParams }: { searchParams: Promise<Search> }) {
  const search = await searchParams;
  const all = await api.vacancies();
  const shown = all.filter((v) => matches(v, search));
  const filtered = shown.length !== all.length;

  return (
    <div className="page">
      <section className={styles.hero}>
        <p className={styles.kicker}>{all.length} open roles</p>
        <h1>Apply knowing exactly how your CV is read.</h1>
        <p className={styles.lead}>
          Before you apply, check your CV against any role: you see each requirement, whether we found it, and the line
          of your CV that shows it. After you apply, the same reading stays on your status page, and a person makes
          every decision.
        </p>
        <ol className={styles.how}>
          <li>
            <strong>Check</strong> your CV against the role. Nothing is stored.
          </li>
          <li>
            <strong>Apply</strong> in one form, with your consent to data processing.
          </li>
          <li>
            <strong>Follow</strong> your private status link, or erase your data from it.
          </li>
        </ol>
      </section>

      <form className={styles.filters} role="search" action="/">
        <label className="field">
          <span className="sr-only">Search roles</span>
          <input type="search" name="q" placeholder="Role, company or city" defaultValue={search.q ?? ''} />
        </label>
        <label className="field">
          <span className="sr-only">Language of the role</span>
          <select name="lang" defaultValue={search.lang ?? ''}>
            <option value="">Any language</option>
            <option value="en">English</option>
            <option value="ru">Russian</option>
          </select>
        </label>
        <label className={styles.check}>
          <input type="checkbox" name="remote" value="1" defaultChecked={search.remote === '1'} /> Remote only
        </label>
        <button className="btn primary" type="submit">
          Search
        </button>
        {filtered && (
          <Link href="/" className={styles.reset}>
            Clear
          </Link>
        )}
      </form>

      <p className={`muted ${styles.count}`} aria-live="polite">
        {filtered ? `${shown.length} of ${all.length} roles` : `${all.length} roles`}
      </p>

      <ul className={styles.list}>
        {shown.map((v) => {
          const must = v.requirements.filter((r) => r.must).length;
          return (
            <li key={v.id}>
              <Link href={`/jobs/${v.id}`} className={`card ${styles.job}`}>
                <div className={styles.jobMain}>
                  <h2>{v.title}</h2>
                  <p className={styles.meta}>{[v.company, v.location].filter(Boolean).join(' · ')}</p>
                </div>
                <div className={styles.jobSide}>
                  {v.remote && <span className="chip accent">Remote</span>}
                  <span className="chip">{v.language === 'ru' ? 'Russian' : 'English'}</span>
                  <span className="chip">
                    {must} must-have{must === 1 ? '' : 's'}
                  </span>
                  <span className={`muted ${styles.when}`}>{ago(v.created_at)}</span>
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
      {!shown.length && (
        <div className={`card ${styles.empty}`}>
          {all.length ? 'No roles match these filters.' : 'There are no open roles right now. Please come back soon.'}
        </div>
      )}
    </div>
  );
}
