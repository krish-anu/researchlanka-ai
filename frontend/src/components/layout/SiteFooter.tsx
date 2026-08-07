import Link from "next/link";

export function SiteFooter() {
  return (
    <footer className="mt-12 border-t border-hairline bg-surface">
      <div className="mx-auto max-w-7xl px-4 py-6 text-sm text-ink-secondary">
        <p className="max-w-prose">
          ResearchLanka is a read-only public view of the consolidated Sri Lankan
          research corpus. Counts describe records observed in the dataset and
          are not official national totals.
        </p>
        <p className="mt-3 text-xs text-muted">
          Entity resolution and topic classification are automated and
          imperfect;{" "}
          <Link href="/data-quality" className="underline hover:text-ink">
            see the data quality notes
          </Link>{" "}
          before citing these figures.
        </p>
      </div>
    </footer>
  );
}
