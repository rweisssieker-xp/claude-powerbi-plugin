---
name: powerbi-kpi-trust
description: "Explains whether the KPIs in a Power BI model can be trusted for a decision: definition, owner, DAX risks, dependencies, trust score per KPI, and an executive trust brief with what to fix first. Use when someone types /powerbi-kpi-trust or asks \"can I trust this KPI\", \"kann ich dieser Kennzahl trauen\", or \"KPI-Katalog erstellen\"."
argument-hint: "<model folder> [KPI name]"
disable-model-invocation: true
---

# KPI Trust Brief

> **Plugin folder:** this skill sits in `<plugin>/skills/powerbi-kpi-trust/`. Commands below use `$PLUGIN_ROOT`: the plugin folder two levels above this skill's folder. Set it at the start of every shell command, for example `PLUGIN_ROOT="$(cd "<this skill's folder>/../.." && pwd)"; python3 -I "$PLUGIN_ROOT/scripts/python/pbi_toolkit.py" …`. Paths like `$PLUGIN_ROOT/skills/powerbi-desktop/references/running-scripts.md` are files inside the plugin.

1. Locate the model (arguments, or search the connected folders as in `/powerbi-review`).
2. Run:
   ```bash
   T="$PLUGIN_ROOT/scripts/python/pbi_toolkit.py"
   python3 -I "$T" catalog "<model>" --json --out "<out>/metric-catalog.json"
   python3 -I "$T" trust "<model>" --json --out "<out>/kpi-trust.json"
   python3 -I "$T" dependencies "<model>" --json --out "<out>/dependencies.json"
   ```
3. If a KPI name was given, focus on it and its upstream measures; otherwise cover all KPIs, lowest trust first.
4. For each KPI, read the DAX yourself and state in plain language:
   - what it calculates (grain, filters, time logic) and whether the name matches the logic
   - owner and business definition (from TMDL `///` descriptions and `annotation Owner`), or that they are missing
   - risks (FILTER over ALL, TODAY/NOW, USERELATIONSHIP, `/` without DIVIDE, long logic) and what each means for a decision-maker
   - trust score and band (High ≥ 80, Medium 60-79, Low < 60) with the deductions
   - a reconciliation question to check against the source system
5. Write `<out>/kpi-trust-brief.md` with: an executive summary (3 sentences), a KPI table (KPI, trust, use for decisions yes/with caveat/no, main reason), and a fix list ordered by impact (owner/definition gaps can be fixed as TMDL `///` descriptions and `annotation Owner = …`; offer to draft them).
6. Offer the deeper scripts when PowerShell is available: `New-PowerBIExecutiveTrustBrief.ps1`, `New-PowerBIKpiTrustContract.ps1`, `New-PowerBIKpiOwnerSignoffWorkflow.ps1`.

Never present a KPI as trustworthy without saying that live values were not reconciled.
