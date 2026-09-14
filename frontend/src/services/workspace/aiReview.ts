import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import { nowIso, readCollection, updateCollection } from "@/services/store/jsonFile";
import { recordAudit } from "@/services/workspace/store";
import type {
  AIReviewCandidate,
  AIReviewDecision,
  AIReviewDecisionLabel,
} from "@/services/workspace/types";
import type { Pagination } from "@/types/api";
import type { SessionUser } from "@/types/auth";

const DECISIONS = "ai-review-decisions";
const EMPTY_DECISIONS: AIReviewDecision[] = [];

const REPO_ROOT = path.resolve(process.cwd(), "..");
const PREDICTIONS_PATH = path.join(
  REPO_ROOT,
  "backend",
  "data",
  "processed",
  "ai",
  "ai_relevance_best_model_rest_predictions.csv",
);
const RESOLVED_PREDICTIONS_PATH = path.join(
  REPO_ROOT,
  "backend",
  "data",
  "processed",
  "ai",
  "ai_relevance_best_model_rest_predictions_resolved.csv",
);
const DECISIONS_CSV_PATH = path.join(
  REPO_ROOT,
  "backend",
  "data",
  "processed",
  "ai",
  "ai_relevance_review_decisions.csv",
);

type CsvRow = Record<string, string>;

export interface AIReviewPage {
  data: AIReviewCandidate[];
  pagination: Pagination;
  pending: number;
  decided: number;
}

function parseCsvLine(line: string): string[] {
  const row: string[] = [];
  let field: string[] = [];
  let inQuotes = false;

  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    const next = line[index + 1];

    if (inQuotes) {
      if (char === '"' && next === '"') {
        field.push('"');
        index += 1;
      } else if (char === '"') {
        inQuotes = false;
      } else {
        field.push(char);
      }
      continue;
    }

    if (char === '"') {
      inQuotes = true;
    } else if (char === ",") {
      row.push(field.join(""));
      field = [];
    } else if (char !== "\r") {
      field.push(char);
    }
  }

  row.push(field.join(""));
  return row;
}

function rowFromValues(header: string[], values: string[]): CsvRow {
  return Object.fromEntries(
    header.map((column, index) => [column, values[index] ?? ""]),
  );
}

function csvValue(value: string): string {
  if (/[",\n\r]/.test(value)) return `"${value.replaceAll('"', '""')}"`;
  return value;
}

function writeCsv(rows: CsvRow[], columns: string[]): string {
  return [
    columns.map(csvValue).join(","),
    ...rows.map((row) => columns.map((column) => csvValue(row[column] ?? "")).join(",")),
  ].join("\n") + "\n";
}

function numberOrNull(value: string): number | null {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function candidateId(row: CsvRow): string {
  return row.publication_id || row.source_row || row.openalex_id || row.doi;
}

async function predictionRows(): Promise<CsvRow[]> {
  const text = await readFile(PREDICTIONS_PATH, "utf8");
  const [headerLine = "", ...recordLines] = text.split(/\r?\n/);
  const header = parseCsvLine(headerLine);
  const labelIndex = header.indexOf("ai_final_label");
  return recordLines
    .filter((line) => line.trim() !== "")
    .map((line) => parseCsvLine(line))
    .filter((values) => labelIndex === -1 || values[labelIndex] === "REVIEW")
    .map((values) => rowFromValues(header, values));
}

async function allAIReviewCandidates(): Promise<AIReviewCandidate[]> {
  const [rows, decisions] = await Promise.all([
    predictionRows(),
    readCollection<AIReviewDecision[]>(DECISIONS, EMPTY_DECISIONS),
  ]);
  const decisionsById = new Map(decisions.map((decision) => [decision.id, decision]));

  return rows
    .map((row) => {
      const id = candidateId(row);
      const decision = decisionsById.get(id) ?? null;
      return {
        id,
        publication_id: row.publication_id,
        source_row: row.source_row,
        status: decision ? "decided" : "pending",
        final_label: row.ai_final_label,
        raw_label: row.ai_model_raw_label,
        confidence: numberOrNull(row.ai_model_confidence),
        margin: numberOrNull(row.ai_model_margin),
        review_threshold: numberOrNull(row.review_threshold),
        selected_model: row.selected_model,
        title: row.title,
        doi: row.doi || null,
        openalex_id: row.openalex_id || null,
        publication_date: row.publication_date || null,
        source_dataset: row.source_dataset,
        source_record_id: row.source_record_id,
        primary_topic: row.primary_topic || null,
        primary_subfield: row.primary_subfield || null,
        primary_field: row.primary_field || null,
        primary_domain: row.primary_domain || null,
        text: row.text,
        decision,
      } satisfies AIReviewCandidate;
    })
    .sort((a, b) => {
      if (a.status !== b.status) return a.status === "pending" ? -1 : 1;
      return (a.confidence ?? 0) - (b.confidence ?? 0);
    });
}

export async function listAIReviewCandidates({
  page = 1,
  pageSize = 25,
}: {
  page?: number;
  pageSize?: number;
} = {}): Promise<AIReviewPage> {
  const safePageSize = Math.min(Math.max(Math.trunc(pageSize), 1), 100);
  const candidates = await allAIReviewCandidates();
  const total = candidates.length;
  const totalPages = Math.max(Math.ceil(total / safePageSize), 1);
  const safePage = Math.min(Math.max(Math.trunc(page), 1), totalPages);
  const start = (safePage - 1) * safePageSize;

  return {
    data: candidates.slice(start, start + safePageSize),
    pagination: {
      page: safePage,
      page_size: safePageSize,
      total,
      total_pages: totalPages,
    },
    pending: candidates.filter((candidate) => candidate.status === "pending").length,
    decided: candidates.filter((candidate) => candidate.status === "decided").length,
  };
}

export async function countPendingAIReviewCandidates(): Promise<number> {
  const candidates = await allAIReviewCandidates();
  return candidates.filter((candidate) => candidate.status === "pending").length;
}

export async function decideAIReview(input: {
  candidateId: string;
  decision: AIReviewDecisionLabel;
  note: string;
  actor: SessionUser;
}): Promise<AIReviewDecision | null> {
  const candidates = await allAIReviewCandidates();
  const candidate = candidates.find((item) => item.id === input.candidateId);
  if (!candidate) return null;

  const decided = await updateCollection<
    AIReviewDecision[],
    AIReviewDecision
  >(DECISIONS, EMPTY_DECISIONS, (decisions) => {
    const decision: AIReviewDecision = {
      id: candidate.id,
      publication_id: candidate.publication_id,
      source_row: candidate.source_row,
      decision: input.decision,
      note: input.note.trim(),
      decided_at: nowIso(),
      decided_by: input.actor.name,
    };
    const next = [
      decision,
      ...decisions.filter((item) => item.id !== input.candidateId),
    ];
    return { next, result: decision };
  });

  await materializeResolvedPredictions();
  await recordAudit({
    action: input.decision === "AI" ? "ai_review.ai" : "ai_review.non_ai",
    subject: decided.id,
    summary: `Marked AI review item as ${input.decision}: “${candidate.title || candidate.publication_id}”`,
    actor: input.actor,
  });
  return decided;
}

export async function materializeResolvedPredictions(): Promise<void> {
  const [text, decisions] = await Promise.all([
    readFile(PREDICTIONS_PATH, "utf8"),
    readCollection<AIReviewDecision[]>(DECISIONS, EMPTY_DECISIONS),
  ]);
  const decisionsById = new Map(decisions.map((decision) => [decision.id, decision]));

  const [headerLine = "", ...recordLines] = text.split(/\r?\n/);
  const baseColumns = parseCsvLine(headerLine);
  const columns = [
    ...baseColumns,
    "human_review_label",
    "human_review_note",
    "human_reviewed_by",
    "human_reviewed_at",
  ];
  const labelIndex = baseColumns.indexOf("ai_final_label");
  const resolved = recordLines
    .filter((line) => line.trim() !== "")
    .map((line) => {
      const values = parseCsvLine(line);
      const row = rowFromValues(baseColumns, values);
      const decision = decisionsById.get(candidateId(row));
      if (decision && labelIndex !== -1) values[labelIndex] = decision.decision;
      const reviewFields = decision
        ? [
            decision.decision,
            decision.note,
            decision.decided_by,
            decision.decided_at,
          ]
        : ["", "", "", ""];
      return [...values, ...reviewFields];
    });

  await mkdir(path.dirname(RESOLVED_PREDICTIONS_PATH), { recursive: true });
  await writeFile(
    RESOLVED_PREDICTIONS_PATH,
    [
      columns.map(csvValue).join(","),
      ...resolved.map((values) => values.map(csvValue).join(",")),
    ].join("\n") + "\n",
    "utf8",
  );
  await writeFile(
    DECISIONS_CSV_PATH,
    writeCsv(
      decisions.map((decision) => ({ ...decision })),
      ["id", "publication_id", "source_row", "decision", "note", "decided_at", "decided_by"],
    ),
    "utf8",
  );
}
