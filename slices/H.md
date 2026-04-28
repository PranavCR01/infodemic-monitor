# Slice H — Job History Dashboard

## Goal
Build the job history list page and result detail page.
Add GET /jobs endpoint to the backend.
This is the last slice before production deploy.

## Pre-implementation
1. Read CLAUDE.md
2. All slices A–G must be complete
3. Read existing frontend/app/page.tsx for design language to match
4. Read GET /jobs/{job_id}/result to understand the result schema

---

## H1. Backend — GET /jobs endpoint

### backend/app/services/job_service.py
Add method:
```python
async def list_jobs(
    session: AsyncSession,
    limit: int = 20,
    offset: int = 0,
    label: Optional[str] = None,
) -> list[dict]:
    # Join Job + Video + Result (left join Result)
    # Return: job_id, status, error_code, created_at,
    #         video filename, label, confidence
    # Order by created_at DESC
    # Filter by label if provided
```

### backend/app/api/routers/jobs.py
Add:
```python
@router.get("/jobs")
async def list_jobs(
    limit: int = 20,
    offset: int = 0,
    label: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    return await job_service.list_jobs(session, limit, offset, label)
```

---

## H2. Frontend pages

### frontend/app/jobs/page.tsx — Server Component

Fetches job list, renders the dashboard.

```tsx
// Server component — use server-side supabase client + apiFetch
export default async function JobsPage() {
  const jobs = await fetchJobs(); // server-side apiFetch("/jobs")
  return <JobsView jobs={jobs} />;
}
```

### frontend/app/jobs/JobsView.tsx — Client Component

Handles polling and renders the table:

```tsx
"use client";

export function JobsView({ initialJobs }) {
  const [jobs, setJobs] = useState(initialJobs);

  useEffect(() => {
    const hasActive = jobs.some(
      j => j.status === "PENDING" || j.status === "PROCESSING"
    );
    if (!hasActive) return;

    const interval = setInterval(async () => {
      const updated = await apiFetch("/jobs").then(r => r.json());
      setJobs(updated);
    }, 5000);

    return () => clearInterval(interval);
  }, [jobs]);

  // render table
}
```

### Each job row shows:
- Video filename (max 40 chars, ellipsis)
- Relative timestamp ("2 hours ago") — use `date-fns` or a simple
  inline helper, no extra deps if avoidable
- Status badge:
  - `PENDING` → gray pill
  - `PROCESSING` → blue pill with CSS pulse animation
  - `SUCCESS` → green pill
  - `FAILED` → red pill (show error_code as tooltip)
- Label badge (only if SUCCESS):
  - `MISINFO` → red
  - `NO_MISINFO` → green
  - `DEBUNKING` → blue
  - `CANNOT_RECOGNIZE` → gray
- Confidence: "95%" next to label badge
- "View →" link → `/jobs/[job_id]`

### Empty state:
```tsx
<div>
  <p>No analyses yet.</p>
  <Link href="/">Upload a video to get started →</Link>
</div>
```

---

## H3. frontend/app/jobs/[job_id]/page.tsx — Result Detail

Server component. Fetches `GET /jobs/{job_id}/result`.

Sections:
1. **Header**: filename + label badge + confidence + back link
2. **Explanation**: the natural-language explanation text
3. **Evidence snippets**: each snippet in a card with quote styling
4. **PubMed Citations** (if present): cards with:
   - Claim that triggered the search
   - Paper title (linked to `https://pubmed.ncbi.nlm.nih.gov/{pmid}/`)
5. **Metadata**: provider, model_used, latency_ms, submitted_at

Handle states:
- Job not found → 404 page
- Job FAILED → show error_code with a friendly message
- Job PENDING/PROCESSING → show "Analysis in progress..." with
  a client component that polls every 5s until terminal state

---

## H4. Navigation update
Add "Job History" link to the header/nav in `frontend/app/page.tsx`
pointing to `/jobs`.

---

## Definition of Done
- [ ] GET /jobs returns paginated list with correct fields
- [ ] /jobs page loads and shows all past jobs
- [ ] Status badges render correctly for all 4 states
- [ ] Label badges render correctly for all 4 labels
- [ ] Polling starts only if active jobs exist, stops when all terminal
- [ ] /jobs/[job_id] shows full result with PubMed citation links
- [ ] Empty state shown when no jobs exist
- [ ] Design matches WHO blue theme from upload page
- [ ] CLAUDE.md updated: Slice H → ✅
- [ ] CLAUDE.md "Slice Progress" table: all A–H marked ✅
