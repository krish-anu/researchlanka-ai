/**
 * Overall frontend application contracts used by Phase 3.
 * @vitest-environment node
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { buildQuery, isNotFound, valueOr, type ApiResult } from "@/services/api";
import { can } from "@/services/auth/permissions";
import { sessionCookieOptions } from "@/services/auth/session";

describe("buildQuery", () => {
  it("encodes adversarial SQL-like search text without dropping the value", () => {
    const qs = buildQuery({ q: "' OR 1=1 --" });
    expect(qs).toContain("q=");
    expect(decodeURIComponent(qs)).toContain("' OR 1=1 --");
  });

  it("omits empty and null params", () => {
    expect(buildQuery({ q: "", year_min: null, field: undefined })).toBe("");
  });

  it("repeats array filters", () => {
    const qs = buildQuery({ institution: ["UOC", "UOP"] });
    expect(qs).toContain("institution=UOC");
    expect(qs).toContain("institution=UOP");
  });
});

describe("ApiResult helpers", () => {
  it("valueOr falls back on failure so pages can render panels", () => {
    const failed: ApiResult<number> = {
      ok: false,
      error: { code: "unreachable", message: "down", status: null },
    };
    expect(valueOr(failed, 0)).toBe(0);
  });

  it("isNotFound distinguishes missing records from outages", () => {
    expect(
      isNotFound({
        ok: false,
        error: { code: "not_found", message: "gone", status: 404 },
      }),
    ).toBe(true);
    expect(
      isNotFound({
        ok: false,
        error: { code: "unreachable", message: "down", status: null },
      }),
    ).toBe(false);
  });
});

describe("auth gates", () => {
  it("guest cannot run admin pipeline", () => {
    expect(can("guest", "admin.pipeline.run")).toBe(false);
    expect(can("user", "admin.pipeline.run")).toBe(false);
    expect(can("admin", "admin.pipeline.run")).toBe(true);
  });
});

describe("sessionCookieOptions", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("always sets HttpOnly and SameSite=lax", () => {
    const options = sessionCookieOptions(3600);
    expect(options.httpOnly).toBe(true);
    expect(options.sameSite).toBe("lax");
    expect(options.path).toBe("/");
  });

  it("honours AUTH_COOKIE_SECURE=true for HTTPS deployments", () => {
    vi.stubEnv("AUTH_COOKIE_SECURE", "true");
    expect(sessionCookieOptions(60).secure).toBe(true);
  });

  it("allows AUTH_COOKIE_SECURE=false for plain-HTTP EC2 smoke deploys", () => {
    vi.stubEnv("AUTH_COOKIE_SECURE", "false");
    expect(sessionCookieOptions(60).secure).toBe(false);
  });
});
