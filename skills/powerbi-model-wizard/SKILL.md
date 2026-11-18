---
name: powerbi-model-wizard
description: "Designs a new Power BI model from a business goal and data sources (local CSV/JSON or any Power BI connector): star schema, KPI drafts, RLS plan, Power Query drafts, and report pages, delivered as PBIP/TMDL drafts. Use when someone says \"build a Power BI model\", \"new semantic model from these files\", \"baue ein Power-BI-Modell\", \"Datenmodell aus diesen Quellen\", or \"star schema for\"."
---

# Power BI Model Wizard

> **Plugin folder:** this skill sits in `<plugin>/skills/powerbi-model-wizard/`. Commands below use `$PLUGIN_ROOT`: the plugin folder two levels above this skill's folder. Set it at the start of every shell command, for example `PLUGIN_ROOT="$(cd "<this skill's folder>/../.." && pwd)"; python3 -I "$PLUGIN_ROOT/scripts/python/pbi_toolkit.py" …`. Paths like `$PLUGIN_ROOT/skills/powerbi-desktop/references/running-scripts.md` are files inside the plugin.

Create a local design pack for a new Power BI model from local files (CSV, JSON) or any Power BI Desktop connector. It proposes facts, dimensions, relationships, base KPIs, Power Query sources, and report pages. It never creates PBIX/PBIT binaries, stores credentials, or publishes.

1. **Gather** the business decision the model supports and the sources: local CSV/JSON paths, and/or a connector declaration file based on `$PLUGIN_ROOT/templates/powerbi-data-sources.example.json` (exact connector name from Power BI Desktop > Get Data, non-secret connection alias, columns if known). Ask only for domain rules that cannot be inferred, such as KPI ownership, fact grain, or RLS roles.
2. **Generate the drafts** (Python, works everywhere):
   ```bash
   python3 -I "$PLUGIN_ROOT/scripts/python/pbi_model_wizard.py" --project-name <Name> --output-directory <out> \
     --business-purpose "<decision>" --source <a.csv> --source <b.json> [--source-config <sources.json>] \
     [--fact FactX] [--dimension DimY] [--kpi "<KPI>"] --initialize
   ```
   It infers column types, keys, and fact-to-dimension relationships, writes source-specific Power Query (CSV with the detected delimiter, JSON, or a connector placeholder), and writes TMDL drafts under `model-drafts/tmdl/` with base DAX (SUM, COUNTROWS, prior year, YoY via DIVIDE). `New-PowerBIModelWizard.ps1` produces the same contract when PowerShell is preferred.
3. **Review with the user:** fact/dimension split, inferred relationships (confidence), KPI drafts, and every TODO (owner, description). Adjust with `--fact`, `--dimension`, or `--kpi` and regenerate into a new folder.
4. **Build in Power BI Desktop:** the user creates the PBIP project and the sources (credentials only in Desktop). Then copy the reviewed TMDL tables, measures, and relationships into the PBIP `definition/` folder. Copying into a real project is an apply step and needs the user's explicit approval for each file.
5. **Validate:** run `python3 -I "$PLUGIN_ROOT/scripts/python/pbi_toolkit.py" review <pbip-folder> --out <out>` (or `Invoke-PowerBIUnifiedReview.ps1`), then open the project in Power BI Desktop.

State clearly that the generated content is a draft until it has been reviewed and validated in Power BI Desktop.
