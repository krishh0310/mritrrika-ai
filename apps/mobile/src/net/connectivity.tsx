/**
 * Connectivity, the pending queue, and the drain that connects them (§60).
 *
 * §60's promise is that a capture made with no signal uploads itself once
 * signal returns, without the operator remembering to come back and press
 * anything. That needs someone watching the network, and it needs the answer
 * shared: the capture screen, the queue screen and the header badge must agree
 * on how many uploads are outstanding, or the operator cannot trust any of
 * them.
 *
 * Two deliberate choices:
 *
 *   * **Polling, not a socket.** `isOnline` is a cheap local radio check.
 *     Polling every few seconds costs nothing and cannot get stuck in a
 *     "connected" state that a listener missed -- which on a field phone
 *     drifting between towers is the failure that actually happens.
 *
 *   * **One drain at a time.** `draining` guards re-entry, because the poll,
 *     the app coming to the foreground and the operator's own tap can all fire
 *     within the same second, and three concurrent drains would upload the
 *     same photograph three times.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { AppState } from "react-native";

import { drainQueue, isOnline } from "../api/sync";
import { uploadQueue, type QueuedUpload } from "../storage/upload-queue";

const POLL_MS = 5_000;

type Connectivity = {
  online: boolean;
  /** Every item the queue knows about, newest capture first. */
  items: QueuedUpload[];
  /** Items the server does not have yet. */
  pending: QueuedUpload[];
  syncing: boolean;
  /** Re-read the queue from storage, e.g. after enqueueing a capture. */
  refresh: () => Promise<void>;
  /** Drain now, on the operator's say-so. Safe to call while offline. */
  syncNow: () => Promise<void>;
};

const ConnectivityContext = createContext<Connectivity | null>(null);

export function ConnectivityProvider({ children }: { children: ReactNode }) {
  const [online, setOnline] = useState(true);
  const [items, setItems] = useState<QueuedUpload[]>([]);
  const [syncing, setSyncing] = useState(false);

  // Refs, not state: these are read inside the poll callback, which must not
  // be torn down and rebuilt every time a value changes.
  const draining = useRef(false);
  const wasOnline = useRef(true);

  const refresh = useCallback(async () => {
    setItems(await uploadQueue.list());
  }, []);

  const drain = useCallback(async () => {
    if (draining.current) return;
    draining.current = true;
    setSyncing(true);
    try {
      await drainQueue();
    } finally {
      draining.current = false;
      setSyncing(false);
      await refresh();
    }
  }, [refresh]);

  const syncNow = useCallback(async () => {
    // No online check here: drainQueue does it, and marks everything
    // WAITING_FOR_NETWORK so the operator sees why nothing moved.
    await drain();
  }, [drain]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    let cancelled = false;

    async function check() {
      const up = await isOnline();
      if (cancelled) return;
      setOnline(up);

      // Only on the offline -> online edge. Draining on every poll while
      // online would retry a genuinely failed upload in a tight loop.
      const returned = up && !wasOnline.current;
      wasOnline.current = up;
      if (!returned) return;

      if ((await uploadQueue.pending()).length > 0) await drain();
    }

    void check();
    const timer = setInterval(() => void check(), POLL_MS);

    // Coming back to the foreground is the other moment worth checking: the
    // phone may have found signal while the screen was off.
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") void check();
    });

    return () => {
      cancelled = true;
      clearInterval(timer);
      subscription.remove();
    };
  }, [drain]);

  const value = useMemo<Connectivity>(
    () => ({
      online,
      items,
      pending: items.filter((item) => item.status !== "UPLOADED"),
      syncing,
      refresh,
      syncNow,
    }),
    [online, items, syncing, refresh, syncNow],
  );

  return (
    <ConnectivityContext.Provider value={value}>{children}</ConnectivityContext.Provider>
  );
}

export function useConnectivity(): Connectivity {
  const context = useContext(ConnectivityContext);
  if (!context) {
    throw new Error("useConnectivity must be used inside <ConnectivityProvider>");
  }
  return context;
}
