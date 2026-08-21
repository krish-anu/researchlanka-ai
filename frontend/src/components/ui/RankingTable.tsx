import Link from "next/link";

import { DataTable } from "@/components/ui/DataTable";
import { formatNumber } from "@/services/format";
import type { RankingEntry } from "@/types/api";

/**
 * Shared ranked directory table for researchers, institutions, topics and
 * fields — all four endpoints return the same `RankingEntry` shape.
 *
 * Rank is shown as a position column rather than encoded in colour, so the
 * ordering survives greyscale, screen readers and print.
 */
export function RankingTable({
  entries,
  labelHeader,
  href,
  caption,
  rankOffset = 0,
}: {
  entries: RankingEntry[];
  labelHeader: string;
  /** Profile lookups match on `label`, never the slugified `key`. */
  href?: (label: string) => string;
  caption?: string;
  rankOffset?: number;
}) {
  return (
    <DataTable
      caption={caption}
      columns={[
        {
          key: "rank",
          header: "#",
          numeric: true,
          render: (_row, index) => (
            <span className="text-muted">{rankOffset + index + 1}</span>
          ),
        },
        {
          key: "label",
          header: labelHeader,
          render: (row) =>
            href ? (
              <Link href={href(row.label)} className="text-ink hover:underline">
                {row.label}
              </Link>
            ) : (
              <span className="text-ink">{row.label}</span>
            ),
        },
        {
          key: "publications",
          header: "Publications",
          numeric: true,
          render: (row) => formatNumber(row.publication_count),
        },
        {
          key: "citations",
          header: "Citations",
          numeric: true,
          render: (row) => formatNumber(row.citation_total),
        },
      ]}
      rows={entries}
      rowKey={(row, index) => `${row.key}-${index}`}
      emptyMessage="No entries matched."
    />
  );
}
