/**
 * Decorative mock of a saved library — structure only, no claimed titles or counts.
 * Used on sign-in / register to show the benefit of an account.
 */
export function LibraryBenefitVisual({ className = "" }: { className?: string }) {
  return (
    <aside
      className={`panel overflow-hidden ${className}`.trim()}
      aria-hidden="true"
    >
      <div className="border-b border-rule bg-wash px-4 py-3">
        <p className="label-caps text-muted">Your library</p>
        <p className="mt-1 text-body-sm text-ink-secondary">
          Save records and flag issues — available after you sign in.
        </p>
      </div>
      <ul className="flex flex-col gap-0 divide-y divide-rule">
        {[0, 1, 2].map((index) => (
          <li key={index} className="flex flex-col gap-2 px-4 py-3">
            <span
              className="block h-3 max-w-[85%] rounded-sm bg-rule/80"
              style={{ width: `${72 - index * 12}%` }}
            />
            <span
              className="block h-2 max-w-[55%] rounded-sm bg-rule/50"
              style={{ width: `${48 - index * 8}%` }}
            />
            <span className="mt-1 flex gap-2">
              <span className="h-5 w-14 rounded bg-primary-muted" />
              <span className="h-5 w-10 rounded bg-wash" />
            </span>
          </li>
        ))}
      </ul>
    </aside>
  );
}
