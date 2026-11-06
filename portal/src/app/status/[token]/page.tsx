import type { Metadata } from 'next';
import { notFound } from 'next/navigation';

import { CheckList } from '@/components/check-list';
import { EraseData, RefreshWhileReading, SaveLink } from '@/components/status-actions';
import { api } from '@/lib/api';
import { STAGES, date, steps } from '@/lib/format';

import styles from './page.module.css';

export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Your application', robots: { index: false, follow: false } };

type Props = { params: Promise<{ token: string }>; searchParams: Promise<{ new?: string }> };

export default async function StatusPage({ params, searchParams }: Props) {
  const [{ token }, { new: fresh }] = await Promise.all([params, searchParams]);
  const status = await api.status(token);
  if (!status) notFound();

  const progress = steps(status.stage);
  const current = STAGES.find((s) => s.stage === status.stage);
  const requirements = status.items.map((i) => ({ id: i.requirement_id, text: i.text, must: i.must, kind: '' }));
  const mustTotal = status.items.filter((i) => i.must).length;
  const mustMet = status.items.filter((i) => i.must && i.status === 'met').length;

  return (
    <div className={`page ${styles.page}`}>
      {fresh === '1' && <SaveLink />}
      <RefreshWhileReading reading={!status.cv_read} />

      <header className={styles.head}>
        <p className="muted">Your application</p>
        <h1>{status.vacancy}</h1>
        {status.company && <p className={styles.company}>{status.company}</p>}
      </header>

      <section className={`card ${styles.card}`} aria-labelledby="progress">
        <div className={styles.cardHead}>
          <h2 id="progress">
            {status.stage === 'closed' ? 'This application is closed' : (current?.label ?? status.stage)}
          </h2>
          <span className="muted">Updated {date(status.updated_at)}</span>
        </div>
        <p className={styles.help}>
          {status.stage === 'closed'
            ? 'The team has decided not to continue with this application. Thank you for applying. Your data is kept only for the period you agreed to, and you can erase it below at any time.'
            : current?.help}
        </p>
        {status.stage !== 'closed' && (
          <ol className={styles.steps}>
            {STAGES.map((s, i) => (
              <li key={s.stage} data-state={progress[i]} aria-current={progress[i] === 'current' ? 'step' : undefined}>
                <span className={styles.dot} aria-hidden="true" />
                <span>{s.label}</span>
              </li>
            ))}
          </ol>
        )}
        {status.timeline.length > 0 && (
          <ul className={styles.timeline}>
            {status.timeline.map((t, i) => (
              <li key={i}>
                <span className={styles.tlStage}>{STAGES.find((s) => s.stage === t.stage)?.label ?? 'Closed'}</span>
                <span className="muted">{date(t.at)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className={`card ${styles.card}`} aria-labelledby="reading">
        <div className={styles.cardHead}>
          <h2 id="reading">What we read in your CV</h2>
          {status.cv_read && mustTotal > 0 && (
            <span className={`chip ${mustMet === mustTotal ? 'met' : 'partial'}`}>
              {mustMet}/{mustTotal} must-haves found
            </span>
          )}
        </div>
        {status.cv_read ? (
          <>
            <p className={styles.help}>
              This is the reading the recruiter sees, requirement by requirement, with the lines of your CV behind it.
              By default the team reviews applications with your name, age, gender and contacts hidden.
            </p>
            <CheckList requirements={requirements} items={status.items} />
          </>
        ) : (
          <p className={styles.help} aria-live="polite">
            Your CV is being read. This page updates by itself in a few seconds.
          </p>
        )}
      </section>

      <section className={`card ${styles.card}`}>
        <EraseData token={token} />
      </section>
    </div>
  );
}
