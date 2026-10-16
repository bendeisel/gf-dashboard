---
title: n8n: Code node (JS / Python)
category: Automation
description: Write or fix the code inside an n8n Code node — $input/$json/$node, batching, dates, HTTP helpers — with correct expression syntax.
tags: n8n, code, javascript, python
input: What the node must do, sample input items, and the exact output shape you need.
---
Invoke the `n8n-code-javascript` skill (Skill tool) first (or `n8n-code-python` only if I ask for Python), plus `n8n-expression-syntax`. JavaScript is the default.

Write the node described below: correct mode (run once for all items vs per item), proper `[{ json: {...} }]` return shape, pairedItem where needed, and no silent drops. Show the code with a short comment on each non-obvious line, and give me 2–3 sample inputs with the expected output so I can test it on pinned data. Don't publish anything.
