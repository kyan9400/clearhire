import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { cache } from 'react';

import { JobWorkspace } from '@/components/job-workspace';
import { api } from '@/lib/api';
import { ago, parseDescription } from '@/lib/format';

import styles from './page.module.css';

export const dynamic = 'force-dynamic';

type Props = { params: Promise<{ id: string }> };

const load = cache((id: string) => api.vacancy(id)); // one API call for metadata and the page

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const vacancy = await load((await params).id);
  if (!vacancy) return { title: 'Role not found' };
  const summary = parseDescription(vacancy.description, vacancy.title).find((b) => b.kind === 'paragraph');
  return {
    title: `${vacancy.title}${vacancy.company ? ` at ${vacancy.company}` : ''}`,
    description: summary?.kind === 'paragraph' ? summary.text.slice(0, 160) : undefined,
    alternates: { canonical: `/jobs/${vacancy.id}` },
  };
}

export default async function JobPage({ params }: Props) {
  const vacancy = await load((await params).id);
  if (!vacancy) notFound();
  const blocks = parseDescription(vacancy.description, vacancy.title);

  // schema.org JobPosting, so search engines can list the role
  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'JobPosting',
    title: vacancy.title,
    description: vacancy.description,
    datePosted: vacancy.created_at,
    hiringOrganization: { '@type': 'Organization', name: vacancy.company || 'Clearhire' },
    ...(vacancy.location && {
      jobLocation: { '@type': 'Place', address: { '@type': 'PostalAddress', addressLocality: vacancy.location } },
    }),
    ...(vacancy.remote && { jobLocationType: 'TELECOMMUTE' }),
  };

  return (
    <div className="page">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, '\\u003c') }}
      />
      <Link href="/" className={styles.back}>
        ← All roles
      </Link>
      <header className={styles.head}>
        <h1>{vacancy.title}</h1>
        <p className={styles.meta}>
          {[vacancy.company, vacancy.location].filter(Boolean).join(' · ')}
          {vacancy.remote && <span className="chip accent">Remote</span>}
          <span className="muted">Posted {ago(vacancy.created_at)}</span>
        </p>
      </header>

      <JobWorkspace vacancyId={vacancy.id} title={vacancy.title} requirements={vacancy.requirements}>
        <div className={styles.description} lang={vacancy.language}>
          {blocks.map((block, i) =>
            block.kind === 'heading' ? (
              <h3 key={i}>{block.text}</h3>
            ) : block.kind === 'list' ? (
              <ul key={i}>
                {block.items.map((item, j) => (
                  <li key={j}>{item}</li>
                ))}
              </ul>
            ) : (
              <p key={i}>{block.text}</p>
            ),
          )}
        </div>
      </JobWorkspace>
    </div>
  );
}
