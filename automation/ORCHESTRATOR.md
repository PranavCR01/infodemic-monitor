# Orchestrator instructions

The orchestrator is a long-lived session woken every hour by a scheduled task. Each wake-up
it does one short check and then goes idle. It never writes product code itself.

## Each wake-up

1. `git fetch origin` and read `automation/BUILD_QUEUE.md` on `origin/langgraph-build`.
2. **If a task is `in_progress`:**
   - Check its session (get_session; the id is in the Session column) and its PR on GitHub.
   - PR merged into `langgraph-build` → make sure the task is `done` (the task session
     normally does this itself), then continue to step 3.
   - Session still working and started less than 6 hours ago → stop here.
   - Session finished or failed with no merged PR, or started 6+ hours ago → if the PR
     exists but is unmerged, mark the task `blocked` with the PR's stated reason. Otherwise
     start one retry (step 3, same task) and note "retry 1" in Notes. A task that already
     had a retry is marked `blocked`.
3. **Start the next ready task:** the first `todo` row whose dependencies are all `done`.
   - Fill in `automation/TASK_PROMPT.md` for it and start a new session on the repo
     (create_session, source revision `langgraph-build`) with that prompt.
   - Set the row to `in_progress`, with the session id and the start time (UTC). Add a Log
     line. Commit and push to `langgraph-build` (pull --rebase first).
4. **Nothing ready:** if every remaining task is `blocked` or waiting on a blocked
   dependency, add one Log line ("waiting: ...") the first time this happens, then stop.

## Rules

- One task in progress at a time.
- Never merge anything into `main`, never close or delete issues, never change the
  schedule.
- Keep each wake-up short; don't investigate code.
- When a task becomes `blocked` or the whole queue finishes, send the project lead a short
  notification saying which task and why.
