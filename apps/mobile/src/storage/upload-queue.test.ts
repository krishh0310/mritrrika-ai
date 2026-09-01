import { beforeEach, describe, expect, it, vi } from "vitest";

const storage = new Map<string, string>();

vi.mock("@react-native-async-storage/async-storage", () => ({
  default: {
    getItem: vi.fn(async (key: string) => storage.get(key) ?? null),
    setItem: vi.fn(async (key: string, value: string) => {
      storage.set(key, value);
    }),
  },
}));

import { uploadQueue } from "./upload-queue";

describe("offline upload queue", () => {
  beforeEach(() => storage.clear());

  it("keeps failed work pending in capture order", async () => {
    const first = await uploadQueue.add({
      uri: "file://first.jpg",
      fileName: "first.jpg",
      documentType: "KHASRA",
    });
    const second = await uploadQueue.add({
      uri: "file://second.jpg",
      fileName: "second.jpg",
      documentType: "KHASRA",
    });
    await uploadQueue.update(first.id, { status: "FAILED", attempts: 1 });

    expect((await uploadQueue.pending()).map((item) => item.id)).toEqual([
      first.id,
      second.id,
    ]);
  });

  it("removes only uploads already accepted by the server", async () => {
    const pending = await uploadQueue.add({
      uri: "file://pending.jpg",
      fileName: "pending.jpg",
      documentType: "KHASRA",
    });
    const uploaded = await uploadQueue.add({
      uri: "file://uploaded.jpg",
      fileName: "uploaded.jpg",
      documentType: "KHASRA",
    });
    await uploadQueue.update(uploaded.id, { status: "UPLOADED", documentId: "DOC-1" });
    await uploadQueue.clearUploaded();

    expect((await uploadQueue.list()).map((item) => item.id)).toEqual([pending.id]);
  });
});
