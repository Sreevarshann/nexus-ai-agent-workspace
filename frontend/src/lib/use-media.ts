"use client";

import { useSyncExternalStore } from "react";

/** Subscribe to a CSS media query so only ONE layout tree renders (no duplicate streams or canvases). */
export function useMediaQuery(query: string, serverDefault = true): boolean {
  return useSyncExternalStore(
    (cb) => {
      const m = window.matchMedia(query);
      m.addEventListener("change", cb);
      return () => m.removeEventListener("change", cb);
    },
    () => window.matchMedia(query).matches,
    () => serverDefault,
  );
}
