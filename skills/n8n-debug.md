---
title: n8n: debug / fix a workflow
category: Automation
description: Diagnose a failing or silently-skipping workflow — validation errors, expression mistakes, missing error handling — and fix it safely.
tags: n8n, debug, errors, validation
input: The workflow name/ID, what's going wrong (error text, execution ID, or "it silently skips"), and when it started.
---
Invoke the `n8n-validation-expert`, `n8n-error-handling` and `n8n-expression-syntax` skills (Skill tool) first; use `using-n8n-mcp-skills` for the tool loop.

Diagnose before changing anything: read the workflow and the failing execution(s), name the root cause in one line, and propose the fix. Then apply it, re-validate, and wire error handling so the failure would be loud next time. Keep the edited workflow UNPUBLISHED until I review (unless I explicitly say it's a live hotfix). Never touch signature/verification steps unless asked.
