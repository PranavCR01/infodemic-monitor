# Multi-Agent Track Context

## 1. What This Role Is

Seven students, **greenfield** research + implementation. No designated lead — the team is
supervised directly by Pranav. Split into 2 pairs and 1 trio (Student-MA1 through
Student-MA7); **subteam assignments are TBD** once names are known.

This track has no prior semester's work to build on — unlike the other four tracks, you're
starting from a blank slate. That also means more of the early work is design, not code.

## 2. The Problem This Solves

The current pipeline classifies a video in **one LLM call, one shot, no verification
step**. Whatever the primary provider (Anthropic) returns is the final answer. A
multi-agent approach adds **deliberation**: multiple agents with different roles debate the
classification before a verdict is returned. This is most valuable for the cases the
single-shot classifier is least confident about — clear-cut cases don't need a committee.

## 3. Proposed Architecture (Not Mandatory — Propose Alternatives)

This is a starting point to react to, not a spec to implement blindly:

- **Extractor agent** — reads the transcript, pulls out specific health claims.
- **Verifier agent** — checks each claim against PubMed evidence.
- **Critic agent** — challenges the verifier's conclusions, flags weak evidence.
- **Coordinator** — runs the group chat, terminates when agents reach agreement or a max
  turn count is hit.
- **Trigger:** runs only when single-LLM confidence < 0.60 — the same threshold under
  investigation by the modality track for the OCR trigger (see `context/MODALITY.md`).
  Consider coordinating with that track on threshold findings.

## 4. Relevant Prior Work

- **AutoGen GroupChat pattern** — explored during project planning as a candidate
  framework for the agent-to-agent conversation.
- **LlamaIndex for PubMed retrieval** — explored as a candidate for the verifier agent's
  evidence lookup.

Neither is implemented in production — both are options for the team to evaluate, not
requirements.

## 5. System Context

Read `context/PRODUCTION.md` and `context/PROJECT_CONTEXT.md` before designing anything.

The multi-agent system should be designed to integrate with the existing pipeline as an
**optional step**, not a replacement for the single-LLM path. The `InferenceProvider`
Protocol in `backend/app/core/inference/classifier.py` is the interface to understand — a
multi-agent provider could implement this same Protocol (`classify(fusion: FusionResult) ->
ClassificationResult`), which would let it slot into `run_pipeline` the same way the
Anthropic/OpenAI providers do today.

## 6. Constraints

- Output must be compatible with the existing `ClassificationResult` schema.
- Must integrate as an **optional** pipeline step — the single-LLM path must keep working
  unmodified for everyone not opted into the multi-agent path.
- Must have a **fallback to single-LLM** if the agent system fails (times out, errors,
  hits max turns without agreement) — a broken multi-agent run should never take down a
  classification that the single-LLM path would have handled fine.

## 7. Objectives This Semester

- **Weeks 1–3:** research and architecture proposal. **Present to Pranav before building
  anything.**
- **Weeks 4–8:** prototype implementation.
- **Weeks 9–12:** evaluation against the single-LLM baseline on the same video set.
- Produce a written comparison: **accuracy, latency, and cost per video** vs. single-LLM.

## 8. Subteam Split (2 Pairs + 1 Trio)

TBD once student names are assigned. **Update this section when the split is decided** —
this file is the source of truth for who's on which subteam.

## 9. Check-In Log

_(Add a dated entry each week with what was done, what was found, and what's next.)_

-

## 10. PR Requirements

- All code goes up as PRs, using `.github/ISSUE_TEMPLATE/multi-agent.md` for the
  originating issue (note the template has a Subteam field).
- Reference the GitHub issue (`Closes #N`).
- Update this file as architecture decisions are made — this file should reflect the
  *current* design, not just the original proposal, as it evolves.
