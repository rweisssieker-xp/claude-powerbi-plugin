---
name: powerbi-desktop
description: "Entry point and router for Power BI Desktop work: building models from data sources, trusting KPIs, reviewing or changing PBIP/TMDL/DAX/Power Query safely, release gates, Fabric operations, and decision governance. Use when someone says \"Power BI\", \"PBIP\", \"PBIX\", \"DAX\", \"Power Query\", \"semantic model\", \"Fabric\", \"was kann das Power-BI-Plugin\", \"prüf mein Power-BI-Modell\", \"kann ich diesem Bericht trauen\", or \"what can you do with Power BI\"."
---

# Power BI Index

> **Plugin folder:** this skill sits in `<plugin>/skills/powerbi-desktop/`. Commands below use `$PLUGIN_ROOT`: the plugin folder two levels above this skill's folder. Set it at the start of every shell command, for example `PLUGIN_ROOT="$(cd "<this skill's folder>/../.." && pwd)"; python3 -I "$PLUGIN_ROOT/scripts/python/pbi_toolkit.py" …`. Paths like `$PLUGIN_ROOT/skills/powerbi-desktop/references/running-scripts.md` are files inside the plugin.

This is the routing skill for the Power BI plugin. Do not enumerate scripts or load specialist workflows until the user's outcome is clear.

For "what can you do?", "help me get started", or broad orientation, read [orientation response](references/orientation-response.md) and return its user-facing content.

## Product Paths

| User outcome | Workflow | Result |
| --- | --- | --- |
| Build a model from data sources | `powerbi-model-wizard` | star schema, Power Query, TMDL and KPI drafts |
| Review a model end to end | `powerbi-review` (/powerbi-review) | risks, fixes, KPI trust, offline gate |
| Understand or trust KPIs | `powerbi-kpi-trust` (/powerbi-kpi-trust) | definitions, caveats, trust scores, executive brief |
| Change a PBIP/TMDL model | `references/authoring.md` | impact, tests, safe drafts, explicit apply |
| Release with confidence | `powerbi-release-gate` (/powerbi-release-gate) | Go/Warn/No-Go and rollback evidence |
| Check the model open in Power BI Desktop | `powerbi-live-desktop` (/powerbi-live-desktop) | live read-only review on Windows |
| Forecast and plan revenue | `powerbi-forecast` (/powerbi-forecast), then the planning skills | forecast, gaps, actions |
| Operate Fabric or a portfolio | `powerbi-fabric-nextgen-usps`, `references/release.md` | capacity, SLO, Direct Lake, governance evidence |
| Govern a decision or action | decision intelligence pack (`Invoke-PowerBIDecisionIntelligencePack.ps1`) | Copilot quality, decision memory, owner actions |

Planning skills (run only when named): `powerbi-forecast-war-room`, `powerbi-revenue-rescue-mode`, `powerbi-goal-seeking-planning`, `powerbi-autonomous-forecast-agents`, `powerbi-causal-counterfactual-forecasting`, `powerbi-constraint-aware-planning`, `powerbi-revenue-digital-twin`, `powerbi-autonomous-planning-loop`, `powerbi-autonomous-exception-management`, `powerbi-forecast-trust-market`, `powerbi-self-healing-forecast-governance`, `powerbi-planning-memory`, `powerbi-planning-readiness-score`.

When the user's outcome matches a workflow above, read that skill's `SKILL.md` in full from `$PLUGIN_ROOT/skills/<name>/SKILL.md` and follow it, even when it is a slash-command skill. Use only the minimum evidence needed, then offer a deeper path.

For any script not covered above, look it up in `$PLUGIN_ROOT/docs/script-catalog.md`.

## Running Scripts

Scripts, rules, templates, and examples ship with this plugin under `$PLUGIN_ROOT`. Before running anything, read [running scripts](references/running-scripts.md). It covers the three routes: the Python toolkit (always works, no setup), PowerShell 7 in the workspace (the full script catalog), and live Power BI Desktop steps on the user's Windows computer.

## Safety

- Never modify PBIX/PBIT binaries.
- Do not publish, sign in, refresh credentials, or change Power BI/Fabric content without explicit authorization.
- Label evidence as local, live, snapshot, heuristic, or draft.
