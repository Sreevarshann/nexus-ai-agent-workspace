"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { ErrorNote } from "@/components/ui/feedback";
import { Input, Label } from "@/components/ui/input";
import { api } from "@/lib/api";
import { keys } from "@/lib/queries";
import type { User } from "@/lib/types";

const loginSchema = z.object({
  email: z.string().regex(/^[^@\s]+@[^@\s]+\.[^@\s]+$/, "Enter a valid email address"),
  password: z.string().min(1, "Password is required"),
});
const registerSchema = loginSchema.extend({
  name: z.string().min(1, "Your name is required").max(120),
  password: z.string().min(10, "Use at least 10 characters"),
});

type Values = { email: string; password: string; name?: string };

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const qc = useQueryClient();
  const [error, setError] = React.useState<unknown>(null);
  const form = useForm<Values>({
    resolver: zodResolver(mode === "login" ? loginSchema : registerSchema) as never,
    defaultValues: { email: "", password: "", name: "" },
  });

  const onSubmit = form.handleSubmit(async (values) => {
    setError(null);
    try {
      const user = await api.post<User>(`/auth/${mode}`, values);
      qc.setQueryData(keys.me, user);
      router.replace("/workspace");
    } catch (e) {
      setError(e);
    }
  });

  const errors = form.formState.errors;
  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      {mode === "register" && (
        <Field label="Name" error={errors.name?.message} htmlFor="name">
          <Input id="name" autoComplete="name" placeholder="Ada Lovelace" {...form.register("name")} />
        </Field>
      )}
      <Field label="Email" error={errors.email?.message} htmlFor="email">
        <Input id="email" type="email" autoComplete="email" placeholder="you@company.com" {...form.register("email")} />
      </Field>
      <Field label="Password" error={errors.password?.message} htmlFor="password">
        <Input
          id="password"
          type="password"
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          placeholder={mode === "register" ? "At least 10 characters" : "••••••••••"}
          {...form.register("password")}
        />
      </Field>
      {error != null && <ErrorNote title={mode === "login" ? "Sign-in failed" : "Could not create account"} error={error} />}
      <Button type="submit" size="lg" className="w-full" disabled={form.formState.isSubmitting}>
        {form.formState.isSubmitting ? <Loader2 className="animate-spin" /> : null}
        {mode === "login" ? "Sign in" : "Create workspace"}
        {!form.formState.isSubmitting && <ArrowRight />}
      </Button>
      <p className="text-center text-[13px] text-muted">
        {mode === "login" ? "New to NEXUS? " : "Already have an account? "}
        <Link href={mode === "login" ? "/register" : "/login"} className="font-medium text-primary hover:underline">
          {mode === "login" ? "Create an account" : "Sign in"}
        </Link>
      </p>
    </form>
  );
}

function Field({ label, error, htmlFor, children }: { label: string; error?: string; htmlFor: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {error && <p className="text-[12px] text-danger">{error}</p>}
    </div>
  );
}
