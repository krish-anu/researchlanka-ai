"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

/** Move keyboard focus to the main landmark after a client navigation. */
export function RouteFocus() {
  const pathname = usePathname();
  const first = useRef(true);

  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    const main = document.getElementById("main");
    if (!(main instanceof HTMLElement)) return;
    main.focus({ preventScroll: true });
  }, [pathname]);

  return null;
}
