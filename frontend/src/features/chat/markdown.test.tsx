import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { linkifyCitations, Markdown } from "@/features/chat/markdown";

describe("citations in markdown", () => {
  it("links labels outside code fences only", () => {
    const out = linkifyCitations("Claim [S1].\n```\narr[S2]\n```\nData [D1]");
    expect(out).toContain("[S1](#cite-S1)");
    expect(out).toContain("arr[S2]");
    expect(out).toContain("[D1](#cite-D1)");
  });

  it("renders clickable chips and flags labels without evidence", () => {
    const onCite = vi.fn();
    render(<Markdown content={"Efficiency was 91.3% [S1]. Unknown [S9]."} onCite={onCite} known={new Set(["S1"])} />);
    fireEvent.click(screen.getByRole("button", { name: "Citation S1" }));
    expect(onCite).toHaveBeenCalledWith("S1");
    expect(screen.getByRole("button", { name: "Citation S9" }).className).toContain("line-through");
  });

  it("renders GFM tables and keeps currency as text", () => {
    render(<Markdown content={"| a | b |\n|---|---|\n| $20 million | $5 |"} />);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("$20 million")).toBeInTheDocument();
  });
});
