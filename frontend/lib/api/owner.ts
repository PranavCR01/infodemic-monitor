// Who submitted a job (T33, #94). The API sends `submitted_by` as the submitter's
// Supabase user id; display names come with T34. Until then: "You", or a short
// neutral label, never a raw id.

/** True when the viewer submitted the job. Prefers the server's `is_own` (T34) when sent. */
export function isOwnSubmission(submittedBy: string | null | undefined, viewerId: string | null, serverIsOwn?: boolean | null): boolean {
  if (typeof serverIsOwn === "boolean") return serverIsOwn;
  return Boolean(viewerId && submittedBy && submittedBy === viewerId);
}

/** "You", "User 3f9a1c", or null when the job has no recorded owner (legacy rows). */
export function submitterText(submittedBy: string | null | undefined, isOwn: boolean, name?: string | null): string | null {
  if (isOwn) return "You";
  if (name) return name;
  return submittedBy ? `User ${submittedBy.slice(0, 6)}` : null;
}
