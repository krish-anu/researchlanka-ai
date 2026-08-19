/**
 * The entity-resolution queue.
 *
 * The deduplication model lives in the pipeline (`backend/research_analytics/
 * deduplication.py` and `duplicate_analysis.py`), but the read-only API does
 * not expose its candidate pairs yet — there is no `/analytics/duplicates`
 * route in `src/api/routing/routes.py`. Until one exists, the queue is seeded
 * from the fixture below so the review screen, its decisions and its audit
 * trail are all real and exercisable; only the *source* of the candidates is
 * standing in. `SEEDED_FROM_FIXTURE` drives the banner that says so on screen,
 * so nobody mistakes fixture pairs for pipeline output.
 *
 * Swapping in the real feed means replacing `seedCandidates()` with a fetch and
 * dropping the flag; the decision path below is unchanged.
 */

import { newId, nowIso, readCollection, updateCollection } from "@/services/store/jsonFile";
import { recordAudit } from "@/services/workspace/store";
import type { ResolutionCandidate } from "@/services/workspace/types";
import type { SessionUser } from "@/types/auth";

const COLLECTION = "resolution-queue";
const EMPTY: ResolutionCandidate[] = [];

/** `true` while the queue is fixture-backed rather than pipeline-fed. */
export const SEEDED_FROM_FIXTURE = true;

const FIXTURE: Omit<ResolutionCandidate, "id" | "created_at">[] = [
  {
    score: 0.96,
    status: "pending",
    decided_at: null,
    decided_by: null,
    left: {
      source: "openalex",
      title: "Climate change impacts on agriculture in dry zone Sri Lanka",
      doi: "10.1016/j.envdev.2023.100842",
      year: 2023,
      authors: ["W. M. Wijesinghe", "A. Perera"],
    },
    right: {
      source: "crossref",
      title: "Impacts of climate change on dry zone agriculture in Sri Lanka",
      doi: "10.1016/j.envdev.2023.100842",
      year: 2023,
      authors: ["Wijesinghe, W.M.", "Perera, A."],
    },
  },
  {
    score: 0.88,
    status: "pending",
    decided_at: null,
    decided_by: null,
    left: {
      source: "sljol",
      title: "Prevalence of dengue vectors in the Colombo district",
      doi: null,
      year: 2021,
      authors: ["S. Fernando", "N. Jayawardena"],
    },
    right: {
      source: "openalex",
      title: "Prevalence of dengue vectors in Colombo District, Sri Lanka",
      doi: "10.4038/sljid.v11i2.8394",
      year: 2021,
      authors: ["Sunil Fernando", "Nadeeka Jayawardena"],
    },
  },
  {
    score: 0.71,
    status: "pending",
    decided_at: null,
    decided_by: null,
    left: {
      source: "repository",
      title: "Machine learning approaches for paddy yield forecasting",
      doi: null,
      year: 2022,
      authors: ["K. Bandara"],
    },
    right: {
      source: "crossref",
      title: "Machine learning for rice yield prediction in Sri Lanka",
      doi: "10.1109/ICTer55305.2022.9924787",
      year: 2022,
      authors: ["Kasun Bandara", "R. Silva"],
    },
  },
];

async function seedCandidates(): Promise<void> {
  const existing = await readCollection<ResolutionCandidate[]>(COLLECTION, EMPTY);
  if (existing.length > 0) return;

  await updateCollection<ResolutionCandidate[], void>(
    COLLECTION,
    EMPTY,
    (candidates) => {
      if (candidates.length > 0) return { next: candidates, result: undefined };
      const seeded = FIXTURE.map((candidate) => ({
        ...candidate,
        id: newId("res"),
        created_at: nowIso(),
      }));
      return { next: seeded, result: undefined };
    },
  );
}

export async function listCandidates(): Promise<ResolutionCandidate[]> {
  await seedCandidates();
  const candidates = await readCollection<ResolutionCandidate[]>(COLLECTION, EMPTY);
  // Pending first, then by descending model confidence: the queue should open
  // on the pairs a reviewer can clear fastest.
  return [...candidates].sort((a, b) => {
    if (a.status !== b.status) return a.status === "pending" ? -1 : 1;
    return b.score - a.score;
  });
}

export async function countPendingCandidates(): Promise<number> {
  const candidates = await listCandidates();
  return candidates.filter((candidate) => candidate.status === "pending").length;
}

export async function decideCandidate(input: {
  candidateId: string;
  decision: "merged" | "rejected";
  actor: SessionUser;
}): Promise<ResolutionCandidate | null> {
  const decided = await updateCollection<
    ResolutionCandidate[],
    ResolutionCandidate | null
  >(COLLECTION, EMPTY, (candidates) => {
    const index = candidates.findIndex(
      (candidate) => candidate.id === input.candidateId,
    );
    if (index === -1) return { next: candidates, result: null };

    const candidate: ResolutionCandidate = {
      ...candidates[index],
      status: input.decision,
      decided_at: nowIso(),
      decided_by: input.actor.name,
    };
    const next = [...candidates];
    next[index] = candidate;
    return { next, result: candidate };
  });

  if (decided) {
    await recordAudit({
      action:
        input.decision === "merged"
          ? "resolution.merged"
          : "resolution.rejected",
      subject: decided.id,
      summary: `${input.decision === "merged" ? "Merged" : "Kept separate"}: “${decided.left.title}”`,
      actor: input.actor,
    });
  }
  return decided;
}
