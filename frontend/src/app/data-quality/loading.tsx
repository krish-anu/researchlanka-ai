import { Skeleton } from "@/components/ui/Feedback";

/**
 * Scoped to this segment deliberately.
 *
 * A `loading.tsx` opens a Suspense boundary over its segment *and every nested
 * route*, which flushes response headers before the page body runs — so a
 * `notFound()` in a nested detail route can no longer set a 404 status. This
 * segment has no dynamic children, so the boundary is safe here; the list
 * segments (publications, researchers, institutions, topics) deliberately have
 * none, and the dashboard streams via in-page Suspense instead.
 */
export default function Loading() {
  return (
    <div className="flex flex-col gap-4" aria-busy="true">
      <span className="sr-only">Loading data quality report…</span>
      <Skeleton className="h-9 w-64" />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
      </div>
      <Skeleton className="h-64" />
    </div>
  );
}
