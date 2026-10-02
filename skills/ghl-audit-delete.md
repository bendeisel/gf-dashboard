---
title: GHL audit / cleanup
category: GoHighLevel
description: List what exists in an account (workflows, calendars, forms) and prepare a cleanup plan.
tags: ghl, audit, cleanup
input: Which GHL profile/location should be audited, and what counts as junk?
---
Use the gohighlevel-cli skill (folder in $GHL_CLI_DIR). Do a READ-ONLY audit of the account I name: workflows, calendars, forms, funnels, smart lists, tags. Produce a table of what exists, flag duplicates and test leftovers, and propose a cleanup list. Do not delete or change anything. Note which items the CLI cannot delete (e.g. workflows) so I can remove them by hand.
