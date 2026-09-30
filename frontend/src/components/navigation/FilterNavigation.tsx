"use client";

import {
  createContext,
  useCallback,
  useContext,
  useTransition,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";

type FilterNavigationValue = {
  isPending: boolean;
  navigate: (href: string) => void;
};

const FilterNavigationContext = createContext<FilterNavigationValue | null>(
  null,
);

/** Build a GET href from a form without a full document navigation. */
export function formActionHref(form: HTMLFormElement, action: string): string {
  const data = new FormData(form);
  const params = new URLSearchParams();
  for (const [key, value] of data.entries()) {
    if (typeof value !== "string" || value === "") continue;
    params.append(key, value);
  }
  const qs = params.toString();
  return qs ? `${action}?${qs}` : action;
}

/**
 * Soft filter navigation: keeps the current results on screen while the next
 * RSC payload loads, and exposes `isPending` for a subtle progress cue.
 */
export function FilterNavigationProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  const navigate = useCallback(
    (href: string) => {
      startTransition(() => {
        router.push(href, { scroll: false });
      });
    },
    [router],
  );

  return (
    <FilterNavigationContext.Provider value={{ isPending, navigate }}>
      <div
        className={isPending ? "filter-pending" : undefined}
        aria-busy={isPending || undefined}
      >
        {isPending ? (
          <div className="filter-pending-bar" role="status" aria-live="polite">
            Updating results
          </div>
        ) : null}
        <div className={isPending ? "filter-pending-content" : undefined}>
          {children}
        </div>
      </div>
    </FilterNavigationContext.Provider>
  );
}

export function useFilterNavigation(): FilterNavigationValue {
  const value = useContext(FilterNavigationContext);
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  const fallbackNavigate = useCallback(
    (href: string) => {
      startTransition(() => {
        router.push(href, { scroll: false });
      });
    },
    [router],
  );

  if (value) return value;
  return { isPending, navigate: fallbackNavigate };
}

/** GET form that soft-navigates so skeletons do not wipe visible results. */
export function SoftNavForm({
  action,
  className,
  children,
}: {
  action: string;
  className?: string;
  children: ReactNode;
}) {
  const { navigate, isPending } = useFilterNavigation();

  return (
    <form
      method="get"
      action={action}
      className={className}
      aria-busy={isPending || undefined}
      onSubmit={(event) => {
        event.preventDefault();
        navigate(formActionHref(event.currentTarget, action));
      }}
    >
      {children}
    </form>
  );
}

/** Link that soft-navigates (filter chips, resets). */
export function SoftNavLink({
  href,
  className,
  children,
}: {
  href: string;
  className?: string;
  children: ReactNode;
}) {
  const { navigate, isPending } = useFilterNavigation();

  return (
    <a
      href={href}
      className={className}
      aria-busy={isPending || undefined}
      onClick={(event) => {
        if (
          event.defaultPrevented ||
          event.button !== 0 ||
          event.metaKey ||
          event.ctrlKey ||
          event.shiftKey ||
          event.altKey
        ) {
          return;
        }
        event.preventDefault();
        navigate(href);
      }}
    >
      {children}
    </a>
  );
}
