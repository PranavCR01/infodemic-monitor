import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { decideAccess, safeNext } from "@/lib/auth/roles";

export async function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  // Old route kept working (HANDOFF §5 renamed /login to /sign-in).
  if (pathname === "/login") return redirectTo(request, "/sign-in", NextResponse.next());

  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet: { name: string; value: string; options: Record<string, unknown> }[]) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) => supabaseResponse.cookies.set(name, value, options));
        },
      },
    }
  );

  // Refresh the session. getUser() asks the Supabase server, so it can't be forged
  // (getSession() only reads the cookie).
  const {
    data: { user },
  } = await supabase.auth.getUser();

  // Signed in already: the sign-in page goes on to where the user was heading.
  if (user && pathname === "/sign-in") {
    return redirectTo(request, safeNext(request.nextUrl.searchParams.get("next")), supabaseResponse);
  }

  const access = decideAccess(pathname, search, user);
  if (access.kind === "sign-in") {
    return redirectTo(request, `/sign-in?next=${encodeURIComponent(access.next)}`, supabaseResponse);
  }
  if (access.kind === "denied") {
    // A missing role renders Permission denied at the same URL, not a redirect (HANDOFF §5).
    const url = request.nextUrl.clone();
    url.pathname = "/permission-denied";
    url.search = `?need=${access.need}`;
    const res = NextResponse.rewrite(url, { status: 403 });
    supabaseResponse.cookies.getAll().forEach((c) => res.cookies.set(c));
    return res;
  }
  return supabaseResponse;
}

function redirectTo(request: NextRequest, target: string, carry: NextResponse) {
  const res = NextResponse.redirect(new URL(target, request.url));
  carry.cookies.getAll().forEach((c) => res.cookies.set(c));
  return res;
}

export const config = {
  // Static files (icons, fonts, images) skip the auth check, so the sign-in page can load them.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icons/).*)"],
};
