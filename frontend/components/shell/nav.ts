import { hasRole, type Role } from "@/lib/auth/roles";

export type NavItem = { href: string; label: string; icon: string; role: Role; match: (path: string) => boolean };

// Routes move to the design's names (/videos, /review, /evaluation) as their
// screens are built; each item is listed only once its page exists.
export const NAV: NavItem[] = [
  { href: "/jobs", label: "Videos", icon: "grid", role: "analyst", match: (p) => p === "/jobs" || p.startsWith("/jobs/") },
  { href: "/", label: "Submit", icon: "upload", role: "analyst", match: (p) => p === "/" },
  { href: "/review", label: "Review queue", icon: "inbox", role: "reviewer", match: (p) => p === "/review" || p.startsWith("/review/") },
];

export function navFor(role: Role | null): NavItem[] {
  return NAV.filter((i) => hasRole(role, i.role));
}

export function initials(email: string | null | undefined): string {
  const local = (email ?? "").split("@")[0];
  const parts = local.split(/[._-]+/).filter(Boolean);
  const letters = parts.length >= 2 ? parts[0][0] + parts[parts.length - 1][0] : local.slice(0, 2);
  return letters.toUpperCase() || "?";
}
