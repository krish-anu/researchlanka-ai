"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";

import { Button } from "@/components/ui/Button";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])';

/**
 * Desktop: a narrow sticky column beside the results.
 * Narrow screens: a Refine button that opens a dialog. Focus stays in the
 * dialog until it closes, and returns to the button.
 */
export function FilterDrawer({
  children,
  activeCount = 0,
  label = "Refine publications",
  collapsible = false,
}: {
  children: ReactNode;
  activeCount?: number;
  /** Accessible name for the refine region. */
  label?: string;
  /** Desktop: a control that shrinks the column to a rail. */
  collapsible?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [narrow, setNarrow] = useState(false);
  const [desktop, setDesktop] = useState(false);
  const pathname = usePathname();
  const panelId = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const railRef = useRef<HTMLButtonElement>(null);
  const narrowButtonRef = useRef<HTMLButtonElement | HTMLAnchorElement>(null);
  const wasOpen = useRef(false);
  const lastNarrow = useRef(narrow);

  useEffect(() => {
    const media = window.matchMedia("(min-width: 1024px)");
    const update = () => setDesktop(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (wasOpen.current && !open) triggerRef.current?.focus();
    wasOpen.current = open;
  }, [open]);

  useEffect(() => {
    if (!collapsible || !desktop || lastNarrow.current === narrow) return;
    lastNarrow.current = narrow;
    if (narrow) railRef.current?.focus();
    else if (narrowButtonRef.current instanceof HTMLButtonElement) {
      narrowButtonRef.current.focus();
    }
  }, [narrow, desktop, collapsible]);

  useEffect(() => {
    if (!open || desktop) return;
    const panel = panelRef.current;
    if (!panel) return;

    const focusable = () =>
      [...panel.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
        (element) => element.tabIndex !== -1,
      );
    const items = focusable();
    const firstControl =
      items.find((element) => !element.hasAttribute("data-refine-close")) ?? items[0];
    firstControl?.focus();

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, desktop]);

  const triggerLabel = activeCount > 0 ? `Refine (${activeCount})` : "Refine";
  const collapsed = collapsible && narrow && desktop;

  return (
    <div className={collapsible ? (collapsed ? "lg:w-11" : "w-full lg:w-[13.25rem]") : undefined}>
      <div className="mb-3 lg:hidden">
        <Button
          ref={triggerRef}
          type="button"
          variant="secondary"
          size="sm"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? "Hide refine" : triggerLabel}
        </Button>
      </div>
      {open && !desktop ? (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-ink/40 lg:hidden"
          aria-label="Close refine"
          onClick={() => setOpen(false)}
        />
      ) : null}
      {collapsed ? (
        <button
          ref={railRef}
          type="button"
          aria-expanded={false}
          aria-label={activeCount > 0 ? `Show refine, ${activeCount} active` : "Show refine"}
          onClick={() => setNarrow(false)}
          className="hidden min-h-11 w-11 items-center justify-center rounded-md border border-rule bg-surface text-h3 text-ink lg:inline-flex"
        >
          <span aria-hidden>▾</span>
        </button>
      ) : (
      <div
        id={panelId}
        ref={panelRef}
        role={open && !desktop ? "dialog" : undefined}
        aria-modal={open && !desktop ? true : undefined}
        aria-label={label}
        className={
          open
            ? "fixed inset-y-0 left-0 z-50 w-[min(18rem,100%)] overflow-y-auto bg-surface p-4 shadow-lg lg:static lg:z-auto lg:block lg:w-auto lg:overflow-visible lg:bg-transparent lg:p-0 lg:shadow-none"
            : "hidden lg:block"
        }
      >
        <div className="mb-1 flex items-center justify-between gap-2">
          <h2 className="text-body-md font-medium text-ink">Refine</h2>
          <div className="flex items-center gap-1">
            {collapsible ? (
              <Button
                ref={narrowButtonRef}
                type="button"
                variant="ghost"
                size="sm"
                className="hidden lg:inline-flex"
                aria-expanded
                aria-label="Collapse refine"
                onClick={() => setNarrow(true)}
              >
                <span aria-hidden>▴</span>
              </Button>
            ) : null}
            {open ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="lg:hidden"
                data-refine-close=""
                onClick={() => setOpen(false)}
              >
                Close
              </Button>
            ) : null}
          </div>
        </div>
        {children}
      </div>
      )}
    </div>
  );
}
