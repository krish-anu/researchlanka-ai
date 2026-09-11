import { AIReviewCard } from "@/components/admin/AIReviewCard";
import { EmptyState, SectionHeading } from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";
import { listAIReviewCandidates } from "@/services/workspace/aiReview";
import { extractPage, type SearchParams } from "@/services/filters";
import { formatNumber } from "@/services/format";

export const metadata = { title: "AI review queue" };

const PAGE_SIZE = 25;

export default async function AdminAIReviewPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const page = extractPage(params);
  const result = await listAIReviewCandidates({ page, pageSize: PAGE_SIZE });
  const pendingOnPage = result.data.filter(
    (candidate) => candidate.status === "pending",
  );
  const decidedOnPage = result.data.filter(
    (candidate) => candidate.status === "decided",
  );

  return (
    <div className="flex flex-col gap-8">
      <SectionHeading
        title="AI relevance review queue"
        description={`Records from the 36k model-prediction file where the confidence threshold produced REVIEW. ${formatNumber(result.pending)} pending, ${formatNumber(result.decided)} decided.`}
      />

      <p className="panel border-l-[3px] border-l-machine p-4 text-body-sm text-ink-secondary">
        Resolved output is written to{" "}
        <code className="data-mono rounded bg-sunk px-1 py-0.5">
          backend/data/processed/ai/ai_relevance_best_model_rest_predictions_resolved.csv
        </code>
        . The original model prediction file is kept unchanged.
      </p>

      <section>
        <h2 className="mb-3 font-display text-h3 text-ink">
          Page {result.pagination.page}: awaiting AI decision ({pendingOnPage.length})
        </h2>
        {pendingOnPage.length === 0 ? (
          <EmptyState
            title={
              result.pending === 0
                ? "AI review queue is clear"
                : "No pending records on this page"
            }
            description={
              result.pending === 0
                ? "Every REVIEW prediction has an admin decision."
                : "Use pagination to continue reviewing pending records."
            }
          />
        ) : (
          <div className="flex flex-col gap-4">
            {pendingOnPage.map((candidate) => (
              <AIReviewCard key={candidate.id} candidate={candidate} />
            ))}
          </div>
        )}
      </section>

      {decidedOnPage.length > 0 ? (
        <section>
          <h2 className="mb-3 font-display text-h3 text-ink">
            Decided on this page ({decidedOnPage.length})
          </h2>
          <div className="flex flex-col gap-4">
            {decidedOnPage.map((candidate) => (
              <AIReviewCard key={candidate.id} candidate={candidate} />
            ))}
          </div>
        </section>
      ) : null}

      <Pagination
        pagination={result.pagination}
        basePath="/admin/ai-review"
        searchParams={params}
      />
    </div>
  );
}
