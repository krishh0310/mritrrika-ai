// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ConfidenceBadge, bandFor } from "@mrittika/ui";

afterEach(cleanup);

describe("field confidence", () => {
  it.each([
    [0.85, "HIGH"],
    [0.6, "MEDIUM"],
    [0.599, "LOW"],
    [undefined, "UNKNOWN"],
  ] as const)("classifies %s as %s", (score, expected) => {
    expect(bandFor(score)).toBe(expected);
  });

  it("shows a word and score so colour is not the only signal", () => {
    render(<ConfidenceBadge score={0.72} />);

    expect(screen.getByText("Medium")).toBeTruthy();
    expect(screen.getByText("0.72")).toBeTruthy();
  });

  it("labels an unavailable score", () => {
    render(<ConfidenceBadge score={null} />);

    expect(screen.getByText("Not scored")).toBeTruthy();
  });
});
