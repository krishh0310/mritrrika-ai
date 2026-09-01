/**
 * Draining the offline queue (§60).
 *
 * Runs when the app regains connectivity and when the operator asks. Uploads
 * strictly one at a time: a field phone on a 2G tether that fires twelve
 * multipart requests at once finishes none of them.
 *
 * A failure is recorded on the item and the drain stops. Continuing past a
 * failure would burn the operator's data allowance retrying a queue whose
 * first item will fail the same way, and it would bury the cause.
 */

import * as Network from "expo-network";

import { uploadQueue, type QueuedUpload } from "../storage/upload-queue";
import { ApiError, api } from "./client";

export type DrainResult = {
  uploaded: number;
  failed: number;
  /** True when the drain stopped because there is no usable connection. */
  offline: boolean;
};

export async function isOnline(): Promise<boolean> {
  try {
    const state = await Network.getNetworkStateAsync();
    return Boolean(state.isConnected && state.isInternetReachable !== false);
  } catch {
    // If we cannot tell, assume we are online and let the request decide.
    return true;
  }
}

async function uploadOne(item: QueuedUpload): Promise<string> {
  const form = new FormData();

  // React Native's FormData takes this shape for a file on disk; the browser
  // File/Blob API does not exist here.
  form.append("file", {
    uri: item.uri,
    name: item.fileName,
    type: "image/jpeg",
  } as unknown as Blob);

  form.append("document_type", item.documentType);
  if (item.villageId) form.append("village_id", item.villageId);
  if (item.recordYear) form.append("record_year", item.recordYear);
  if (item.khasraNumber) form.append("khasra_number", item.khasraNumber);
  if (item.parcelId) form.append("parcel_id", item.parcelId);

  const created = await api.upload<{ document_id: string }>("/api/v1/documents", form);
  return created.document_id;
}

export async function drainQueue(): Promise<DrainResult> {
  if (!(await isOnline())) {
    for (const item of await uploadQueue.pending()) {
      await uploadQueue.update(item.id, { status: "WAITING_FOR_NETWORK" });
    }
    return { uploaded: 0, failed: 0, offline: true };
  }

  let uploaded = 0;
  let failed = 0;

  for (const item of await uploadQueue.pending()) {
    await uploadQueue.update(item.id, { status: "UPLOADING" });
    try {
      const documentId = await uploadOne(item);
      await uploadQueue.update(item.id, {
        status: "UPLOADED",
        documentId,
        lastError: undefined,
      });
      uploaded += 1;
    } catch (cause) {
      const error = cause instanceof ApiError ? cause : null;
      await uploadQueue.update(item.id, {
        status: error?.isOffline ? "WAITING_FOR_NETWORK" : "FAILED",
        attempts: item.attempts + 1,
        lastError:
          error?.message ??
          (cause instanceof Error ? cause.message : "Upload failed"),
      });
      failed += 1;

      // Lost the connection mid-drain: stop rather than failing the rest.
      if (error?.isOffline) return { uploaded, failed, offline: true };
      break;
    }
  }

  return { uploaded, failed, offline: false };
}
