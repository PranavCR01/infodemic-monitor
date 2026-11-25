"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "@/components/ui";
import type { NavItem } from "./nav";

export function NavLinks({ items }: { items: Pick<NavItem, "href" | "label" | "icon">[] }) {
  const path = usePathname();
  const active = (href: string) => (href === "/" ? path === "/" : path === href || path.startsWith(href + "/"));
  return (
    <nav aria-label="Main" className="flex flex-1 flex-wrap gap-1">
      {items.map((i) => (
        <Link
          key={i.href}
          href={i.href}
          aria-current={active(i.href) ? "page" : undefined}
          className={`inline-flex min-h-10 items-center gap-1.5 rounded-md px-3 font-medium no-underline ${
            active(i.href) ? "bg-primary-subtle text-ink" : "text-ink-2 hover:bg-surface-sunken hover:text-ink"
          }`}
        >
          <Icon name={i.icon} />
          {i.label}
        </Link>
      ))}
    </nav>
  );
}
