# Orchestrator instructions

The orchestrator is a long-lived session. It never writes product code itself. It acts on two
kinds of message:

- **"Task finished: Txx ..."** sent by a task session the moment it merges or gets blocked.
  Act on it immediately.
- **"Orchestrator wake-up"** from the hourly scheduled task. This is only a safety net for a
  task session that died without reporting.

Both get the same check below. Speed matters: start ready work as soon as it is ready.

## Each check

1. `git fetch origin` and read `automation/BUILD_QUEUE.md` on `origin/langgraph-build`.
2. **For every task that is `in_progress`:**
   - Check its session (get_session; the id is in the Session column) and its PR on GitHub.
   - PR merged into `langgraph-build` → make sure the task is `done` (the task session
     normally does this itself).
   - Session still working and started less than 6 hours ago → leave it.
   - Session finished or failed with no merged PR, or started 6+ hours ago → if the PR
     exists but is unmerged, mark the task `blocked` with the PR's stated reason. Otherwise
     restart it once (step 3) and note "retry 1" in Notes. A task that already had a retry
     is marked `blocked`.
3. **Start every ready task, up to 3 in progress in total.** A task is ready when it is
   `todo` and all its dependencies are `done`. Start them in table order.
   - Fill in `automation/TASK_PROMPT.md` for each one (including this orchestrator's session
     id, `session_013cWxq1xr2wMZ2m7f1Z5MU8`) and start a new session on the repo
     (create_session, source_url https://github.com/PranavCR01/infodemic-monitor,
     source_revision `langgraph-build`, tags ["infodemic-build"]).
   - Set each row to `in_progress`, with the session id and the start time (UTC). Add Log
     lines. Commit and push to `langgraph-build` (pull --rebase first).
4. **Nothing ready and nothing running:** if every remaining task is `blocked` or waiting on
   a blocked dependency, add one Log line ("waiting: ...") the first time this happens.

## Rules

- At most 3 tasks in progress at once.
- Never merge anything into `main`, never close or delete issues, never change the
  schedule.
- Keep each check short; don't investigate code.
- When a task becomes `blocked` or the whole queue finishes, send the project lead a short
  notification saying which task and why.
