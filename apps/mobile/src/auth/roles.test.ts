import { describe, expect, it } from "vitest";

import { experienceFor, primaryRole } from "./roles";

describe("mobile role routing", () => {
  it("routes citizens to their portal", () => {
    expect(experienceFor({ roles: ["CITIZEN"], permissions: [] })).toBe("CITIZEN");
  });

  it("routes upload-capable officers to field capture", () => {
    expect(
      experienceFor({ roles: ["DEO"], permissions: ["document:upload"] }),
    ).toBe("FIELD");
  });

  it("keeps verifier and approval work on desktop", () => {
    expect(experienceFor({ roles: ["VERIFIER"], permissions: [] })).toBe(
      "DESKTOP_ONLY",
    );
  });

  it("chooses only a known primary role", () => {
    expect(primaryRole(["UNTRUSTED", "TEHSILDAR"])).toBe("TEHSILDAR");
  });
});
