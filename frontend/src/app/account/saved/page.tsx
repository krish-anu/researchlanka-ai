import Link from "next/link";

import { removeSaved } from "@/app/actions/workspace";
import { EmptyState, SectionHeading } from "@/components/ui/Feedback";
import { requireCapability } from "@/services/auth/server";
import { formatDate } from "@/services/format";
import { publicationHref } from "@/services/links";
import { listSavedItems } from "@/services/workspace/store";

export const metadata = { title: "Saved library" };

export default async function SavedPage() {
  const user = await requireCapability("library.save", "/account/saved");
  const items = await listSavedItems(user.id);

  return (
    <div>
      <SectionHeading
        title="Saved library"
        description="Publications you have kept from search and profile pages. Saving is per account and private to you."
      />

      {items.length === 0 ? (
        <EmptyState
          title="Nothing saved yet"
          description="Open any publication and use “Save to library” to keep it here."
          action={
            <Link
              href="/publications"
              className="mt-2 rounded bg-primary px-4 py-2 text-body-sm font-semibold text-on-primary hover:bg-primary-hover"
            >
              Search publications
            </Link>
          }
        />
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((item) => (
            <li
              key={item.id}
              className="panel flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between"
            >
              <div className="min-w-0">
                <Link
                  href={publicationHref(item.publication_key)}
                  className="font-display text-body-lg text-ink hover:text-primary hover:underline"
                >
                  {item.title}
                </Link>
                <p className="data-mono mt-1 truncate text-muted">
                  {item.publication_key}
                </p>
                <p className="mt-1 text-body-sm text-muted">
                  Saved {formatDate(item.created_at)}
                </p>
              </div>
              <form action={removeSaved} className="shrink-0">
                <input type="hidden" name="item_id" value={item.id} />
                <button
                  type="submit"
                  className="rounded border border-rule px-3 py-1.5 text-body-sm text-ink-secondary hover:border-critical hover:text-critical"
                >
                  Remove
                </button>
              </form>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
