import type { Metadata } from 'next';
import Link from 'next/link';

import styles from './page.module.css';

export const metadata: Metadata = {
  title: 'How we decide',
  description: 'How your CV is read, what the team sees, and what happens to your data.',
};

export default function HowWeHire() {
  const retention = Number(process.env.CLEARHIRE_RETENTION_DAYS ?? 365);
  return (
    <article className={`page ${styles.page}`}>
      <h1>How we decide</h1>
      <p className={styles.lead}>
        Software reads every CV by the same rules and shows its working. People make the decisions.
      </p>

      <section>
        <h2>1. The role is split into checks</h2>
        <p>
          A role&apos;s description becomes a short list of requirements, such as &ldquo;5+ years of Python&rdquo; or
          &ldquo;English B2&rdquo;, each marked must-have or nice to have. A recruiter reviews the list before the role
          opens. It is the list you see on every role page.
        </p>
      </section>

      <section>
        <h2>2. Your CV is read against each check</h2>
        <p>Each requirement is marked found, partly found or not found, with the lines of your CV that show it:</p>
        <ul>
          <li>
            <strong>Skills</strong> are recognised in Russian and English, including common spellings and related tools
            (for example, Django counts as Python experience).
          </li>
          <li>
            <strong>Experience</strong> is counted from the dates of your jobs, overlaps counted once.
          </li>
          <li>
            <strong>Languages and education</strong> are read from those sections, with levels such as B2 or a
            master&apos;s degree.
          </li>
          <li>
            <strong>Other requirements</strong>, like &ldquo;mentoring developers&rdquo;, are compared by meaning with
            what you wrote, and only count when the match is close.
          </li>
        </ul>
        <p>
          Scanned or photographed CVs are read with OCR. If something is missing from the reading, it is usually missing
          from the CV text: write it there and check again.
        </p>
      </section>

      <section>
        <h2>3. Personal details are hidden</h2>
        <p>
          Your name, photo, contacts, age and birth date, gender, marital status, children and citizenship say nothing
          about whether you can do the job. They are removed before the model reads your CV, so they cannot change your
          result, and the team reviews applications with them hidden by default. Hiring managers never see them. We test
          this: swapping these details between otherwise identical CVs leaves every result unchanged.
        </p>
      </section>

      <section>
        <h2>4. People decide</h2>
        <p>
          The reading orders applications and explains them; it does not reject anyone. A recruiter reads your
          application and moves it on or closes it. Every step, and every time someone opens your full details, is
          written to a tamper-evident log.
        </p>
      </section>

      <section id="data">
        <h2>5. Your data</h2>
        <ul>
          <li>
            <strong>Checking a CV</strong> before applying stores nothing: the file is read in memory and dropped.
          </li>
          <li>
            <strong>Applying</strong> stores your CV and what was read from it, with your consent under Federal Law
            152-FZ, for {retention} days after your last application. It is used for this role and for similar ones.
          </li>
          <li>
            <strong>Erasing</strong> is one button on your status page. It deletes your applications, your CV and
            everything read from it at once. The log keeps only a note that an erasure happened.
          </li>
        </ul>
      </section>

      <p className={styles.back}>
        <Link href="/" className="btn primary">
          See open roles
        </Link>
      </p>
    </article>
  );
}
