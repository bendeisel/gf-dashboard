---
title: n8n: AI agent workflow
category: Automation
description: Design or fix an n8n AI Agent / LLM chain — model, memory, tools, structured output, RAG, human-in-the-loop — the right way.
tags: n8n, ai-agent, llm, automation
input: What the agent should do, which channel it lives on (SMS/GHL, chat, email), and the tools/data it needs.
---
Invoke the `n8n-agents` skill (Skill tool) first; also load `n8n-code-tool` if the agent needs a custom code tool, and `using-n8n-mcp-skills` for the build/validate loop.

Design the agent described below: choose agent vs chain vs classifier deliberately, write the system prompt and tool descriptions as the prompt they are, define memory/session handling, and use structured output with a parser where the result feeds another node. Keep it UNPUBLISHED until I review; never test against live contacts. Confirm the plan in bullets, then build and validate.
