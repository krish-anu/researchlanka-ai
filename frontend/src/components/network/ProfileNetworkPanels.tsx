import { CollaborationNetwork } from "@/components/network/CollaborationNetwork";
import { ChartPanel } from "@/components/ui/ChartPanel";
import { ApiErrorPanel } from "@/components/ui/Feedback";
import { getCollaborationNetwork, type QueryParams } from "@/services/api";
import { networkComponentForLabel } from "@/services/network";

/** Streamed network tab for researcher profiles — does not block overview/pubs. */
export async function ResearcherNetworkPanel({
  label,
  filters = {},
}: {
  label: string;
  filters?: QueryParams;
}) {
  const network = await getCollaborationNetwork({
    ...filters,
    scope: "researcher",
    researcher: [label],
    limit: 40,
    min_weight: 1,
  });

  return (
    <ChartPanel
      title="Author collaboration network"
      description="Co-author links across publications attributed to this researcher."
    >
      {!network.ok ? (
        <ApiErrorPanel
          error={network.error}
          what="the author collaboration network"
        />
      ) : (
        <CollaborationNetwork
          network={network.value.data}
          scope="researcher"
          height={380}
        />
      )}
    </ChartPanel>
  );
}

/** Streamed network tab for institution profiles. */
export async function InstitutionNetworkPanel({ label }: { label: string }) {
  const network = await getCollaborationNetwork({
    scope: "institution",
    institution: [label],
    limit: 40,
    min_weight: 1,
  });

  if (!network.ok) {
    return (
      <ApiErrorPanel error={network.error} what="the collaboration network" />
    );
  }

  const profileNetwork = networkComponentForLabel(network.value.data, label);

  if (profileNetwork.nodes.length === 0) {
    return (
      <p className="text-body-sm text-muted">
        No collaboration network for this institution under the current settings.
      </p>
    );
  }

  return (
    <ChartPanel
      title="Collaboration network"
      description="Co-publishing structure around this institution."
    >
      <CollaborationNetwork
        network={profileNetwork}
        scope="institution"
        height={380}
      />
    </ChartPanel>
  );
}
