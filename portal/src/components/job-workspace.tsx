'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useActionState, useId, useRef, useState } from 'react';

import { send, type Applied, type Precheck, type Requirement } from '@/lib/api';
import { duration } from '@/lib/format';

import { CheckList } from './check-list';
import styles from './job-workspace.module.css';

const ACCEPT = '.pdf,.docx,.txt,.png,.jpg,.jpeg,.webp,.tiff';
const MAX_MB = 10;

type Check =
  { state: 'idle' } | { state: 'checking' } | { state: 'done'; result: Precheck } | { state: 'error'; message: string };

export function JobWorkspace({
  vacancyId,
  title,
  requirements,
  telegramBot,
  children,
}: {
  vacancyId: string;
  title: string;
  requirements: Requirement[];
  /** The bot's username, when one is configured: candidates can apply there instead. */
  telegramBot?: string;
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [check, setCheck] = useState<Check>({ state: 'idle' });
  const [applyOpen, setApplyOpen] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const ids = useId();

  function pick(next: File | null) {
    if (next && next.size > MAX_MB * 1024 * 1024) {
      setCheck({ state: 'error', message: `The file is larger than ${MAX_MB} MB.` });
      return;
    }
    setFile(next);
    setCheck({ state: 'idle' });
  }

  async function runCheck() {
    if (!file) return;
    setCheck({ state: 'checking' });
    const body = new FormData();
    body.append('file', file);
    try {
      const result = await send<Precheck>(`/api/public/vacancies/${vacancyId}/precheck`, { method: 'POST', body });
      setCheck({ state: 'done', result });
      document.getElementById('requirements')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) {
      setCheck({ state: 'error', message: (error as Error).message });
    }
  }

  const [applyError, apply, applying] = useActionState(async (_: string | null, form: FormData) => {
    if (!file) return 'Choose your CV first.';
    form.set('file', file);
    form.set('consent', form.get('consent') ? 'true' : 'false');
    try {
      const { status_token } = await send<Applied>(`/api/public/vacancies/${vacancyId}/apply`, {
        method: 'POST',
        body: form,
      });
      router.push(`/status/${status_token}?new=1`);
      return null;
    } catch (error) {
      return (error as Error).message;
    }
  }, null);

  const result = check.state === 'done' ? check.result : null;
  const partly = result ? result.items.filter((i) => i.must && i.status === 'partial').length : 0;

  return (
    <div className={styles.layout}>
      <div className={styles.main}>
        <section id="requirements" className={styles.section} aria-labelledby={`${ids}-req`}>
          <div className={styles.sectionHead}>
            <h2 id={`${ids}-req`}>What the role needs</h2>
            {!result && <span className="muted">Check your CV to see which ones we can find in it.</span>}
          </div>
          {result && (
            <div className={styles.summary} role="status">
              <div className={styles.score} data-qualified={result.qualified}>
                <strong>
                  {result.must_met}/{result.must_total}
                </strong>
                <span>must-haves found</span>
              </div>
              <div className={styles.summaryText}>
                <p>
                  {result.qualified
                    ? 'Your CV shows every must-have for this role.'
                    : `We found ${result.must_met} of ${result.must_total} must-haves${partly ? `, and ${partly} partly` : ''}. If you have the missing ones, say so in your CV: we can only count what is written there.`}
                </p>
                <p className="muted">
                  Experience read: {duration(result.experience_months)}. This is the same reading the recruiter sees; a
                  person makes the decision.
                </p>
              </div>
            </div>
          )}
          <CheckList requirements={requirements} items={result?.items} />
        </section>
        <section className={styles.section}>
          <h2 className={styles.descTitle}>About the role</h2>
          {children}
        </section>
      </div>

      <aside className={styles.side} aria-label="Your CV">
        <div className={`card ${styles.panel}`}>
          <h2 className={styles.panelTitle}>Your CV</h2>
          <label
            className={styles.drop}
            data-has-file={!!file}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              pick(e.dataTransfer.files[0] ?? null);
            }}
          >
            <input
              ref={input}
              type="file"
              accept={ACCEPT}
              className="sr-only"
              onChange={(e) => pick(e.target.files?.[0] ?? null)}
            />
            {file ? (
              <>
                <strong className={styles.fileName}>{file.name}</strong>
                <span className="muted">{Math.max(1, Math.round(file.size / 1024))} KB · choose another</span>
              </>
            ) : (
              <>
                <strong>Drop your CV here or choose a file</strong>
                <span className="muted">PDF, Word, text or a photo of a paper CV · up to {MAX_MB} MB</span>
              </>
            )}
          </label>

          <button className="btn block" type="button" disabled={!file || check.state === 'checking'} onClick={runCheck}>
            {check.state === 'checking' ? 'Reading your CV…' : result ? 'Check again' : 'Check it against this role'}
          </button>
          <p className={styles.note}>The check runs in memory: your file is not stored and nobody is notified.</p>
          {check.state === 'error' && (
            <p className="error-box" role="alert">
              {check.message}
            </p>
          )}

          <hr className={styles.rule} />

          {!applyOpen ? (
            <>
              <button className="btn primary block" type="button" onClick={() => setApplyOpen(true)}>
                Apply for {title}
              </button>
              {telegramBot && (
                <a
                  className="btn block"
                  href={`https://t.me/${telegramBot}?start=job_${vacancyId}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Apply in Telegram
                </a>
              )}
            </>
          ) : (
            <form action={apply} className={styles.form}>
              <label className="field">
                Full name
                <input type="text" name="full_name" required minLength={2} maxLength={200} autoComplete="name" />
              </label>
              <label className="field">
                E-mail
                <input type="email" name="email" required maxLength={254} autoComplete="email" />
              </label>
              <label className="field">
                <span>
                  Telegram <span className="hint">optional, for updates from our bot</span>
                </span>
                <input type="text" name="telegram" maxLength={64} placeholder="@username" />
              </label>
              <label className={styles.consent}>
                <input type="checkbox" name="consent" required />
                <span>
                  I agree to the processing of my personal data for this and similar roles (152-FZ). I can erase it at
                  any time from my status page. <Link href="/how-we-hire#data">What is kept and for how long</Link>
                </span>
              </label>
              {!file && <p className="error-box">Choose your CV above first.</p>}
              {applyError && (
                <p className="error-box" role="alert">
                  {applyError}
                </p>
              )}
              <button className="btn primary block" type="submit" disabled={!file || applying}>
                {applying ? 'Sending…' : 'Send application'}
              </button>
            </form>
          )}
        </div>
      </aside>
    </div>
  );
}
