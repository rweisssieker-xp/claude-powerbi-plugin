---
name: powerbi-fabric-nextgen-usps
description: "Produces Power BI and Fabric next-generation evidence: Fabric FinOps, Copilot answer regression tests, Direct Lake/OneLake readiness, data-product SLOs, capacity change proof, and executive decision traces. Use when someone asks about \"Fabric FinOps\", \"Direct Lake readiness\", \"Copilot regression\", \"Capacity-Kosten\", or \"data product SLOs\"."
disable-model-invocation: true
---

# Power BI And Fabric Next-Generation USPs

> **Plugin folder:** this skill sits in `<plugin>/skills/powerbi-fabric-nextgen-usps/`. Commands below use `$PLUGIN_ROOT`: the plugin folder two levels above this skill's folder. Set it at the start of every shell command, for example `PLUGIN_ROOT="$(cd "<this skill's folder>/../.." && pwd)"; python3 -I "$PLUGIN_ROOT/scripts/python/pbi_toolkit.py" …`. Paths like `$PLUGIN_ROOT/skills/powerbi-desktop/references/running-scripts.md` are files inside the plugin.

Run the local pack first:

```powershell
pwsh -NoProfile -File "$PLUGIN_ROOT/scripts/Invoke-PowerBINextGenUspPack.ps1" -Path .\your-model -OutputDirectory .\powerbi-nextgen-usp-pack
```

It produces six machine-readable artifacts: Fabric FinOps Copilot, Copilot Answer Regression Lab, Direct Lake/OneLake Readiness, Data Product SLO Manager, Capacity Change Verifier, and Executive Decision Trace.

- Treat FinOps, Direct Lake, and decision outputs as decision support unless live/snapshot evidence is attached.
- The Copilot lab creates test cases; it does not claim a Copilot answer was validated until an approved answer capture is supplied.
- Capacity savings require before/after Capacity Metrics or CU evidence.
- Never access Fabric with a token or change service state unless the user explicitly requests it.

Scripts and templates named here live under `$PLUGIN_ROOT/scripts/` and `$PLUGIN_ROOT/templates/`. Before running one, read `$PLUGIN_ROOT/skills/powerbi-desktop/references/running-scripts.md`.
