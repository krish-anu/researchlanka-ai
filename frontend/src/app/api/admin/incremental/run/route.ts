import { NextResponse } from "next/server";

import { can } from "@/services/auth/permissions";
import { getViewer } from "@/services/auth/server";

export async function POST() {
  const viewer = await getViewer();
  if (!can(viewer.role, "admin.pipeline.view")) {
    return NextResponse.json(
      { error: { code: "forbidden", message: "Administrator access required." } },
      { status: 403 },
    );
  }

  return NextResponse.json(
    {
      error: {
        code: "not_configured",
        message:
          "The frontend run endpoint is not configured in this checkout. Run `make incremental-update` from the repository root or restore the backend admin job script.",
      },
    },
    { status: 501 },
  );
}
