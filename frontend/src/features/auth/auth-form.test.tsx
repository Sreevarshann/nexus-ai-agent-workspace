import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AuthForm } from "@/features/auth/auth-form";
import { renderWithProviders } from "@/test/render";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, push: vi.fn() }) }));

describe("AuthForm", () => {
  it("validates fields before calling the API", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<AuthForm mode="register" />);
    await userEvent.type(screen.getByLabelText("Email"), "not-an-email");
    await userEvent.type(screen.getByLabelText("Password"), "short");
    await userEvent.click(screen.getByRole("button", { name: /Create workspace/ }));
    expect(await screen.findByText("Enter a valid email address")).toBeInTheDocument();
    expect(screen.getByText("Use at least 10 characters")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the server error and does not navigate on failed sign-in", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Invalid email or password" }), { status: 401 })));
    renderWithProviders(<AuthForm mode="login" />);
    await userEvent.type(screen.getByLabelText("Email"), "a@nexus.local");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: /Sign in/ }));
    expect(await screen.findByText("Invalid email or password")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("navigates to the workspace after signing in", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "1", email: "a@nexus.local", name: "A" }), { status: 200 })));
    renderWithProviders(<AuthForm mode="login" />);
    await userEvent.type(screen.getByLabelText("Email"), "a@nexus.local");
    await userEvent.type(screen.getByLabelText("Password"), "right-password");
    await userEvent.click(screen.getByRole("button", { name: /Sign in/ }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/workspace"));
  });
});
