"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { signOut } from "@/app/actions/auth";
import { RoleBadge } from "@/components/auth/RoleBadge";
import { ROLE_CAPABILITY_SUMMARY } from "@/services/auth/permissions";
import type { Viewer } from "@/types/auth";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return parts.map((part) => part[0]?.toUpperCase() ?? "").join("") || "?";
}

/**
 * The signed-in identity control in the top bar, and the sign-in call to action
 * that replaces it for visitors.
 *
 * A visitor gets a plain link rather than a disabled-looking menu: the point of
 * the control for someone unsigned is the way in, not a preview of what they
 * cannot reach.
 */
export function AccountMenu({ viewer }: { viewer: Viewer }) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    function onPointerDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  if (!viewer.user) {
    return (
      <div className="flex items-center gap-2">
        <Link
          href="/login"
          className="rounded border border-rule px-3 py-1.5 text-body-sm text-ink-secondary hover:border-primary hover:text-primary"
        >
          Sign in
        </Link>
        <Link
          href="/register"
          className="hidden rounded bg-primary px-3 py-1.5 text-body-sm font-semibold text-on-primary hover:bg-primary-hover sm:inline-block"
        >
          Create account
        </Link>
      </div>
    );
  }

  const { user, role } = viewer;

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex items-center gap-2 rounded border border-rule px-2 py-1.5 text-body-sm text-ink-secondary hover:border-primary hover:text-primary"
      >
        <span
          aria-hidden
          className="flex h-7 w-7 items-center justify-center rounded bg-primary-container text-label font-bold text-on-primary"
        >
          {initials(user.name)}
        </span>
        <span className="hidden max-w-[10rem] truncate sm:inline">
          {user.name}
        </span>
        <span aria-hidden className="text-muted">
          ▾
        </span>
        <span className="sr-only">Account menu</span>
      </button>

      {open ? (
        <div
          role="menu"
          className="overlay absolute right-0 z-50 mt-2 w-72 p-4 text-left"
        >
          <p className="truncate font-display text-body-md font-semibold text-ink">
            {user.name}
          </p>
          <p className="data-mono mt-1 truncate text-muted">{user.email}</p>
          <RoleBadge role={role} className="mt-3" />

          <ul className="mt-3 flex flex-col gap-1 border-t border-rule pt-3 text-body-sm text-ink-secondary">
            {ROLE_CAPABILITY_SUMMARY[role].map((line) => (
              <li key={line} className="flex gap-2">
                <span aria-hidden className="text-muted">
                  ·
                </span>
                {line}
              </li>
            ))}
          </ul>

          <div className="mt-3 flex flex-col gap-1 border-t border-rule pt-3">
            <Link
              href="/account"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="rounded px-2 py-1.5 text-body-sm text-ink-secondary hover:bg-wash hover:text-ink"
            >
              Your account
            </Link>
            <Link
              href="/account/saved"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="rounded px-2 py-1.5 text-body-sm text-ink-secondary hover:bg-wash hover:text-ink"
            >
              Saved library
            </Link>
            {role === "admin" ? (
              <Link
                href="/admin"
                role="menuitem"
                onClick={() => setOpen(false)}
                className="rounded px-2 py-1.5 text-body-sm font-semibold text-primary hover:bg-wash"
              >
                Administration
              </Link>
            ) : null}
          </div>

          <form action={signOut} className="mt-3 border-t border-rule pt-3">
            <button
              type="submit"
              role="menuitem"
              className="w-full rounded border border-rule px-2 py-1.5 text-body-sm text-ink-secondary hover:border-primary hover:text-primary"
            >
              Sign out
            </button>
          </form>
        </div>
      ) : null}
    </div>
  );
}
