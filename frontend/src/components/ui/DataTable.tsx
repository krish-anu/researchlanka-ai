import type { ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T, index: number) => ReactNode;
  /** Numeric columns right-align and take the mono data face. */
  numeric?: boolean;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T, index: number) => string;
  caption?: string;
  emptyMessage?: string;
}

/**
 * Plain accessible table. Doubles as the "table view" that every chart needs as
 * a non-visual route to the same numbers, for readers who cannot use the plot
 * at all — screen readers, print, greyscale.
 *
 * Rows are separated by 1px rules with generous padding, per the design
 * system's "archival list" treatment.
 */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  caption,
  emptyMessage = "No data available.",
}: DataTableProps<T>) {
  if (rows.length === 0) {
    return <p className="p-4 text-body-sm text-muted">{emptyMessage}</p>;
  }

  return (
    <div className="scroll-x">
      <table className="w-full min-w-[32rem] border-collapse text-body-sm">
        {caption ? (
          <caption className="pb-2 text-left text-body-sm text-muted">
            {caption}
          </caption>
        ) : null}
        <thead>
          <tr className="border-b border-rule">
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={`label-caps px-3 py-3 text-muted ${
                  column.numeric ? "text-right" : "text-left"
                }`}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr
              key={rowKey(row, index)}
              className="border-b border-rule last:border-0 hover:bg-wash"
            >
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={`px-3 py-3 align-top text-ink-secondary ${
                    column.numeric ? "text-right font-mono" : "text-left"
                  }`}
                >
                  {column.render(row, index)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Collapsed table companion for a chart. Open-on-demand so the chart stays the
 * primary read, while the numbers remain reachable without colour vision.
 */
export function TableDisclosure({
  label = "View as table",
  children,
}: {
  label?: string;
  children: ReactNode;
}) {
  return (
    <details className="mt-4 border-t border-rule pt-3">
      <summary className="cursor-pointer text-body-sm text-ink-secondary hover:text-primary">
        {label}
      </summary>
      <div className="mt-2">{children}</div>
    </details>
  );
}
