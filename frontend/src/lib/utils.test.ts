import { describe, expect, it } from "vitest";

import { domainOf, formatBytes, formatDuration, formatNumber } from "@/lib/utils";

describe("formatters", () => {
  it("formats durations", () => {
    expect(formatDuration(420)).toBe("420 ms");
    expect(formatDuration(1500)).toBe("1.5 s");
    expect(formatDuration(125_000)).toBe("2m 5s");
    expect(formatDuration(null)).toBe("—");
  });
  it("abbreviates large numbers but keeps small ones exact", () => {
    expect(formatNumber(20_068_214.8)).toBe("20.07M");
    expect(formatNumber(15_270)).toBe("15.3k");
    expect(formatNumber(42)).toBe("42");
  });
  it("formats bytes and domains", () => {
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(domainOf("https://www.langchain.com/langgraph")).toBe("langchain.com");
    expect(domainOf("not a url")).toBe("not a url");
  });
});
