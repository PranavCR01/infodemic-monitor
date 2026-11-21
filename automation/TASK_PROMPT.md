# Prompt for one automated build task

The orchestrator fills in `<TASK>`, `<ISSUE>` and `<SECTIONS>` from `automation/BUILD_QUEUE.md`
and sends this to a fresh session.

```
You are building one task of the WHO Infodemic Monitor target system, unattended.
Work autonomously: make reasonable decisions, record them, and only stop if truly
blocked. Nobody will answer questions while you work.

Task: <TASK>   Issue: <ISSUE>   Design sections: §<SECTIONS>

## Read first
- docs/target-system-design.md (§<SECTIONS> in full, plus §4–§5 for the state
  schema and §14 for how work is measured).
- The GitHub issue <ISSUE> (if it has a number) and its acceptance criteria.
- context/MULTI_AGENT.md, automation/BUILD_QUEUE.md, and the code this plugs into.

## Branching
- Start from the latest langgraph-build: git fetch origin; git checkout -b
  auto/<task-id> origin/langgraph-build.
- NEVER push to, merge into, or open a PR against main.

## Build rules
- Follow the design doc. Where the doc and an issue disagree, the doc wins; note it.
- Model choices come from config (config/routing.yaml once it exists); never
  hardcode a model id in node code.
- No real API calls: mock every model and external service in tests (PubMed via
  recorded fixtures). No API keys are available to you; do not try to obtain any.
- Tests for every acceptance criterion. Run the whole backend test suite
  (cd backend && python -m pytest); everything must pass, including the tests that
  existed before.
- Don't change the live pipeline's behaviour unless the task is the integration
  task, and then only behind a flag that defaults to off.
- Never commit secrets, videos, zips or large binaries.

## Finish
1. Update context/MULTI_AGENT.md: add a dated check-in log line for this task and any
   design decision you made.
2. Push auto/<task-id> and open a PR into langgraph-build titled
   "[auto] <task-id>: <TASK>", with: what was built, test results, decisions and
   deviations from the doc, and anything left for a person.
3. If the full test suite passes, merge the PR into langgraph-build yourself
   (squash). If it doesn't pass and you can't fix it, leave the PR open and explain
   why in the PR.
4. In automation/BUILD_QUEUE.md on langgraph-build, set this task to `done` (merged)
   or `blocked` (with the reason), fill in the PR link, and add a Log line. Commit
   that directly to langgraph-build (git pull --rebase first).
```
