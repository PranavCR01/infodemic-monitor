import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";
import { safeNext } from "@/lib/auth/roles";

// Magic-link landing: swap the one-time code for a session cookie, then continue.
// The Supabase project must list <site>/auth/callback under Auth → URL Configuration.
export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code");
  const next = safeNext(request.nextUrl.searchParams.get("next"));
  if (!code) return NextResponse.redirect(new URL("/sign-in?error=link", request.url));

  const store = cookies();
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => store.getAll(),
        setAll: (toSet: { name: string; value: string; options: Record<string, unknown> }[]) =>
          toSet.forEach(({ name, value, options }) => store.set(name, value, options)),
      },
    }
  );
  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error) return NextResponse.redirect(new URL("/sign-in?error=link", request.url));
  return NextResponse.redirect(new URL(next, request.url));
}
