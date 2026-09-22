"use client";
import { DownloadIcon } from "@/components/layout/NavIcons";

export function CsvDownload({ filename, headers, rows }: { filename: string; headers: string[]; rows: (string | number)[][] }) {
  function download() {
    const cell = (value: string | number) => {
      const text = typeof value === "string" && /^[=+@\-\t\r]/.test(value) ? `'${value}` : String(value);
      return `"${text.replaceAll('"', '""')}"`;
    };
    const csv = [headers, ...rows].map(row => row.map(cell).join(",")).join("\r\n");
    const url = URL.createObjectURL(new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = filename; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <button type="button" className="button" onClick={download}><DownloadIcon className="h-3.5 w-3.5" />Download CSV</button>;
}
