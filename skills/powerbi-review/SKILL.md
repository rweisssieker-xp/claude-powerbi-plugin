---
name: powerbi-review
description: "Runs a complete offline review of a Power BI model or report (PBIX, PBIP, TMDL, model.bim, DAX, or Power Query exports; a folder of PBIX files becomes a portfolio review): structure, model summary, DAX and Power Query risks, KPI catalog, best practices, dependency impact, KPI trust, and an offline release gate, then reports the top risks and next fixes. Use when someone types /powerbi-review or asks to \"review this Power BI model\" or \"prüf mein Power-BI-Modell\"."
argument-hint: "<.pbix file, folder of .pbix files, PBIP project, or model folder>"
disable-model-invocation: true
---

# Power BI Review

> **Plugin folder:** this skill sits in `<plugin>/skills/powerbi-review/`. Commands below use `$PLUGIN_ROOT`: the plugin folder two levels above this skill's folder. Set it at the start of every shell command, for example `PLUGIN_ROOT="$(cd "<this skill's folder>/../.." && pwd)"; python3 -I "$PLUGIN_ROOT/scripts/python/pbi_toolkit.py" …`. Paths like `$PLUGIN_ROOT/skills/powerbi-desktop/references/running-scripts.md` are files inside the plugin.

1. **Locate the model.** Use the path from the arguments. Otherwise look in the connected folders for `*.pbix`, `*.pbip`, `*.SemanticModel`, `definition/*.tmdl`, `model.bim`, `*.dax`, or `*.pq`. For `.pbix`/`.pbit` files, make sure the optional reader is installed (`python3 -c "import pbixray"`, otherwise `pip install --break-system-packages pbixray`) so the semantic model is reviewed and not just the report layer. Copy files from the user's computer into the workspace first if needed.
2. **Run the review** into a new output folder next to the model (for example `<model>/../powerbi-review-YYYYMMDD`):
   ```bash
   python3 -I "$PLUGIN_ROOT/scripts/python/pbi_toolkit.py" review "<model>" --out "<out>"
   ```
   When PowerShell 7 is available, also run `Invoke-PowerBIUnifiedReview.ps1 -Path <model> -OutputDirectory <out>/powershell -SkipLive` for the full script pack (see `$PLUGIN_ROOT/skills/powerbi-desktop/references/running-scripts.md`).
3. **Read** `index.md`, `powerbi-insight-scan.json`, `powerbi-kpi-trust.json`, `powerbi-model-summary.json` (includes report pages, visuals, storage), and `powerbi-dependency-graph.json`. For a portfolio, start with the comparison table in `index.md`, then open each file's sub-folder. Open individual findings in the model files to confirm them before reporting; drop or downgrade any that do not hold.
4. **Report** in the user's language:
   - one-line verdict (offline gate decision, risk level, KPI trust score)
   - top 5 risks, each with file/measure, why it matters, and the concrete fix (show corrected DAX/M where short)
   - which KPIs are safe to use now and which are not
   - most-depended-on measures (change carefully)
   - for PBIX files: report-layer findings (broken visual fields, unused measures, custom visuals) and the hint that changes should be made in a PBIP export (File > Save as > Power BI project)
   - next step: offer `/powerbi-kpi-trust`, `/powerbi-release-gate`, safe PBIP drafts via `powerbi-desktop`, or a live check with `/powerbi-live-desktop`
5. Label the evidence as `local (python direct file analysis)` and state that live validation was not run.

Never edit model files in this command. Fixes are proposals until the user approves a change.
