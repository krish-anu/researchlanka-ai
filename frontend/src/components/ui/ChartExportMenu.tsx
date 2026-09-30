"use client";

import { useEffect, useId, useRef, useState } from "react";

import { DownloadIcon } from "@/components/layout/NavIcons";
import { Button } from "@/components/ui/Button";

type CsvBlobSource = {
  filename: string;
  headers: string[];
  rows: (string | number)[][];
};

function downloadCsvBlob({ filename, headers, rows }: CsvBlobSource) {
  const cell = (value: string | number) => {
    const text =
      typeof value === "string" && /^[=+@\-\t\r]/.test(value)
        ? `'${value}`
        : String(value);
    return `"${text.replaceAll('"', '""')}"`;
  };
  const csv = [headers, ...rows]
    .map((row) => row.map(cell).join(","))
    .join("\r\n");
  const url = URL.createObjectURL(
    new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/**
 * Per-panel Export menu: CSV + copy current URL (filters preserved in query).
 * Plotly PNG stays in the chart modebar; network PNG stays on the network toolbar.
 */
export function ChartExportMenu({
  csvHref,
  csv,
  csvLabel = "Download CSV",
}: {
  /** Server/API CSV export URL. */
  csvHref?: string;
  /** Client-built CSV (pairs, rankings without an export endpoint). */
  csv?: CsvBlobSource;
  csvLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  useEffect(() => {
    if (!copied) return;
    const t = window.setTimeout(() => setCopied(false), 1600);
    return () => window.clearTimeout(t);
  }, [copied]);

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
    } catch {
      setCopied(false);
    }
    setOpen(false);
  };

  const hasCsv = Boolean(csvHref || csv);

  return (
    <div ref={rootRef} className="relative inline-flex">
      <Button
        type="button"
        variant="secondary"
        size="sm"
        aria-expanded={open}
        aria-haspopup="menu"
        aria-controls={menuId}
        onClick={() => setOpen((v) => !v)}
      >
        <DownloadIcon className="h-3.5 w-3.5" />
        Export
      </Button>
      {open ? (
        <ul
          id={menuId}
          role="menu"
          className="absolute right-0 z-20 mt-1 min-w-48 rounded-md border border-rule bg-surface py-1 shadow-sm"
        >
          {hasCsv ? (
            <li role="none">
              {csvHref ? (
                <a
                  role="menuitem"
                  href={csvHref}
                  className="block px-3 py-2 text-body-sm text-ink hover:bg-wash"
                  onClick={() => setOpen(false)}
                >
                  {csvLabel}
                </a>
              ) : (
                <button
                  type="button"
                  role="menuitem"
                  className="block w-full px-3 py-2 text-left text-body-sm text-ink hover:bg-wash"
                  onClick={() => {
                    if (csv) downloadCsvBlob(csv);
                    setOpen(false);
                  }}
                >
                  {csvLabel}
                </button>
              )}
            </li>
          ) : null}
          <li role="none">
            <button
              type="button"
              role="menuitem"
              className="block w-full px-3 py-2 text-left text-body-sm text-ink hover:bg-wash"
              onClick={copyLink}
            >
              {copied ? "Link copied" : "Copy link with filters"}
            </button>
          </li>
        </ul>
      ) : null}
    </div>
  );
}
