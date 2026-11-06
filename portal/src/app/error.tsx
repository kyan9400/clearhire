'use client';

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="page" style={{ padding: '72px 16px', maxWidth: 620 }}>
      <h1>Something went wrong</h1>
      <p style={{ margin: '12px 0 24px', color: 'var(--text-2)' }}>
        We could not reach the careers service. Please try again in a moment.
      </p>
      <button className="btn primary" type="button" onClick={reset}>
        Try again
      </button>
    </div>
  );
}
