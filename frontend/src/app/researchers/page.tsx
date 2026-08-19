import { ApiErrorPanel, EmptyState } from "@/components/ui/Feedback";
import { RankingTable } from "@/components/ui/RankingTable";
import { SnapshotNote } from "@/components/ui/Provenance";
import { listResearchers } from "@/services/api";
import { extractFilters, type SearchParams } from "@/services/filters";
import { researcherHref } from "@/services/links";

export const metadata = {
  title: "Researchers",
  description:
    "Most active authors in the Sri Lankan research corpus, ranked by number of publications recorded.",
};

export default async function ResearchersPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const filters = extractFilters(params);
  const result = await listResearchers({ ...filters, limit: 100 });

  return (
    <div className="flex flex-col gap-10 md:gap-12">
      <div>
        <h1 className="title-page text-ink">Researchers</h1>
        <p className="mt-1 max-w-prose text-body-sm text-ink-secondary">
          Author aggregates ranked by publication count. Open a profile for the
          full publication list, co-author network, and output over time.
        </p>
      </div>

      <div className="panel border-warning/40 p-3">
        <p className="flex gap-2 text-body-sm text-ink-secondary">
          <span aria-hidden className="text-warning">
            ▲
          </span>
          <span>
            <strong className="font-medium text-ink">
              Author names are not disambiguated.
            </strong>{" "}
            Profiles group records by normalised display name, so common names
            may merge distinct people and name variants may split one person
            across several entries. Treat these aggregates as indicative.
          </span>
        </p>
      </div>

      {!result.ok ? (
        <ApiErrorPanel error={result.error} what="the researcher directory" />
      ) : result.value.data.length === 0 ? (
        <EmptyState
          title="No researchers found"
          description="No author aggregates matched the current filters."
        />
      ) : (
        <>
          <div className="panel p-1">
            <RankingTable
              entries={result.value.data}
              labelHeader="Researcher"
              href={researcherHref}
            />
          </div>
          <SnapshotNote
            snapshotDate={result.value.meta.snapshot_date}
            datasetStage={result.value.meta.dataset_stage}
          />
        </>
      )}
    </div>
  );
}
