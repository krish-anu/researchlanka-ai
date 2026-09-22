"use client";

import { useEffect, useState } from "react";

const STORAGE_KEY = "researchlanka-theme";
const CHANGE_EVENT = "researchlanka-theme-change";

function setTheme(dark: boolean) {
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  try { window.localStorage.setItem(STORAGE_KEY, dark ? "dark" : "light"); } catch { /* Browsing still works when storage is disabled. */ }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

/** The preview's light palette is the default; the existing dark palette stays available. */
export function ThemeToggle() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    let saved = false;
    try { saved = window.localStorage.getItem(STORAGE_KEY) === "dark"; } catch { /* Use the light default. */ }
    document.documentElement.dataset.theme = saved ? "dark" : "light";
    setDark(saved);
    window.dispatchEvent(new Event(CHANGE_EVENT));
    const sync = () => setDark(document.documentElement.dataset.theme === "dark");
    window.addEventListener(CHANGE_EVENT, sync);
    return () => window.removeEventListener(CHANGE_EVENT, sync);
  }, []);

  return <button
    type="button"
    className="theme-toggle"
    onClick={() => setTheme(!dark)}
    aria-label={dark ? "Use light theme" : "Use dark theme"}
    title={dark ? "Use light theme" : "Use dark theme"}
  >
    {dark ? <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42" /></svg>
      : <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M20.2 15.6A8.5 8.5 0 0 1 8.4 3.8 8.5 8.5 0 1 0 20.2 15.6Z" /></svg>}
  </button>;
}
