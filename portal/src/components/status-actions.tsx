'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { send } from '@/lib/api';

import styles from './status-actions.module.css';

/** Shown right after applying: the link is the only key to this page, so ask the candidate to keep it. */
export function SaveLink() {
  const [copied, setCopied] = useState(false);
  const [url, setUrl] = useState('');
  useEffect(() => setUrl(window.location.href.replace(/\?.*$/, '')), []);

  return (
    <div className={styles.save} role="status">
      <div>
        <strong>Application sent. Keep this link.</strong>
        <p>It is the only way back to this page, and nobody else has it. Bookmark it or copy it somewhere safe.</p>
      </div>
      <div className={styles.copyRow}>
        <input readOnly value={url} aria-label="Your private status link" onFocus={(e) => e.target.select()} />
        <button
          className="btn"
          type="button"
          onClick={async () => {
            await navigator.clipboard.writeText(url);
            setCopied(true);
          }}
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
    </div>
  );
}

/** While the CV is still being read (a scan can take a few seconds of OCR), refresh the page data. */
export function RefreshWhileReading({ reading }: { reading: boolean }) {
  const router = useRouter();
  useEffect(() => {
    if (!reading) return;
    let tries = 0;
    const timer = setInterval(() => {
      tries += 1;
      if (tries > 20) clearInterval(timer);
      router.refresh();
    }, 2500);
    return () => clearInterval(timer);
  }, [reading, router]);
  return null;
}

export function EraseData({ token }: { token: string }) {
  const [phase, setPhase] = useState<'idle' | 'confirm' | 'erasing' | 'erased'>('idle');
  const [error, setError] = useState<string | null>(null);

  if (phase === 'erased') {
    return (
      <div className={styles.erased} role="status">
        <strong>Your data has been erased.</strong>
        <p>
          Your applications, CV and everything read from it are deleted. The audit log only keeps a note that an erasure
          happened. This link no longer works.
        </p>
      </div>
    );
  }

  return (
    <div className={styles.erase}>
      <div>
        <h3>Withdraw and erase my data</h3>
        <p className="muted">
          Withdraws your consent: deletes this and any other application, your CV and everything read from it. This
          cannot be undone.
        </p>
      </div>
      {phase === 'idle' ? (
        <button className="btn danger" type="button" onClick={() => setPhase('confirm')}>
          Erase my data
        </button>
      ) : (
        <div className={styles.confirm}>
          <span>Erase everything now?</span>
          <button
            className="btn danger"
            type="button"
            disabled={phase === 'erasing'}
            onClick={async () => {
              setPhase('erasing');
              setError(null);
              try {
                await send<null>(`/api/public/status/${encodeURIComponent(token)}`, { method: 'DELETE' });
                setPhase('erased');
              } catch (e) {
                setError((e as Error).message);
                setPhase('confirm');
              }
            }}
          >
            {phase === 'erasing' ? 'Erasing…' : 'Yes, erase'}
          </button>
          <button className="btn" type="button" onClick={() => setPhase('idle')} disabled={phase === 'erasing'}>
            Keep it
          </button>
        </div>
      )}
      {error && (
        <p className="error-box" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
