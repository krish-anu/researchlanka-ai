import type { PublicationTrace } from "@/types/api";

export function aiRelevanceText(trace?: PublicationTrace | null): string {
  if (!trace) return "AI relevance verified";
  if (trace.review_status === "human_accepted") return "Human verified";
  if (trace.review_status === "auto_accepted") {
    return "High-confidence automated classification";
  }
  return "AI relevance verified";
}

export function AIRelevanceStatus({
  trace,
  compact = false,
}: {
  trace?: PublicationTrace | null;
  compact?: boolean;
}) {
  return (
    <span
      className={[
        "inline-flex items-center gap-1.5 rounded-md border border-success-text/25 bg-wash text-success-text",
        compact ? "px-2 py-1 text-xs" : "px-2.5 py-1.5 text-body-sm",
      ].join(" ")}
      title="AI relevance is shown only after the ResearchLanka public eligibility gates."
    >
      <span aria-hidden>✓</span>
      <span className="font-medium">AI relevance</span>
      <span className="text-ink-secondary">{aiRelevanceText(trace)}</span>
    </span>
  );
}
