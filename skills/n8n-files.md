---
title: n8n: files & binary data
category: Automation
description: Handle files, images, PDFs and attachments correctly in n8n — $binary vs $json, keeping binary alive across Merge, agent file I/O.
tags: n8n, files, binary, pdf, attachments
input: Where the file comes from, what should happen to it, and where it goes (email, GHL, storage, an AI step).
---
Invoke the `n8n-binary-and-data` skill (Skill tool) first; use `using-n8n-mcp-skills` for the build/validate loop.

Build or fix the file-handling path described below: read/write binary correctly, keep it alive across transforms and Merge nodes, and respect the agent-tool boundary if an AI step needs the file. Validate with a small test file, never with real member documents. Keep it UNPUBLISHED until I review.
