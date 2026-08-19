import { DataTable, type Column } from "@/components/ui/DataTable";
import { formatDecimal, formatNumber } from "@/services/format";
import { institutionHref, researcherHref } from "@/services/links";
import type { NetworkNode, NetworkSummary } from "@/types/api";
import Link from "next/link";

/**
 * How strong a community split has to be before it is worth reading.
 *
 * Newman's conventional floor. Below it the partition is largely an artefact
 * of the algorithm rather than structure in the data, and the panel says so
 * instead of presenting the community count as a finding.
 */
const MEANINGFUL_MODULARITY = 0.3;

function Stat({
  label,
  value,
  caption,
}: {
  label: string;
  value: string;
  caption: string;
}) {
  return (
    <div className="flex flex-col gap-0.5 border-l border-rule px-3 first:border-0 first:pl-0">
      <span className="label-caps text-muted">{label}</span>
      <span className="font-display text-h3 tabular text-primary">{value}</span>
      <span className="text-body-sm text-muted">{caption}</span>
    </div>
  );
}

/**
 * The graph-level read: how big, how connected, how clustered.
 *
 * Sits above the broker table because every number in that table is only
 * interpretable against this context — a betweenness of 0.4 means one thing in
 * a single connected component and another in a graph that is mostly isolated
 * pairs.
 */
export function NetworkSummaryPanel({
  summary,
}: {
  summary: NetworkSummary | undefined;
}) {
  // An API one version behind sends nodes and edges but no summary. The rest of
  // this app treats a cold or mismatched API as a normal state rather than a
  // crash, so the panel simply stands down and the graph above it still renders.
  if (!summary) return null;

  const fragmented = summary.component_count > 1;
  const clustered = summary.modularity >= MEANINGFUL_MODULARITY;

  return (
    <div className="panel p-4">
      <div className="scroll-x flex gap-3">
        <Stat
          label="Nodes"
          value={formatNumber(summary.node_count)}
          caption="in the displayed graph"
        />
        <Stat
          label="Ties"
          value={formatNumber(summary.edge_count)}
          caption="collaborating pairs"
        />
        <Stat
          label="Density"
          value={formatDecimal(summary.density, 3)}
          caption="of all possible pairs"
        />
        <Stat
          label="Components"
          value={formatNumber(summary.component_count)}
          caption={
            fragmented
              ? `largest holds ${formatNumber(summary.largest_component_size)}`
              : "single connected graph"
          }
        />
        <Stat
          label="Communities"
          value={formatNumber(summary.community_count)}
          caption={`modularity ${formatDecimal(summary.modularity, 3)}`}
        />
      </div>

      <p className="mt-3 border-t border-rule pt-3 text-body-sm text-ink-secondary">
        {clustered ? (
          <>
            Modularity of {formatDecimal(summary.modularity, 3)} is above the
            conventional 0.3 floor, so the {summary.community_count} communities
            reflect real clustering rather than an artefact of the algorithm.
          </>
        ) : (
          <>
            Modularity of {formatDecimal(summary.modularity, 3)} is below the
            conventional 0.3 floor. Treat the community split as weak — the
            graph does not divide cleanly, so read the groupings as suggestive
            rather than as findings.
          </>
        )}
      </p>
    </div>
  );
}

function entityHref(node: NetworkNode): string | null {
  if (node.type === "institution") return institutionHref(node.label);
  if (node.type === "researcher") return researcherHref(node.label);
  return null;
}

/**
 * The brokers: nodes carrying the most shortest paths between others.
 *
 * Deliberately a different ranking from "most publications". A prolific
 * institution that only ever co-publishes inside its own cluster brokers
 * nothing; a smaller one that is the sole link between two clusters brokers a
 * great deal, and only betweenness surfaces it.
 */
export function NetworkBrokersTable({
  nodes,
  limit = 10,
}: {
  nodes: NetworkNode[];
  limit?: number;
}) {
  const ranked = [...nodes]
    .sort(
      (a, b) =>
        b.betweenness_centrality - a.betweenness_centrality ||
        b.publication_count - a.publication_count ||
        a.label.localeCompare(b.label),
    )
    .slice(0, limit);

  // Every betweenness being zero means no node bridges anything — a complete
  // graph, or one made only of disconnected pairs. Ranking by it would then be
  // arbitrary, so the table says so rather than presenting a meaningless order.
  const anyBrokerage = ranked.some((node) => node.betweenness_centrality > 0);

  if (!anyBrokerage) {
    return (
      <p className="panel p-4 text-body-sm text-ink-secondary">
        No node sits on a shortest path between two others, so there are no
        brokers to rank. This happens when every displayed collaboration is an
        isolated pair, or when the graph is fully connected.
      </p>
    );
  }

  return (
    <div className="panel p-2">
      <DataTable<NetworkNode>
        rows={ranked}
        rowKey={(node) => node.id}
        caption="Ranked by betweenness — the share of shortest paths running through each node."
        columns={BROKER_COLUMNS}
      />
    </div>
  );
}

const BROKER_COLUMNS: Column<NetworkNode>[] = [
  {
    key: "label",
    header: "Node",
    render: (node) => {
      const href = entityHref(node);
      return href ? (
        <Link href={href} className="text-ink hover:text-primary hover:underline">
          {node.label}
        </Link>
      ) : (
        <span className="text-ink">{node.label}</span>
      );
    },
  },
  {
    key: "betweenness",
    header: "Betweenness",
    numeric: true,
    render: (node) => formatDecimal(node.betweenness_centrality, 3),
  },
  {
    key: "degree",
    header: "Partners",
    numeric: true,
    render: (node) => formatDecimal(node.degree_centrality, 3),
  },
  {
    key: "strength",
    header: "Co-publications",
    numeric: true,
    render: (node) => formatNumber(node.strength),
  },
  {
    key: "publications",
    header: "Publications",
    numeric: true,
    render: (node) => formatNumber(node.publication_count),
  },
  {
    key: "community",
    header: "Community",
    numeric: true,
    render: (node) => `#${node.community}`,
  },
];
