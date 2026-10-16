---
title: n8n: sub-workflows & refactor
category: Automation
description: Split a large or duplicated workflow into reusable sub-workflows with typed inputs, verb-first names, and clean execution modes.
tags: n8n, subworkflow, refactor, reuse
input: Which workflow(s) to refactor and what logic is shared or repeated.
---
Invoke the `n8n-subworkflows` and `n8n-workflow-patterns` skills (Skill tool) first; use `using-n8n-mcp-skills` for the tool loop.

Map the current workflow(s), identify the shared logic, and propose the split (sub-workflow names, typed inputs, all-vs-each mode) before changing anything. Build the sub-workflows as NEW workflows and leave the originals untouched and published; wire the refactored version as an unpublished copy for me to test. Never test against live contacts.
