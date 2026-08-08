import Link from "next/link";

export default function NotFound() {
  return (
    <div className="panel mx-auto max-w-lg p-6">
      <h1 className="text-lg font-semibold text-ink">Not found</h1>
      <p className="mt-2 text-sm text-ink-secondary">
        No record matches that address. It may have been merged into another
        record during deduplication, or removed from the dataset in a later
        snapshot.
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <Link
          href="/publications"
          className="rounded-md border border-rule bg-wash px-3 py-1.5 text-sm font-medium text-ink hover:bg-page"
        >
          Search publications
        </Link>
        <Link
          href="/"
          className="rounded-md border border-rule px-3 py-1.5 text-sm text-ink-secondary hover:bg-wash"
        >
          National dashboard
        </Link>
      </div>
    </div>
  );
}
