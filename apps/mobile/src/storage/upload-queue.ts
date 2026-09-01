/**
 * The offline capture queue (§60).
 *
 * A lekhpal photographing records in a village has no signal. The capture must
 * therefore succeed on the device and upload later, which means:
 *
 *   capture -> compress -> persist locally -> (network returns) -> upload
 *
 * Two rules this module exists to enforce:
 *
 *   1. **A queued item is never silently dropped.** A failed upload records
 *      why and how many attempts it has had; it does not vanish. An operator
 *      who photographed forty pages must be able to see all forty.
 *   2. **An item is only removed once the server has it.** Removal happens
 *      after a 201, never optimistically.
 *
 * The image itself stays on the filesystem at the URI the camera gave us;
 * AsyncStorage holds only the metadata. Base64-ing a dozen scans into a
 * key-value store would blow past its practical size limits.
 */

import AsyncStorage from "@react-native-async-storage/async-storage";

const KEY = "mrittika.upload-queue";

/** §60's status vocabulary, as the operator sees it. */
export type QueueStatus =
  | "QUEUED"
  | "WAITING_FOR_NETWORK"
  | "UPLOADING"
  | "UPLOADED"
  | "FAILED";

export type QueuedUpload = {
  /** Local id. The server's DOC- id lands in `documentId` after upload. */
  id: string;
  uri: string;
  fileName: string;
  documentType: string;
  villageId?: string;
  recordYear?: string;
  khasraNumber?: string;
  parcelId?: string;
  capturedAt: string;
  status: QueueStatus;
  attempts: number;
  lastError?: string;
  /** Set once the server has accepted it. */
  documentId?: string;
};

async function readAll(): Promise<QueuedUpload[]> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as QueuedUpload[]) : [];
  } catch {
    // A corrupt queue must not brick the app. Losing the index is bad; a
    // capture screen that cannot open is worse.
    return [];
  }
}

async function writeAll(items: QueuedUpload[]): Promise<void> {
  await AsyncStorage.setItem(KEY, JSON.stringify(items));
}

export const uploadQueue = {
  list: readAll,

  async add(
    item: Omit<QueuedUpload, "id" | "capturedAt" | "status" | "attempts">,
  ): Promise<QueuedUpload> {
    const queued: QueuedUpload = {
      ...item,
      id: `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      capturedAt: new Date().toISOString(),
      status: "QUEUED",
      attempts: 0,
    };
    const items = await readAll();
    await writeAll([queued, ...items]);
    return queued;
  },

  async update(id: string, patch: Partial<QueuedUpload>): Promise<void> {
    const items = await readAll();
    await writeAll(items.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  },

  async remove(id: string): Promise<void> {
    const items = await readAll();
    await writeAll(items.filter((item) => item.id !== id));
  },

  /** Items still owed to the server, oldest first so capture order is kept. */
  async pending(): Promise<QueuedUpload[]> {
    const items = await readAll();
    return items
      .filter((item) => item.status !== "UPLOADED")
      .map((item, index) => ({ item, index }))
      .sort(
        (a, b) =>
          a.item.capturedAt.localeCompare(b.item.capturedAt) || b.index - a.index,
      )
      .map(({ item }) => item);
  },

  async clearUploaded(): Promise<void> {
    const items = await readAll();
    await writeAll(items.filter((item) => item.status !== "UPLOADED"));
  },
};
