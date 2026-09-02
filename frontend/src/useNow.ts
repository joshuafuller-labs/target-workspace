// Shared 1 Hz clock. All `useNow()` subscribers re-render together,
// driven by a single setInterval — 50 cards on screen don't spawn 50
// timers. Pattern: external mutable store + useSyncExternalStore.

import { useSyncExternalStore } from "react";

let current = Date.now();
const subscribers = new Set<() => void>();
let intervalId: ReturnType<typeof setInterval> | null = null;

function ensureRunning(): void {
  if (intervalId !== null) return;
  // Aligning the first tick to the next whole second keeps card
  // counters stepping in sync; otherwise the first tick lands at a
  // random sub-second offset and the visual is slightly jittery.
  const ms = 1000 - (Date.now() % 1000);
  intervalId = setTimeout(() => {
    intervalId = setInterval(() => {
      current = Date.now();
      for (const cb of subscribers) cb();
    }, 1000);
    current = Date.now();
    for (const cb of subscribers) cb();
  }, ms);
}

function subscribe(cb: () => void): () => void {
  ensureRunning();
  subscribers.add(cb);
  return () => {
    subscribers.delete(cb);
    if (subscribers.size === 0 && intervalId !== null) {
      clearInterval(intervalId);
      clearTimeout(intervalId);
      intervalId = null;
    }
  };
}

function getSnapshot(): number {
  return current;
}

/** Returns the current Date.now()-equivalent, updated each second. */
export function useNow(): number {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}
