import Link from "next/link";

import { PublicationCardList } from "@/components/publications/PublicationCard";
import { DownloadLink } from "@/components/ui/ChartPanel";
import { ApiErrorPanel, EmptyState, SectionHeading } from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";
import { SnapshotNote } from "@/components/ui/Provenance";
import { exportUrl, getTopicPublications } from "@/services/api";
import { extractPage, type SearchParams } from "@/services/filters";
import { formatNumber } from "@/services/format";
import { decodeKeySegments, topicHref } from "@/services/links";

interface PageProps {
  params: Promise<{ key: string[] }>;
  searchParams: Promise<SearchParams>;
}

export async function generateMetadata({ params }: PageProps) {
  const { key } = await params;
  const topic = decodeKeySegments(key);
  return {
    title: topic,
    description: `Publications classified under the topic "${topic}".`,
  };
}

export default async function TopicPublicationsPage({
  params,
  searchParams,
}: PageProps) {
  const { key } = await params;
  const query = await searchParams;
  const topicKey = decodeKeySegments(key);
  const page = extractPage(query);

  const result = await getTopicPublications(topicKey, {
    page,
    page_size: 25,
  });

  return (
    <div className="flex flex-col gap-4">
      <nav className="text-sm text-muted">
        <Link href="/topics" className="hover:text-ink hover:underline">
          Topics
        </Link>
        <span aria-hidden> / </span>
        <span>{topicKey}</span>
      </nav>

      <SectionHeading
        title={topicKey}
        description={
          result.ok
            ? `${formatNumber(result.value.pagination.total)} publications classified under this topic.`
            : undefined
        }
        action={
          <DownloadLink href={exportUrl("publications.csv", { topic: [topicKey] })}>
            Export (CSV)
          </DownloadLink>
        }
      />

      {!result.ok ? (
        <ApiErrorPanel error={result.error} what="publications for this topic" />
      ) : result.value.data.length === 0 ? (
        <EmptyState
          title="No publications under this topic"
          description="The topic exists in the classification but no records matched."
        />
      ) : (
        <>
          <PublicationCardList publications={result.value.data} />
          <Pagination
            pagination={result.value.pagination}
            basePath={topicHref(topicKey)}
            searchParams={query}
          />
          <SnapshotNote
            snapshotDate={result.value.meta.snapshot_date}
            datasetStage={result.value.meta.dataset_stage}
          />
        </>
      )}
    </div>
  );
}
