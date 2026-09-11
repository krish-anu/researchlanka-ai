/**
 * Saved libraries, record flags and the administrator audit log.
 *
 * All three are app-owned state with no home in the read-only analytics API,
 * so they live in `.data/` through `services/store/jsonFile`.
 */

import { newId, nowIso, readCollection, updateCollection } from "@/services/store/jsonFile";
import type {
  AuditAction,
  AuditEntry,
  FlagReason,
  FlagStatus,
  RecordFlag,
  SavedItem,
} from "@/services/workspace/types";
import type { SessionUser } from "@/types/auth";

const SAVED = "saved-items";
const FLAGS = "flags";
const AUDIT = "audit-log";

const NO_SAVED: SavedItem[] = [];
const NO_FLAGS: RecordFlag[] = [];
const NO_AUDIT: AuditEntry[] = [];

/* ------------------------------------------------------------ saved library */

export async function listSavedItems(userId: string): Promise<SavedItem[]> {
  const items = await readCollection<SavedItem[]>(SAVED, NO_SAVED);
  return items
    .filter((item) => item.user_id === userId)
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
}

export async function isSaved(
  userId: string,
  publicationKey: string,
): Promise<boolean> {
  const items = await readCollection<SavedItem[]>(SAVED, NO_SAVED);
  return items.some(
    (item) => item.user_id === userId && item.publication_key === publicationKey,
  );
}

/** Adds or removes in one call; returns the state the item ended in. */
export async function toggleSavedItem(input: {
  userId: string;
  publicationKey: string;
  title: string;
}): Promise<{ saved: boolean }> {
  return updateCollection<SavedItem[], { saved: boolean }>(
    SAVED,
    NO_SAVED,
    (items) => {
      const index = items.findIndex(
        (item) =>
          item.user_id === input.userId &&
          item.publication_key === input.publicationKey,
      );

      if (index !== -1) {
        const next = items.filter((_, position) => position !== index);
        return { next, result: { saved: false } };
      }

      const item: SavedItem = {
        id: newId("sav"),
        user_id: input.userId,
        publication_key: input.publicationKey,
        title: input.title,
        note: "",
        created_at: nowIso(),
      };
      return { next: [...items, item], result: { saved: true } };
    },
  );
}

export async function removeSavedItem(
  userId: string,
  itemId: string,
): Promise<void> {
  await updateCollection<SavedItem[], void>(SAVED, NO_SAVED, (items) => ({
    next: items.filter(
      (item) => !(item.id === itemId && item.user_id === userId),
    ),
    result: undefined,
  }));
}

/* -------------------------------------------------------------------- flags */

export async function listFlags(filter: { status?: FlagStatus } = {}): Promise<
  RecordFlag[]
> {
  const flags = await readCollection<RecordFlag[]>(FLAGS, NO_FLAGS);
  return flags
    .filter((flag) => !filter.status || flag.status === filter.status)
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
}

export async function listFlagsByUser(userId: string): Promise<RecordFlag[]> {
  const flags = await readCollection<RecordFlag[]>(FLAGS, NO_FLAGS);
  return flags
    .filter((flag) => flag.reported_by.id === userId)
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
}

export async function countOpenFlags(): Promise<number> {
  const flags = await readCollection<RecordFlag[]>(FLAGS, NO_FLAGS);
  return flags.filter((flag) => flag.status === "open").length;
}

export type CreateFlagResult =
  | { ok: true; flag: RecordFlag }
  | { ok: false; reason: "already_reported" };

/** One open flag per record per reporter — repeat reports add nothing to triage. */
export async function createFlag(input: {
  publicationKey: string;
  title: string;
  reason: FlagReason;
  detail: string;
  reporter: SessionUser;
}): Promise<CreateFlagResult> {
  return updateCollection<RecordFlag[], CreateFlagResult>(
    FLAGS,
    NO_FLAGS,
    (flags) => {
      const duplicate = flags.some(
        (flag) =>
          flag.publication_key === input.publicationKey &&
          flag.reported_by.id === input.reporter.id &&
          flag.status === "open",
      );
      if (duplicate) {
        return { next: flags, result: { ok: false, reason: "already_reported" } };
      }

      const flag: RecordFlag = {
        id: newId("flg"),
        publication_key: input.publicationKey,
        title: input.title,
        reason: input.reason,
        detail: input.detail.trim(),
        status: "open",
        reported_by: {
          id: input.reporter.id,
          name: input.reporter.name,
          email: input.reporter.email,
        },
        created_at: nowIso(),
        resolved_at: null,
        resolved_by: null,
        resolution_note: "",
      };
      return { next: [...flags, flag], result: { ok: true, flag } };
    },
  );
}

export async function resolveFlag(input: {
  flagId: string;
  status: Exclude<FlagStatus, "open">;
  note: string;
  actor: SessionUser;
}): Promise<RecordFlag | null> {
  const updated = await updateCollection<RecordFlag[], RecordFlag | null>(
    FLAGS,
    NO_FLAGS,
    (flags) => {
      const index = flags.findIndex((flag) => flag.id === input.flagId);
      if (index === -1) return { next: flags, result: null };

      const flag: RecordFlag = {
        ...flags[index],
        status: input.status,
        resolved_at: nowIso(),
        resolved_by: input.actor.name,
        resolution_note: input.note.trim(),
      };
      const next = [...flags];
      next[index] = flag;
      return { next, result: flag };
    },
  );

  if (updated) {
    await recordAudit({
      action: input.status === "accepted" ? "flag.accepted" : "flag.rejected",
      subject: updated.id,
      summary: `${input.status === "accepted" ? "Accepted" : "Rejected"} flag on “${updated.title}”`,
      actor: input.actor,
    });
  }
  return updated;
}

/* ---------------------------------------------------------------- audit log */

export async function recordAudit(input: {
  action: AuditAction;
  subject: string;
  summary: string;
  actor: SessionUser;
}): Promise<void> {
  await updateCollection<AuditEntry[], void>(AUDIT, NO_AUDIT, (entries) => {
    const entry: AuditEntry = {
      id: newId("aud"),
      action: input.action,
      subject: input.subject,
      summary: input.summary,
      actor: { id: input.actor.id, name: input.actor.name },
      created_at: nowIso(),
    };
    // Newest first, and capped — this is an activity feed, not a compliance log.
    return { next: [entry, ...entries].slice(0, 500), result: undefined };
  });
}

export async function listAudit(limit = 20): Promise<AuditEntry[]> {
  const entries = await readCollection<AuditEntry[]>(AUDIT, NO_AUDIT);
  return entries.slice(0, limit);
}
