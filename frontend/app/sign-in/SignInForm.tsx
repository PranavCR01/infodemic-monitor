"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Button, Field, Icon } from "@/components/ui";
import { emailProblem, magicLinkOutcome, passwordSignInError } from "@/lib/auth/messages";
import { getBrowserClient } from "@/lib/supabase";

type Props = { next: string; notice: string | null };

export function SignInForm({ next, notice }: Props) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [emailError, setEmailError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(notice);
  const [busy, setBusy] = useState<"password" | "link" | null>(null);
  const [sentTo, setSentTo] = useState<string | null>(null);

  function checkEmail(): boolean {
    const problem = emailProblem(email);
    setEmailError(problem);
    return problem === null;
  }

  async function signIn(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const okEmail = checkEmail();
    const okPassword = password.length > 0;
    setPasswordError(okPassword ? null : "Enter your password, or email yourself a sign-in link.");
    if (!okEmail || !okPassword) return;
    setBusy("password");
    const { error } = await getBrowserClient().auth.signInWithPassword({ email: email.trim(), password });
    setBusy(null);
    if (error) {
      setFormError(passwordSignInError(error));
      return;
    }
    router.replace(next);
    router.refresh();
  }

  async function sendLink() {
    setFormError(null);
    setPasswordError(null);
    if (!checkEmail()) return;
    setBusy("link");
    const redirect = new URL("/auth/callback", window.location.origin);
    redirect.searchParams.set("next", next);
    const { error } = await getBrowserClient().auth.signInWithOtp({
      email: email.trim(),
      // Invitation only: a link never creates an account.
      options: { shouldCreateUser: false, emailRedirectTo: redirect.toString() },
    });
    setBusy(null);
    const outcome = magicLinkOutcome(error);
    if (outcome.sent) setSentTo(email.trim());
    else setFormError(outcome.message ?? null);
  }

  return (
    <div className="flex w-full max-w-[400px] flex-col gap-6">
      <div className="flex flex-col gap-1.5">
        <h2 className="font-serif text-h1 text-ink">Sign in</h2>
        <p className="text-small text-ink-2">Use the email address your invitation was sent to.</p>
      </div>

      {sentTo ? (
        <div role="status" className="flex gap-3 rounded-lg border border-nomisinfo-bd bg-primary-subtle p-4 text-ink">
          <Icon name="mail" className="mt-0.5 !h-5 !w-5 text-primary" />
          <div className="flex flex-col gap-1">
            <strong>Check your email</strong>
            <span className="text-small">
              If <span className="font-mono">{sentTo}</span> has an invitation, we sent a sign-in link to it. It works once and expires in 1 hour.
            </span>
            <button type="button" className="w-fit text-small text-primary underline" onClick={() => setSentTo(null)}>
              Use a different address, or send it again
            </button>
          </div>
        </div>
      ) : (
        <>
          {formError && (
            <p role="alert" className="rounded-md border border-err-bd bg-err-bg px-3 py-2 text-small text-err-fg">
              {formError}
            </p>
          )}
          <form noValidate onSubmit={signIn} className="flex flex-col gap-4">
            <Field
              id="email"
              label="Email"
              type="email"
              autoComplete="email"
              inputMode="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              error={emailError}
            />
            <Field
              id="password"
              label="Password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              error={passwordError}
            />
            <Button type="submit" className="w-full" disabled={busy !== null}>
              {busy === "password" ? "Signing in…" : "Sign in"}
            </Button>
          </form>
          <div className="flex items-center gap-3" aria-hidden="true">
            <hr className="flex-1 border-line" />
            <span className="text-cap text-ink-3">or</span>
            <hr className="flex-1 border-line" />
          </div>
          <Button variant="secondary" className="w-full" onClick={sendLink} disabled={busy !== null}>
            <Icon name="mail" />
            {busy === "link" ? "Sending…" : "Email me a sign-in link"}
          </Button>
        </>
      )}

      <p className="text-cap text-ink-3">
        No account? Ask your project lead for an invitation. Forgot your password? Email yourself a sign-in link.
      </p>
    </div>
  );
}
