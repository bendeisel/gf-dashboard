---
title: KPI dashboard design
category: Reporting
description: Design a metrics dashboard — which KPIs, how to visualize them, layout and real-time patterns — or debug a dashboard whose numbers contradict each other.
tags: kpi, dashboard, metrics, analytics
input: Who the dashboard is for, what decisions it supports, and the data sources (GHL, OpenSEO, GA, n8n…).
---
Invoke the `kpi-dashboard-design` skill (Skill tool) first (and `dataviz` for the chart/colour rules if it's available).

Design the dashboard described below: choose a small set of KPIs tied to the decisions the viewer makes, define how each is calculated (one methodology per metric, written down), pick the right visual for each, and lay it out by priority. If this is for our command dashboard or a client report page, output working HTML/CSS matching the Growth Factor brand (load `gf-brand`). Start by listing the proposed KPIs with one line on why each earns its place.
