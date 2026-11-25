# Smoke test against a deployed environment

`e2e/smoke.spec.ts` walks the analyst journey on a real deployment: sign in →
upload a short video → follow the progress view → read the result → open a
claim and close it → export and print the report → find the job in the list.
It checks along the way that no internal names or codes appear on screen and
that the browser console stays clean.

It never runs in CI and skips unless it is configured. It creates a real job,
so point it at staging or a preview with a staging backend, not production.

## Run

```bash
cd frontend
E2E_BASE_URL=https://<preview>.vercel.app \
E2E_EMAIL=<test analyst> E2E_PASSWORD=<password> \
E2E_VIDEO=/path/to/short-clip.mp4 \
npm run e2e
```

- `E2E_TIMEOUT_MINUTES` (default 10): how long to wait for the analysis.
- `PW_CHROMIUM_PATH`: a Chromium binary, if Playwright's own isn't installed
  (`npx playwright install chromium` otherwise).
- The video must be MP4 or MOV, under 3 minutes and 100 MB. A clip with a
  spoken health claim exercises the claim drawer; without claims that step is
  skipped and noted.
- Credentials come from the environment only. Use a dedicated test account
  with the analyst role, never a real person's.

The report (screenshots of each step, the exported PDF) is written to
`frontend/e2e-report/`; open `index.html`. Neither folder is committed.

## Needs, on the deployment

- Supabase password sign-in for the test account.
- `STORAGE_BACKEND=supabase` on the API (signed uploads), and the bucket
  accepting browser uploads from the frontend's origin.
- The worker running, so the job finishes.
