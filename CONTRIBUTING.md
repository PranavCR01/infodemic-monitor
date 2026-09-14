# Contributing to WHO Infodemic Monitor

Welcome to the team. Read this fully before touching anything.

---

## 1. Before You Start

Read these in order:

1. [`context/PROJECT_CONTEXT.md`](context/PROJECT_CONTEXT.md) — what the system is, the full stack, and how the team is organized
2. Your domain's context file — find it in the [`context/`](context/) folder:
   - Production → [`context/PRODUCTION.md`](context/PRODUCTION.md)
   - Model Evaluation → [`context/MODEL_EVAL.md`](context/MODEL_EVAL.md)
   - Modality Comparison → [`context/MODALITY.md`](context/MODALITY.md)
   - Claim-Level Classification → [`context/CLAIM_LEVEL.md`](context/CLAIM_LEVEL.md)
   - Multi-Agent → [`context/MULTI_AGENT.md`](context/MULTI_AGENT.md)

Do not start any work until you have read both documents.

---

## 2. One-Time Setup

### Clone the repo

```bash
git clone https://github.com/PranavCR01/infodemic-monitor.git
cd infodemic-monitor
```

### Backend setup (production track only)

```bash
cd backend
pip install -e ".[dev]"
cp ../.env.example .env
# Fill in your .env values — ask Pranav for the keys
```

### Frontend setup (production track only)

```bash
cd frontend
npm install
cp .env.example .env.local
# Fill in your .env.local values
```

---

## 3. Workflow — Every Issue

Every piece of work maps to a GitHub Issue. Never work without an issue. Never push directly to `main`.

### Step 1 — Find your issue

Go to the [Project board](https://github.com/users/PranavCR01/projects/1) or the [Issues tab](https://github.com/PranavCR01/infodemic-monitor/issues). Your issues are assigned to you and labeled with your domain.

### Step 2 — Start from a clean main

```bash
git checkout main
git pull origin main
```

Always do this before creating a new branch. Never branch off an existing feature branch.

### Step 3 — Create a branch

Name your branch after your issue number and a short description:

```bash
git checkout -b feature/<issue-number>-short-description
```

Examples:
```bash
git checkout -b feature/9-expand-modality-dataset
git checkout -b feature/1-sha256-dedup
git checkout -b feature/14-multi-agent-proposal
```

### Step 4 — Do your work

Make your changes. Commit regularly with clear messages:

```bash
git add .
git commit -m "Short description of what you did (#<issue-number>)"
```

### Step 5 — Update your context doc

Every PR must include an update to your domain's context file in `context/`. If your work changes anything documented there — findings, decisions, current state — update it in the same commit. PRs without context doc updates will not be approved if the doc is now out of date.

### Step 6 — Push your branch

```bash
git push origin feature/<issue-number>-short-description
```

### Step 7 — Open a Pull Request

Go to [github.com/PranavCR01/infodemic-monitor](https://github.com/PranavCR01/infodemic-monitor). You will see a yellow banner — click **Compare & pull request**.

The PR description will auto-populate with a template. Fill in every field. The most important line is at the top:

```
Closes #<issue-number>
```

This must be in the **PR description**, not a comment. It links your PR to the issue and closes it automatically when merged.

### Step 8 — Wait for review

Pranav will review your PR, leave comments if needed, and approve. Do not merge your own PR. Once approved and merged, your issue closes automatically and moves to Done on the board.

---

## 4. Research Tracks

If you are on Model Eval, Modality, Claim-Level, or Multi-Agent — your output is mostly scripts, notebooks, and CSV results rather than production code changes. Put all your work under:

```
research/<your-domain>/
```

Examples:
```
research/modality/
research/model-eval/
research/claim-level/
research/multi-agent/
```

Keep research files completely separate from `backend/` and `frontend/`. Do not modify production code without coordinating with the production student and Pranav first.

---

## 5. Rules

- **Never push directly to `main`** — branch protection will block it anyway
- **Every change needs an issue** — if there is no issue for your work, create one first
- **`Closes #N` goes in the PR description**, not a comment
- **Update your context doc in the same PR** as your code or analysis
- **Coordinate cross-domain changes** — if your work touches the production schema (e.g. claim-level schema changes), talk to the production student and Pranav before opening a PR
- **One issue per PR** — don't bundle unrelated work into one PR

---

## 6. Getting Help

- Read your domain's context file first — most questions are answered there
- Check existing issues and PRs for prior discussion
- If still stuck, tag Pranav in a comment on your issue
