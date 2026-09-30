// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { UiLanguageProvider } from "@mrittika/ui";

import { api } from "../../lib/api-client";
import { ForensicsPanel } from "./forensics-panel";

vi.mock("../../lib/api-client", () => ({ api: { get: vi.fn(), post: vi.fn() } }));

beforeEach(() => {
  localStorage.clear();
  vi.resetAllMocks();
  vi.mocked(api.get).mockResolvedValue({ reports: [] });
  vi.mocked(api.post).mockResolvedValue({ reports: [], job: { status: "COMPLETED", progress: 100 } });
});
afterEach(cleanup);

function show(language: "en" | "hi" = "en") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <UiLanguageProvider defaultLanguage={language}><ForensicsPanel documentId="DOC-1" /></UiLanguageProvider>
    </QueryClientProvider>,
  );
}

it("requires keyboard consent before sending a document externally and announces completion", async () => {
  const user = userEvent.setup();
  show();
  const run = screen.getByRole<HTMLButtonElement>("button", { name: "Run checks" });
  expect(run.disabled).toBe(true);
  expect(screen.getByText(/do not prove authenticity or fraud/)).toBeTruthy();
  await user.tab();
  expect(document.activeElement).toBe(screen.getByRole("checkbox"));
  await user.keyboard(" ");
  expect(run.disabled).toBe(false);
  expect(api.post).not.toHaveBeenCalled();
  await user.tab();
  expect(document.activeElement).toBe(run);
  await user.keyboard("{Enter}");
  await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/v1/documents/DOC-1/forensics", { consent: true }));
  await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Checks finished"));
});

it("provides Hindi controls and translates an AI verdict without calling it proof", async () => {
  vi.mocked(api.get).mockResolvedValue({ reports: [{
    check: "tamper", verdict: "AUTHENTIC", score: 2, result: {}, created_at: null,
  }] });
  show("hi");
  expect(screen.getByRole("region", { name: "दस्तावेज़ जाँच" })).toBeTruthy();
  expect(screen.getByRole("checkbox").getAttribute("type")).toBe("checkbox");
  expect(await screen.findByText(/एआई ने कोई संदेह नहीं बताया/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "फिर से जाँचें" })).toBeTruthy();
});

it("announces report retrieval errors instead of claiming checks were never run", async () => {
  vi.mocked(api.get).mockRejectedValue(new Error("provider-secret"));
  show();
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(screen.getByText("Previous reports could not be loaded.")).toBeTruthy();
  expect(screen.queryByText("Not run yet.")).toBeNull();
  expect(screen.queryByText("provider-secret")).toBeNull();
  expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
});

 it("shows queued progress and prevents duplicate runs", async () => {
  vi.mocked(api.get).mockResolvedValue({ reports: [], job: { status: "RUNNING", progress: 40 } });
  show();
  await waitFor(() => expect(screen.getByRole("status").textContent).toContain("40%"));
  expect(screen.getByRole<HTMLButtonElement>("button", { name: /Checks are running/ }).disabled).toBe(true);
});
