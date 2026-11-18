---
name: powerbi-autonomous-planning-loop
description: "Runs a closed-loop Power BI planning cycle: observe actuals and backlog, forecast, detect gaps, simulate scenarios, decide, act, learn, and version the run, without touching PBIX files. Use when someone asks for an \"autonomous planning loop\", \"Planungszyklus\", \"rollierende Planung automatisieren\", or \"recurring forecast control cycle\"."
disable-model-invocation: true
---

# Power BI Autonomous Planning Loop

> **Plugin folder:** this skill sits in `<plugin>/skills/powerbi-autonomous-planning-loop/`. Commands below use `$PLUGIN_ROOT`: the plugin folder two levels above this skill's folder. Set it at the start of every shell command, for example `PLUGIN_ROOT="$(cd "<this skill's folder>/../.." && pwd)"; python3 -I "$PLUGIN_ROOT/scripts/python/pbi_toolkit.py" …`. Paths like `$PLUGIN_ROOT/skills/powerbi-desktop/references/running-scripts.md` are files inside the plugin.

Use this skill when the user wants planning to run as a recurring control cycle rather than a one-time forecast.

## Loop

1. **Observe**: load actuals, open backlog, forecast outputs, model quality, overrides, and action status.
2. **Forecast**: run or reuse `Invoke-PowerBIAIForecast.ps1` (live, Windows) or the Python worker described in `powerbi-forecast` (exported data).
3. **Detect**: identify gaps to budget, roll, prior year, and committed actions.
4. **Simulate**: create target, base, risk, and rescue scenarios.
5. **Decide**: classify items as trusted, challenge, rescue, de-risk, or advisory.
6. **Act**: create action records with owner hints, probability, impact, and due date.
7. **Learn**: compare outcomes to forecast and update trust, bias, and readiness signals.
8. **Repeat**: preserve a versioned run record for the next cycle.

## Required artifacts

- `planning-run-log.csv`
- `planning-gap-detection.csv`
- `planning-decisions.csv`
- `planning-learning-events.csv`

## Guardrails

- Keep every run immutable and timestamped.
- Never overwrite management numbers; store autonomous recommendations separately.
- Stop autonomous action recommendations when readiness is below threshold.

Scripts and templates named here live under `$PLUGIN_ROOT/scripts/` and `$PLUGIN_ROOT/templates/`. Before running one, read `$PLUGIN_ROOT/skills/powerbi-desktop/references/running-scripts.md`.
