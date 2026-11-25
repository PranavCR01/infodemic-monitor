// Plain-language sign-in messages. Supabase's own messages are technical and some
// would reveal whether an account exists; none of them reach the screen.

type AuthErrorLike = { message?: string; status?: number; code?: string } | null | undefined;

export const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function emailProblem(email: string): string | null {
  if (!email.trim()) return "Enter your email address.";
  if (!EMAIL_PATTERN.test(email.trim())) return "Enter an email address like name@example.org.";
  return null;
}

export function passwordSignInError(error: AuthErrorLike): string {
  if (!error) return "";
  if (error.status === 429) return "Too many attempts. Wait a minute, then try again.";
  if (error.code === "email_not_confirmed" || /not confirmed/i.test(error.message ?? "")) {
    return "This address hasn't been confirmed yet. Use the link in your invitation email first.";
  }
  if (error.status === 400 || /invalid login credentials/i.test(error.message ?? "")) {
    return "That email and password don't match. Check them, or email yourself a sign-in link.";
  }
  return "We couldn't sign you in just now. Try again in a moment.";
}

/**
 * Sign-in link result. Invitation-only, so an unknown address must look the same
 * as a known one; only rate limits and outages are reported.
 */
export function magicLinkOutcome(error: AuthErrorLike): { sent: boolean; message?: string } {
  if (!error) return { sent: true };
  if (error.status === 429) return { sent: false, message: "Too many sign-in links requested. Wait a minute, then try again." };
  if (error.status && error.status >= 500) return { sent: false, message: "We couldn't send the link just now. Try again in a moment." };
  return { sent: true };
}

export const CALLBACK_ERRORS: Record<string, string> = {
  link: "That sign-in link has expired or was already used. Ask for a new one below.",
  session: "Your session ended. Sign in again to continue.",
};
