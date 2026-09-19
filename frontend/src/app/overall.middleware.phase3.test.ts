/**
 * Middleware matcher contracts for protected routes.
 * @vitest-environment node
 */

import { describe, expect, it } from "vitest";

import { config } from "@/middleware";

describe("middleware matcher", () => {
  it("covers account and admin trees", () => {
    expect(config.matcher).toEqual(
      expect.arrayContaining(["/account/:path*", "/admin/:path*"]),
    );
  });
});
