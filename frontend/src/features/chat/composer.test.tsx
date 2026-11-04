import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Composer } from "@/features/chat/composer";
import { renderWithProviders } from "@/test/render";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("[]", { status: 200 })));
});

describe("Composer", () => {
  it("submits on Enter with the selected mode and keeps Shift+Enter for new lines", async () => {
    const onSubmit = vi.fn();
    renderWithProviders(<Composer onSubmit={onSubmit} />);
    const box = screen.getByRole("textbox", { name: "Message" });
    await userEvent.type(box, "first line{Shift>}{Enter}{/Shift}second");
    expect(onSubmit).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("radio", { name: /Research/ }));
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ content: "first line\nsecond", mode: "research" }));
  });

  it("exposes mission options only in agent mode and passes them through", async () => {
    const onSubmit = vi.fn();
    renderWithProviders(<Composer onSubmit={onSubmit} />);
    expect(screen.queryByRole("switch", { name: /Require approval/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: /Agent/ }));
    await userEvent.click(screen.getByRole("switch", { name: /Require approval/ }));
    await userEvent.type(screen.getByRole("textbox", { name: "Message" }), "research agents{Enter}");
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ mode: "agent", options: { mission_mode: "deep", require_approval: true } }));
  });

  it("shows a stop control while busy and Escape stops", () => {
    const onStop = vi.fn();
    renderWithProviders(<Composer onSubmit={vi.fn()} onStop={onStop} busy />);
    fireEvent.keyDown(screen.getByRole("textbox", { name: "Message" }), { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "Stop generation" }));
    expect(onStop).toHaveBeenCalledTimes(2);
  });
});
