export default function PublicationsLoading() {
  return (
    <div className="flex flex-col gap-3" aria-busy="true" aria-live="polite">
      <p className="text-body-sm text-muted">Loading publications…</p>
      <ul className="flex flex-col gap-3">
        {Array.from({ length: 6 }, (_, index) => (
          <li key={index} className="search-suggest-skeleton panel p-3" aria-hidden="true">
            <span style={{ width: "70%" }} />
            <span style={{ width: "46%" }} />
            <span style={{ width: "32%" }} />
          </li>
        ))}
      </ul>
    </div>
  );
}
