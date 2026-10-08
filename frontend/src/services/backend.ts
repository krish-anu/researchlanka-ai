/**
 * Server-side calls to the backend's protected endpoints.
 *
 * The backend admin token proves a request came from this server; the actor
 * headers say which signed-in account it is for. Neither ever reaches the
 * browser, so import this only from server components, server actions and
 * route handlers.
 */

import { buildQuery, type QueryParams } from "@/services/api";
import type { SessionUser } from "@/types/auth";

const REMOTE_API_BASE_URL =
  process.env.API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL;
const REMOTE_ADMIN_API_TOKEN = process.env.RESEARCHLANKA_ADMIN_API_TOKEN;

/** The DOI lookup and the AI relevance check can each take several seconds. */
const BACKEND_TIMEOUT_MS = 45_000;

export type BackendResult<T> =
  | { ok: true; data: T }
  | {
      ok: false;
      message: string;
      code: string;
      status: number | null;
      details?: Record<string, unknown>;
    };

export async function backendRequest<T = unknown>(
  path: string,
  options: {
    method?: "GET" | "POST";
    params?: QueryParams;
    body?: Record<string, unknown>;
    actor?: SessionUser | null;
  } = {},
): Promise<BackendResult<T>> {
  if (!REMOTE_API_BASE_URL) {
    return {
      ok: false,
      code: "api_not_configured",
      status: null,
      message: "API_BASE_URL is not configured for backend admin endpoints.",
    };
  }
  const url = `${REMOTE_API_BASE_URL.replace(/\/$/, "")}${path}${buildQuery(options.params ?? {})}`;
  try {
    const response = await fetch(url, {
      method: options.method ?? "GET",
      headers: backendHeaders(
        options.actor,
        options.body ? { "Content-Type": "application/json" } : {},
      ),
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: AbortSignal.timeout(BACKEND_TIMEOUT_MS),
      cache: "no-store",
    });
    const payload = (await response.json().catch(() => ({}))) as {
      data?: T;
      error?: { code?: string; message?: string; details?: Record<string, unknown> };
    };
    if (!response.ok) {
      return {
        ok: false,
        code: payload.error?.code ?? `http_${response.status}`,
        status: response.status,
        message: payload.error?.message ?? `Backend API returned HTTP ${response.status}.`,
        details: payload.error?.details,
      };
    }
    return { ok: true, data: payload.data as T };
  } catch (cause) {
    const isTimeout = cause instanceof DOMException && cause.name === "TimeoutError";
    return {
      ok: false,
      code: isTimeout ? "timeout" : "api_unreachable",
      status: null,
      message: isTimeout
        ? "The backend API took too long to respond. Try again."
        : `Could not reach the backend API at ${REMOTE_API_BASE_URL}.`,
    };
  }
}

function backendHeaders(
  actor: SessionUser | null | undefined,
  extra: Record<string, string> = {},
): Record<string, string> {
  return {
    Accept: "application/json",
    ...(REMOTE_ADMIN_API_TOKEN
      ? { "X-ResearchLanka-Admin-Token": REMOTE_ADMIN_API_TOKEN }
      : {}),
    ...(actor
      ? {
          "X-ResearchLanka-Actor-Id": actor.id,
          "X-ResearchLanka-Actor-Email": actor.email,
          "X-ResearchLanka-Actor-Name": actor.name,
        }
      : {}),
    ...extra,
  };
}

/** A failed backend call in the shape `ApiErrorPanel` renders. */
export function asApiFailure(result: Extract<BackendResult<unknown>, { ok: false }>) {
  return {
    code: result.code,
    message: result.message,
    status: result.status,
    details: result.details,
  };
}
