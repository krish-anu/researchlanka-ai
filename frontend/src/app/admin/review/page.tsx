import { ResolutionCard } from "@/components/admin/ResolutionCard";
import { EmptyState, SectionHeading } from "@/components/ui/Feedback";
import {
  listCandidates,
  SEEDED_FROM_FIXTURE,
} from "@/services/workspace/resolution";

export const metadata = { title: "Resolution queue" };

export default async function AdminReviewPage() {
  const candidates = await listCandidates();
  const pending = candidates.filter((c) => c.status === "pending");
  const decided = candidates.filter((c) => c.status !== "pending");

  return (
    <div className="flex flex-col gap-8">
      <SectionHeading
        title="Entity resolution queue"
        description="Record pairs the deduplication model believes describe the same work. A merge is irreversible in the corpus, so every pair is confirmed by a person before the pipeline applies it."
      />

      {SEEDED_FROM_FIXTURE ? (
        <p className="panel border-l-[3px] border-l-warning p-4 text-body-sm text-ink-secondary">
          <span className="label-caps mr-2 text-warning">Fixture data</span>
          The API does not expose the deduplication model&apos;s candidate pairs
          yet — there is no route for them in{" "}
          <code className="data-mono rounded bg-sunk px-1 py-0.5">
            backend/src/api/routing/routes.py
          </code>
          . These pairs come from a local fixture so the review workflow can be
          exercised end to end; the decisions you record are real and audited,
          but the candidates are not live pipeline output.
        </p>
      ) : null}

      <section>
        <h2 className="mb-3 font-display text-h3 text-ink">
          Awaiting decision ({pending.length})
        </h2>
        {pending.length === 0 ? (
          <EmptyState
            title="Queue is clear"
            description="Every candidate pair the model produced has been decided."
          />
        ) : (
          <div className="flex flex-col gap-4">
            {pending.map((candidate) => (
              <ResolutionCard key={candidate.id} candidate={candidate} />
            ))}
          </div>
        )}
      </section>

      {decided.length > 0 ? (
        <section>
          <h2 className="mb-3 font-display text-h3 text-ink">
            Decided ({decided.length})
          </h2>
          <div className="flex flex-col gap-4">
            {decided.map((candidate) => (
              <ResolutionCard key={candidate.id} candidate={candidate} />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
