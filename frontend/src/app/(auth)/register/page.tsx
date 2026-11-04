import type { Metadata } from "next";

import { LogoMark } from "@/components/shell/logo";
import { AuthForm } from "@/features/auth/auth-form";

export const metadata: Metadata = { title: "Create account" };

export default function RegisterPage() {
  return (
    <div>
      <LogoMark className="mb-6 size-10 lg:hidden" />
      <h1 className="text-[26px] font-semibold tracking-[-0.025em] text-ink">Create your workspace</h1>
      <p className="mb-8 mt-1.5 text-[14px] text-muted">Accounts are stored locally in your NEXUS database.</p>
      <AuthForm mode="register" />
    </div>
  );
}
