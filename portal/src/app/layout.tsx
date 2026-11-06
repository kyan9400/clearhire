import type { Metadata, Viewport } from 'next';
import Link from 'next/link';

import styles from './layout.module.css';
import './globals.css';

export const metadata: Metadata = {
  title: { default: 'Careers · Clearhire', template: '%s · Clearhire careers' },
  description:
    'Open roles. Check your CV against a vacancy before you apply, and see exactly how it was read, requirement by requirement.',
  metadataBase: new URL(process.env.CLEARHIRE_PUBLIC_URL ?? 'http://localhost:3100'),
  openGraph: { type: 'website', siteName: 'Clearhire careers' },
};

export const viewport: Viewport = {
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#f6f7f9' },
    { media: '(prefers-color-scheme: dark)', color: '#0e1116' },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a className="sr-only" href="#main">
          Skip to content
        </a>
        <header className={styles.header}>
          <div className={`page ${styles.bar}`}>
            <Link href="/" className={styles.brand}>
              <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
                <rect width="24" height="24" rx="6" fill="var(--accent)" />
                <path
                  d="M7 12.5l3.2 3.2L17 9"
                  fill="none"
                  stroke="#fff"
                  strokeWidth="2.4"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              Clearhire <span>careers</span>
            </Link>
            <nav className={styles.nav} aria-label="Main">
              <Link href="/">Open roles</Link>
              <Link href="/how-we-hire">How we decide</Link>
            </nav>
          </div>
        </header>
        <main id="main">{children}</main>
        <footer className={styles.footer}>
          <div className={`page ${styles.footRow}`}>
            <span>
              Every CV is read by the same rules, and people make every decision.{' '}
              <Link href="/how-we-hire">How it works</Link>
            </span>
            <span className="muted">Personal data is processed under 152-FZ with your consent.</span>
          </div>
        </footer>
      </body>
    </html>
  );
}
