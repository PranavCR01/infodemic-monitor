// Roles and route access (design HANDOFF §5).
//
// ADAPTER: until T27 lands, where the role lives is not final ("Supabase JWT claims
// or a roles table"). We read `app_metadata.role`, which only the service role can
// set; never `user_metadata`, which users can edit themselves. The server enforces
// roles on every endpoint (T27); this module only decides what the UI shows.

export const ROLES = ["analyst", "reviewer", "admin"] as const;
export type Role = (typeof ROLES)[number];

const RANK: Record<Role, number> = { analyst: 0, reviewer: 1, admin: 2 };

/**
 * Role assumed for a signed-in user with no role claim. The design says a missing
 * role should see Permission denied; today no user has a role claim, so that would
 * lock everyone out. Set to null once T27 assigns roles.
 */
export const ROLE_WHEN_MISSING: Role | null = "analyst";

type UserLike = { app_metadata?: Record<string, unknown> | null } | null | undefined;

export function isRole(v: unknown): v is Role {
  return typeof v === "string" && (ROLES as readonly string[]).includes(v);
}

export function roleOf(user: UserLike): Role | null {
  const claim = user?.app_metadata?.role;
  if (isRole(claim)) return claim;
  return user ? ROLE_WHEN_MISSING : null;
}

export function hasRole(role: Role | null, required: Role): boolean {
  return role !== null && RANK[role] >= RANK[required];
}

/** Pages that need more than a signed-in analyst. Longest prefix wins. */
export const ROUTE_ROLES: { prefix: string; role: Role }[] = [
  { prefix: "/review", role: "reviewer" },
  { prefix: "/evaluation", role: "admin" },
];

const matches = (path: string, prefix: string) => path === prefix || path.startsWith(prefix + "/");

export function requiredRole(pathname: string): Role {
  const hit = ROUTE_ROLES.filter((r) => matches(pathname, r.prefix)).sort((a, b) => b.prefix.length - a.prefix.length)[0];
  return hit ? hit.role : "analyst";
}

/** Pages anyone can open, signed in or not. */
export const PUBLIC_PATHS = ["/sign-in", "/auth/callback"];

export function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATHS.some((p) => matches(pathname, p));
}

/**
 * Where to go after signing in. Only same-site paths are accepted, so a crafted
 * `?next=` can't send someone to another site (open redirect).
 */
export function safeNext(next: string | null | undefined, fallback = "/"): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return fallback;
  if (/[\u0000-\u001f]/.test(next)) return fallback;
  if (isPublicPath(next.split("?")[0])) return fallback;
  return next;
}

export const ROLE_DISPLAY: Record<Role, string> = { analyst: "Analyst", reviewer: "Reviewer", admin: "Admin" };

export type Access = { kind: "allow" } | { kind: "sign-in"; next: string } | { kind: "denied"; need: Role };

/** The middleware's decision for one request. */
export function decideAccess(pathname: string, search: string, user: UserLike): Access {
  if (isPublicPath(pathname)) return { kind: "allow" };
  if (!user) return { kind: "sign-in", next: pathname + search };
  const need = requiredRole(pathname);
  return hasRole(roleOf(user), need) ? { kind: "allow" } : { kind: "denied", need };
}
