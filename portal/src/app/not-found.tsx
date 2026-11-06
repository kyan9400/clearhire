import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="page" style={{ padding: '72px 16px', maxWidth: 620 }}>
      <h1>Not found</h1>
      <p style={{ margin: '12px 0 24px', color: 'var(--text-2)' }}>
        This role may have closed, or the link is incomplete. A status link stops working after its data is erased.
      </p>
      <Link href="/" className="btn primary">
        See open roles
      </Link>
    </div>
  );
}
