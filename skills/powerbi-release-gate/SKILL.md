---
name: powerbi-release-gate
description: "Decides Go, Warn, or No-Go for releasing a Power BI model or report, with blocking reasons, caveats, rollback readiness, and a release note. Use when someone types /powerbi-release-gate or asks \"can we release this report\", \"Release-Freigabe\", or \"Go/No-Go for this model\"."
argument-hint: "<model folder or .pbip> [git base ref, e.g. last release tag]"
disable-model-invocation: true
---

# Release Gate

> **Plugin folder:** this skill sits in `<plugin>/skills/powerbi-release-gate/`. Commands below use `$PLUGIN_ROOT`: the plugin folder two levels above this skill's folder. Set it at the start of every shell command, for example `PLUGIN_ROOT="$(cd "<this skill's folder>/../.." && pwd)"; python3 -I "$PLUGIN_ROOT/scripts/python/pbi_toolkit.py" …`. Paths like `$PLUGIN_ROOT/skills/powerbi-desktop/references/running-scripts.md` are files inside the plugin.

1. Locate the model. If the model sits in a git repository, use the last release tag or commit as the base ref for change impact.
2. **Full gate (preferred, needs PowerShell 7):**
   ```bash
   pwsh -NoProfile -File "$PLUGIN_ROOT/scripts/New-PowerBIReleaseCandidatePack.ps1" -Path "<model>" -OutputDirectory "<out>/release-candidate"
   ```
   Add `-IncludeAnalyticalQa` for KPI/methodology changes. Add `-IncludeAdvancedUspQa` for evidence graphs, contracts, RLS, freshness, and UX risk. Run `Invoke-PowerBISemanticTestRunner.ps1` first when semantic expectations exist. For change impact against the last release, run `New-PowerBIPBIPChangeImpactGate.ps1 -Path <repo> -BaseRef <tag-or-commit> -HeadRef HEAD`. For rollback readiness, run `Test-PowerBIPBIPRollbackReadiness.ps1 -PbipPath <project.pbip>`.
3. **Offline gate (no PowerShell):**
   ```bash
   python3 -I "$PLUGIN_ROOT/scripts/python/pbi_toolkit.py" review "<model>" --out "<out>"
   ```
   Use `powerbi-release-gate.json`, and state that it approximates the PowerShell gate (no guided fix plan, Copilot readiness, or semantic test run).
4. **Report:**
   - decision in one word, then the release note
   - blocking checks with the exact measure/file and the fix
   - warnings that need a documented caveat or waiver, and who should sign off
   - what was not verified (live values, semantic tests, RLS against real users)
   - rollback: the previous PBIP version in source control, or that none was found
5. Treat the gate as decision support, never as business sign-off. Never publish or deploy.
