---
title: Write a PRD
category: Planning
description: Turn a rough idea into a phased product requirements doc before any building starts.
tags: prd, planning, spec, scope
input: The idea / problem, who it's for, and any constraints or must-haves.
---
Define before building. Produce a tight PRD that exposes assumptions and splits the work into phases, so sessions don't drift and late changes stay cheap.

## Steps
1. **Interview the idea.** Ask (or infer and state) the business problem, the users, the behavior they need, success criteria, and hard constraints. Call out unknowns and risky assumptions explicitly rather than papering over them.
2. **Draft the PRD** with these sections: Problem · Users & jobs · Goals / non-goals · Core flows · Data & integrations · Constraints (brand, security, budget) · Open questions. Keep it concrete and short — decisions, not prose.
3. **Phase the work.** Break delivery into phases (e.g. foundation → core flow → integrations → polish), each with a clear "done" and a way to verify it. Note where backend / frontend / integration work split.
4. **Verification plan.** For each phase, say how we'll confirm it works against the *deployed* result (real browser flows, responsive, form submits, auth/data isolation) — a green local build isn't proof.
5. **Output** the PRD as Markdown (or a Word doc via the docx skill if it's client-facing), and list the open questions that should be answered before Phase 1.

## Rules
- Match model + effort to the task; don't over-plan a small change or under-plan a big one.
- Reflect GF's constraints where relevant: per-repo CLAUDE.md context, read-only GHL, secrets out of the repo, drafts stay drafts until approved.
- End with a recommendation on what to build first — not an exhaustive menu.
