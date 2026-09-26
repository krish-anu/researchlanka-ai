import { Button } from "@/components/ui/Button";

export default function NotFound() {
  return (
    <div className="panel mx-auto max-w-lg p-6">
      <h1 className="font-display text-h1 text-ink">Not found</h1>
      <p className="mt-2 text-body-sm text-ink-secondary">
        No record matches that address. It may have been merged into another
        record during deduplication, or removed from the dataset in a later
        snapshot.
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button href="/publications" variant="secondary">
          Search publications
        </Button>
        <Button href="/" variant="ghost">
          National dashboard
        </Button>
      </div>
    </div>
  );
}
