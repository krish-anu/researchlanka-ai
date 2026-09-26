"use client";

import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/Button";

/** Soft-reloads the current route so server components refetch after an API failure. */
export function RetryButton({ label = "Retry" }: { label?: string }) {
  const router = useRouter();

  return (
    <Button type="button" variant="primary" size="sm" onClick={() => router.refresh()}>
      {label}
    </Button>
  );
}
