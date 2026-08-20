/**
 * Tiny JSON-file persistence for the state this app owns itself.
 *
 * The ResearchLanka API is a read-only analytics service: it has no accounts,
 * no write endpoints and no notion of a role (see `backend/src/api/routing/
 * routes.py`, which dispatches GET only). Accounts, saved libraries, record
 * flags and resolution decisions therefore have nowhere to live but here, and
 * they are kept in JSON files under `.data/` so a developer can run the whole
 * role system with nothing but `npm run dev`.
 *
 * This is deliberately the smallest thing that works, not a database. Writes
 * are serialised per file and written atomically via a temp file + rename, so
 * concurrent requests in one Node process cannot interleave a half-written
 * file. It does not survive a multi-instance deployment — swap this module for
 * a real store before running more than one server.
 */

import { randomUUID } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";

const DATA_DIR = process.env.APP_DATA_DIR
  ? path.resolve(process.env.APP_DATA_DIR)
  : path.join(process.cwd(), ".data");

/** One promise chain per file, so writes to the same file never interleave. */
const writeQueues = new Map<string, Promise<unknown>>();

function filePath(name: string): string {
  return path.join(DATA_DIR, `${name}.json`);
}

export async function readCollection<T>(name: string, fallback: T): Promise<T> {
  try {
    const raw = await readFile(filePath(name), "utf8");
    return JSON.parse(raw) as T;
  } catch (cause) {
    const code = (cause as NodeJS.ErrnoException | null)?.code;
    if (code === "ENOENT") return fallback;
    if (cause instanceof SyntaxError) {
      throw new Error(
        `${filePath(name)} is not valid JSON. Fix or delete the file and retry.`,
      );
    }
    throw cause;
  }
}

async function writeCollection<T>(name: string, value: T): Promise<void> {
  await mkdir(DATA_DIR, { recursive: true });
  const target = filePath(name);
  const temp = `${target}.${randomUUID()}.tmp`;
  await writeFile(temp, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  await rename(temp, target);
}

/**
 * Read-modify-write one collection under the file's lock.
 *
 * `mutate` receives the current contents and returns the next ones plus
 * whatever the caller needs back (the created row, a success flag, …).
 */
export async function updateCollection<T, R>(
  name: string,
  fallback: T,
  mutate: (current: T) => Promise<{ next: T; result: R }> | { next: T; result: R },
): Promise<R> {
  const previous = writeQueues.get(name) ?? Promise.resolve();

  const run = previous.then(async () => {
    const current = await readCollection<T>(name, fallback);
    const { next, result } = await mutate(current);
    await writeCollection(name, next);
    return result;
  });

  // Keep the chain alive even when this write rejects, or one failure would
  // poison every later write to the same file.
  writeQueues.set(
    name,
    run.catch(() => undefined),
  );
  return run;
}

export function newId(prefix: string): string {
  return `${prefix}_${randomUUID().replace(/-/g, "").slice(0, 16)}`;
}

export function nowIso(): string {
  return new Date().toISOString();
}
