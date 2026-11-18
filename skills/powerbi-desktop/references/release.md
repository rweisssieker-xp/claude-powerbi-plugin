# Release Workflow

> **Plugin folder:** `$PLUGIN_ROOT` below is the plugin folder, three levels above this file (`<plugin>/skills/powerbi-desktop/references/`). Set it at the start of every shell command: `PLUGIN_ROOT="$(cd "<folder of this file>/../../.." && pwd)"`.

Start with `New-PowerBIReleaseCandidatePack.ps1 -Path .\your-model -OutputDirectory .\powerbi-release-candidate`.

- Add `-IncludeAnalyticalQa` when business methodology or KPI changes need a stakeholder-ready explanation.
- Add `-IncludeAdvancedUspQa` when evidence graphs, contract testing, RLS, freshness, or UX risk matter.
- Use Fabric snapshots for repeatable evidence. Live Fabric access is token-file and GET-only.
- Use `Invoke-PowerBISemanticTestRunner.ps1` before a release when semantic expectations are available.

Report a release gate as decision support, not a substitute for business-owner sign-off. Clearly separate live proof, snapshot evidence, local findings, and unresolved assumptions.

All scripts are in `$PLUGIN_ROOT/scripts/`. See [running scripts](running-scripts.md) for how to run them here.
