import type { ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T, index: number) => ReactNode;
  /** Numeric columns right-align and inherit tabular figures. */
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
 * a non-visual route to the same numbers — several palette slots sit below 3:1
 * on the light surface, and the relief rule requires either direct labels or
 * this.
 */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  caption,
  emptyMessage = "No data available.",
}: DataTableProps<T>) {
  if (rows.length === 0) {
    return <p className="p-4 text-sm text-muted">{emptyMessage}</p>;
  }

  return (
    <div className="scroll-x">
      <table className="w-full min-w-[32rem] border-collapse text-sm">
        {caption ? (
          <caption className="pb-2 text-left text-xs text-muted">{caption}</caption>
        ) : null}
        <thead>
          <tr className="border-b border-hairline">
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={`px-3 py-2 text-xs font-medium uppercase tracking-wide text-muted ${
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
              className="border-b border-hairline last:border-0 hover:bg-wash"
            >
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={`px-3 py-2 align-top text-ink-secondary ${
                    column.numeric ? "text-right" : "text-left"
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
    <details className="mt-3 border-t border-hairline pt-3">
      <summary className="cursor-pointer text-sm text-ink-secondary hover:text-ink">
        {label}
      </summary>
      <div className="mt-2">{children}</div>
    </details>
  );
}
