import Link from "next/link";
import type { ReactNode } from "react";

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
  leadingColumn,
  showCitations = false,
  fitWidth = false,
}: {
  entries: RankingEntry[];
  labelHeader: string;
  /** Profile lookups match on `label`, never the slugified `key`. */
  href?: (label: string) => string;
  caption?: string;
  rankOffset?: number;
  /** `citation_total` is already on the ranking row. Off for directories that do not show it. */
  showCitations?: boolean;
  /** Let the name column wrap instead of forcing a wide table. */
  fitWidth?: boolean;
  /** Optional leading column (e.g. compare checkboxes). */
  leadingColumn?: {
    header: string;
    render: (row: RankingEntry, index: number) => ReactNode;
  };
}) {
  return (
    <DataTable
      caption={caption}
      columns={[
        ...(leadingColumn
          ? [
              {
                key: "leading",
                header: leadingColumn.header,
                render: leadingColumn.render,
              },
            ]
          : []),
        {
          key: "rank",
          header: "#",
          numeric: true,
          render: (_row: RankingEntry, index: number) => (
            <span className="text-muted">{rankOffset + index + 1}</span>
          ),
        },
        {
          key: "label",
          header: labelHeader,
          render: (row: RankingEntry) =>
            href ? (
              <Link
                href={href(row.label)}
                className="inline whitespace-normal break-words text-ink hover:underline [overflow-wrap:anywhere]"
              >
                {row.label}
              </Link>
            ) : (
              <span className="whitespace-normal break-words text-ink [overflow-wrap:anywhere]">
                {row.label}
              </span>
            ),
        },
        {
          key: "publications",
          header: "Publications",
          numeric: true,
          render: (row: RankingEntry) => formatNumber(row.publication_count),
        },
        ...(showCitations
          ? [
              {
                key: "citations",
                header: "Citations",
                numeric: true,
                render: (row: RankingEntry) => formatNumber(row.citation_total),
              },
            ]
          : []),
      ]}
      rows={entries}
      rowKey={(row, index) => `${row.key}-${index}`}
      emptyMessage="No entries matched."
      fit={fitWidth}
    />
  );
}
