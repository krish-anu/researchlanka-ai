import Link from "next/link";

/** A row of query-string filters for a review queue; the current one is marked. */
export function QueueFilter({
  label,
  options,
  current,
  hrefFor,
}: {
  label: string;
  options: { value: string; label: string; count?: number }[];
  current: string;
  hrefFor: (value: string) => string;
}) {
  return (
    <nav aria-label={label} className="flex flex-wrap gap-2">
      {options.map((option) => {
        const active = option.value === current;
        return (
          <Link
            key={option.value}
            href={hrefFor(option.value)}
            aria-current={active ? "page" : undefined}
            className={`chip ${active ? "border-primary text-primary" : ""}`}
          >
            {option.label}
            {option.count ? <span className="data-mono text-muted">{option.count}</span> : null}
          </Link>
        );
      })}
    </nav>
  );
}
