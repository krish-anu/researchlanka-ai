import { FlagCard } from "@/components/admin/FlagCard";
import { EmptyState, SectionHeading } from "@/components/ui/Feedback";
import { listFlags } from "@/services/workspace/store";

export const metadata = { title: "Flag triage" };

export default async function AdminFlagsPage() {
  const flags = await listFlags();
  const open = flags.filter((flag) => flag.status === "open");
  const closed = flags.filter((flag) => flag.status !== "open");

  return (
    <div className="flex flex-col gap-8">
      <SectionHeading
        title="Flag triage"
        description="Records that signed-in users reported as wrong. Accepting a flag records the decision for the next pipeline correction pass — it does not edit the published record."
      />

      <section>
        <h2 className="mb-3 font-display text-h3 text-ink">
          Open ({open.length})
        </h2>
        {open.length === 0 ? (
          <EmptyState
            title="Nothing to triage"
            description="No open flags. Signed-in users raise these from a publication page."
          />
        ) : (
          <div className="flex flex-col gap-4">
            {open.map((flag) => (
              <FlagCard key={flag.id} flag={flag} />
            ))}
          </div>
        )}
      </section>

      {closed.length > 0 ? (
        <section>
          <h2 className="mb-3 font-display text-h3 text-ink">
            Closed ({closed.length})
          </h2>
          <div className="flex flex-col gap-4">
            {closed.map((flag) => (
              <FlagCard key={flag.id} flag={flag} />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
