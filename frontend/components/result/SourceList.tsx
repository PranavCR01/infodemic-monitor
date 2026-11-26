"use client";

import { useEffect, useId, useRef, useState } from "react";
import { buttonClass } from "@/components/ui";
import type { BlindSource } from "@/lib/api/blind-material";
import type { Source } from "@/lib/api/result-adapter";
import { SourceCard } from "./SourceCard";

/** How many sources show before "Show N more sources" (T59). */
export const SOURCES_SHOWN = 3;

/**
 * A claim's sources, the first few shown and the rest behind a button (T59). The order is
 * the caller's and is never changed here: in the blind step that is retrieval order, so
 * the split says nothing about how a source relates to the claim.
 */
export function SourceList({ sources, initial = SOURCES_SHOWN }: { sources: (Source | BlindSource)[]; initial?: number }) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const firstHidden = useRef<HTMLLIElement>(null);
  const justOpened = useRef(false);
  const hidden = Math.max(0, sources.length - initial);
  const visible = open ? sources : sources.slice(0, initial);

  // After "Show more", move focus to the first newly shown source (keyboard users land on the new content).
  useEffect(() => {
    if (open && justOpened.current) {
      justOpened.current = false;
      firstHidden.current?.focus();
    }
  }, [open]);

  if (sources.length === 0) return null;
  return (
    <div className="flex flex-col gap-2">
      <ul id={listId} className="flex flex-col gap-2">
        {visible.map((s, i) => (
          <li key={s.id} ref={i === initial ? firstHidden : undefined} tabIndex={i === initial ? -1 : undefined} className="outline-none focus-visible:ring-2 focus-visible:ring-primary">
            <SourceCard s={s} />
          </li>
        ))}
      </ul>
      {hidden > 0 && (
        <button
          type="button"
          aria-expanded={open}
          aria-controls={listId}
          onClick={() => {
            justOpened.current = !open;
            setOpen(!open);
          }}
          className={buttonClass("secondary", "sm", "w-fit")}
        >
          {open ? "Show fewer sources" : `Show ${hidden} more ${hidden === 1 ? "source" : "sources"}`}
        </button>
      )}
    </div>
  );
}
