import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChartView } from "@/features/data/chart";

const spec = { type: "bar" as const, x: "region", y: ["sum_revenue"], title: "Revenue by region", columns: ["region", "sum_revenue"], rows: [["North", 1200.5], ["South", 800]] };

describe("ChartView", () => {
  it("renders a chart container and a table view with exact values", () => {
    render(<ChartView spec={spec} />);
    expect(screen.getByTestId("chart")).toBeInTheDocument();
    expect(screen.getByText("Revenue by region")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show table" }));
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("1,200.5")).toBeInTheDocument();
  });
});
