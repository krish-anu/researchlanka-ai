"use client";

import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/Button";

/** Soft-reloads the current route so server components refetch after an API failure. */
export function RetryButton({
  label = "Retry",
  variant = "primary",
}: {
  label?: string;
  variant?: "primary" | "secondary";
}) {
  const router = useRouter();

  return (
    <Button type="button" variant={variant} size="md" onClick={() => router.refresh()}>
      {label}
    </Button>
  );
}
