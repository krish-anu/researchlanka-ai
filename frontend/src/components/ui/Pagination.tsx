import Link from "next/link";

import { pageHref, type SearchParams } from "@/services/filters";
import { formatNumber } from "@/services/format";
import type { Pagination as PaginationMeta } from "@/types/api";

interface PaginationProps {
  pagination: PaginationMeta;
  basePath: string;
  searchParams: SearchParams;
}

/** Window of page numbers around the current page, plus first/last anchors. */
function pageWindow(current: number, total: number): (number | "gap")[] {
  if (total <= 7) return Array.from({ length: total }, (_, index) => index + 1);

  const pages = new Set<number>([1, total, current]);
  for (const offset of [-1, 1]) {
    const candidate = current + offset;
    if (candidate > 1 && candidate < total) pages.add(candidate);
  }

  const sorted = [...pages].sort((a, b) => a - b);
  const result: (number | "gap")[] = [];
  let previous = 0;
  for (const page of sorted) {
    if (previous && page - previous > 1) result.push("gap");
    result.push(page);
    previous = page;
  }
  return result;
}

export function Pagination({
  pagination,
  basePath,
  searchParams,
}: PaginationProps) {
  const { page, total, total_pages: totalPages, page_size: pageSize } = pagination;
  if (totalPages <= 1) {
    return (
      <p className="text-body-sm text-ink-secondary">
        {formatNumber(total)} {total === 1 ? "result" : "results"}
      </p>
    );
  }

  const first = (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);
  const linkClass =
    "inline-flex min-w-9 items-center justify-center rounded border border-rule px-2 py-1 text-body-sm hover:border-primary hover:text-primary";

  return (
    <nav
      className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
      aria-label="Pagination"
    >
      <p className="text-body-sm text-ink-secondary">
        Showing {formatNumber(first)}–{formatNumber(last)} of{" "}
        {formatNumber(total)}
      </p>

      <div className="scroll-x">
        <ul className="flex items-center gap-1">
          <li>
            {page > 1 ? (
              <Link
                href={pageHref(basePath, searchParams, page - 1)}
                className={linkClass}
                rel="prev"
              >
                Previous
              </Link>
            ) : (
              <span className={`${linkClass} cursor-default text-muted opacity-50`}>
                Previous
              </span>
            )}
          </li>

          {pageWindow(page, totalPages).map((entry, index) =>
            entry === "gap" ? (
              <li key={`gap-${index}`} className="px-1 text-muted">
                …
              </li>
            ) : (
              <li key={entry}>
                <Link
                  href={pageHref(basePath, searchParams, entry)}
                  aria-current={entry === page ? "page" : undefined}
                  className={
                    entry === page
                      ? "inline-flex min-w-9 items-center justify-center rounded border border-primary bg-primary px-2 py-1 text-body-sm font-semibold text-on-primary"
                      : linkClass
                  }
                >
                  {entry}
                </Link>
              </li>
            ),
          )}

          <li>
            {page < totalPages ? (
              <Link
                href={pageHref(basePath, searchParams, page + 1)}
                className={linkClass}
                rel="next"
              >
                Next
              </Link>
            ) : (
              <span className={`${linkClass} cursor-default text-muted opacity-50`}>
                Next
              </span>
            )}
          </li>
        </ul>
      </div>
    </nav>
  );
}
