import type { Metadata } from "next";

import { LogoMark } from "@/components/shell/logo";
import { AuthForm } from "@/features/auth/auth-form";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <div>
      <LogoMark className="mb-6 size-10 lg:hidden" />
      <h1 className="text-[26px] font-semibold tracking-[-0.025em] text-ink">Welcome back</h1>
      <p className="mb-8 mt-1.5 text-[14px] text-muted">Sign in to your NEXUS workspace.</p>
      <AuthForm mode="login" />
    </div>
  );
}
