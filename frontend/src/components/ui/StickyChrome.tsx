"use client";

import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";

/**
 * Adds `is-stuck` when the sticky chrome is pinned, for a light elevation shadow.
 * Uses a 1px sentinel above the sticky element (IntersectionObserver).
 */
export function StickyChrome({
  children,
  className = "",
  style,
  stickyClassName = "",
}: {
  children: ReactNode;
  className?: string;
  stickyClassName?: string;
  style?: CSSProperties;
}) {
  const sentinelRef = useRef<HTMLDivElement>(null);
  const [stuck, setStuck] = useState(false);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      ([entry]) => setStuck(!entry.isIntersecting),
      { threshold: [1] },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, []);

  return (
    <div className={className}>
      <div ref={sentinelRef} className="sticky-chrome-sentinel" aria-hidden />
      <div
        className={`sticky-chrome ${stuck ? "is-stuck" : ""} ${stickyClassName}`.trim()}
        style={style}
      >
        {children}
      </div>
    </div>
  );
}
