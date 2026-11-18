# pbi-workbench: Power BI Workbench for Claude

Guided Power BI workflows from data sources to trusted decisions: model design, KPI trust, safe PBIP/TMDL changes, release gates, live Desktop review, AI forecasting, and Fabric operations. Ported from the author's Codex plugin `powerbi-desktop` 3.0.0 and extended for Claude.

PBIX/PBIT binaries are never modified. Live Desktop and Fabric access are read-only. Every result is labeled by its evidence: local, live, snapshot, heuristic, or draft.

## Install

**Claude Code:**

```
/plugin marketplace add rweisssieker-xp/claude-powerbi-plugin
/plugin install pbi-workbench@pbi-workbench
```

**Claude app (chat):** download [pbi-workbench.plugin](https://github.com/rweisssieker-xp/claude-powerbi-plugin/raw/dist/pbi-workbench.plugin) and open it in Claude to install.

## Quick start

| Command | What you get |
| --- | --- |
| `/powerbi-review <model or .pbix>` | Full offline review: risks with fixes, KPI catalog, trust scores, dependency impact, report checks, Go/Warn/No-Go. A folder of PBIX files becomes a portfolio comparison |
| `/powerbi-kpi-trust <model> [KPI]` | Can I trust this KPI? Trust brief per KPI plus a fix list |
| `/powerbi-release-gate <model>` | Release decision with blocking reasons, caveats, and rollback |
| `/powerbi-forecast <export>` | AI sales forecast with backtest, top deltas, model quality |
| `/powerbi-live-desktop [title]` | Read-only review of the models open in Power BI Desktop (Windows); several open files are reviewed one after another |
| `/powerbi-change <PBIP> <change>` | Writes a reviewed measure, column, table, relationship, RLS role or Power Query change into a PBIP project: dry run, approval, zip backup, undo |

Or just describe the goal ("build a Power BI model from these CSVs", "prüf mein Power-BI-Modell"). The `powerbi-desktop` skill routes to the right workflow.

## Skills

Load automatically when relevant:

- `powerbi-desktop`: entry point and router
- `powerbi-model-wizard`: new model from sources (star schema, relationships, Power Query, TMDL, base KPIs)

Slash commands: `powerbi-review`, `powerbi-kpi-trust`, `powerbi-release-gate`, `powerbi-forecast`, `powerbi-live-desktop`, `powerbi-change`

Planning skills (run only when called by name): `powerbi-forecast-war-room`, `powerbi-revenue-rescue-mode`, `powerbi-goal-seeking-planning`, `powerbi-autonomous-forecast-agents`, `powerbi-causal-counterfactual-forecasting`, `powerbi-constraint-aware-planning`, `powerbi-revenue-digital-twin`, `powerbi-autonomous-planning-loop`, `powerbi-autonomous-exception-management`, `powerbi-forecast-trust-market`, `powerbi-self-healing-forecast-governance`, `powerbi-planning-memory`, `powerbi-planning-readiness-score`, `powerbi-fabric-nextgen-usps`


## What this plugin runs, sends, and fetches

- **No hooks and no MCP servers.** Nothing runs on its own. Scripts run only when a skill tells Claude to run one, or when you start one yourself.
- **Python tools** (`scripts/python`, `scripts/support`) are standard-library only. They read the files you point them at and write reports to the output folder you choose. They make no network calls.
- **Optional package:** for the semantic model inside `.pbix` files, the review skills suggest `pip install pbixray` (MIT, from PyPI). Without it the review still runs on the report layer.
- **PowerShell scripts** (`scripts/*.ps1`) read local files. The live scripts connect read-only to the local Analysis Services instance that Power BI Desktop opens on `localhost`. They never refresh, change or publish the model.
- **PBIP changes** (`/powerbi-change`, `pbi_apply.py`, `Apply-*.ps1`) write TMDL files only in the project you name, only with an explicit apply flag, with a zip backup in `<project>/.pbip-apply/`. PBIX files are never written.
- **Fabric / Power BI Service:** the optional `Invoke-PowerBIFabricReadOnly*.ps1` scripts send GET requests to `https://api.powerbi.com/v1.0/myorg` with an access token that you put in a file and pass with `-AccessTokenPath`. Other HTTP methods are blocked. All other Fabric features work on snapshot JSON files you export yourself.
- **External Tools registration** (`Install-PowerBIExternalTool.ps1`) writes one `.pbitool.json` file to the Power BI Desktop External Tools folder when you run it as administrator; `Uninstall-PowerBIExternalTool.ps1` removes it.
- No telemetry. No data is sent anywhere else.

Power BI, Power BI Desktop and Microsoft Fabric are trademarks of Microsoft. This plugin is an independent community project and is not affiliated with or endorsed by Microsoft.

## Three ways the tools run

1. **Python toolkit** (`scripts/python/`, no setup; for PBIX models add `pip install pbixray`): `pbi_toolkit.py` (inventory, structure, summary, scan, catalog, best-practices, dependencies, trust, gate, review) and `pbi_model_wizard.py`. Reads PBIX/PBIT files (report layer always, semantic model via the optional `pbixray` package), real PBIP/TMDL exports, `model.bim`, `.dax`, and `.pq`, and uses the same rule files and output schemas as the PowerShell scripts. On the bundled fixtures, risk scores, KPI trust scores, and gate decisions match the PowerShell results exactly.
2. **PowerShell 7** (`scripts/*.ps1`, about 230 scripts): the full catalog, also on Linux. Claude asks before installing PowerShell into its workspace.
3. **Your Windows computer** for live Power BI Desktop, External Tools, and live Fabric. Double-click `scripts\Run-PowerBILiveReview.cmd` with a model open, let Claude give you the exact command, or let Claude run it with computer use. Verified with the Microsoft Store edition of Power BI Desktop 2.159 and Windows PowerShell 5.1.

Details: `skills/powerbi-desktop/references/running-scripts.md`. Script reference: `docs/script-catalog.md`.

## Install on Windows for live use

Copy this plugin folder to your computer (for example `C:\temp\ClaudeWork\PowerbiPlugin\pbi-workbench`). To add the review to the Power BI Desktop *External Tools* ribbon, run this in a PowerShell window opened **as administrator** (it writes to `%CommonProgramFiles%\Microsoft Shared\Power BI Desktop\External Tools`):

```powershell
cd C:\temp\ClaudeWork\PowerbiPlugin\pbi-workbench
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install-PowerBIExternalTool.ps1
```

Then restart Power BI Desktop and choose *Claude Power BI Workbench* under External Tools.

## Tests

```bash
python3 -I tests/python/test_pbi_toolkit.py          # 20 tests: TMDL/PBIR/PBIX parsing, parity, wizard, trust, gate, portfolio
python3 test_powerbi_ai_forecast.py                   # forecast engine
pwsh -File tests/Run-PowerBITests.ps1 -SkipPester     # 78-check smoke suite + golden baselines
pwsh -File tests/Run-PowerBITests.ps1                 # incl. Pester (Windows / Pester 5 installed)
```

## 3.2.0: tested on real PBIX files

Tested on 8 PBIX reports (PBIR format, 1 to 11 pages, up to 33 visuals, 0 to 7 measures, custom visuals) offline and live in Power BI Desktop.

- **PBIX review without Power BI Desktop:** report pages, visuals, field usage, custom visuals; semantic model via `pbixray`. Live results for the same file matched exactly (tables, columns, measures, DAX, dependencies).
- **Portfolio review** of a folder of PBIX files with a comparison table.
- **New report checks:** visual references a missing field, measures unused in the report, custom visuals embedded from file, empty/dense pages, tables without relationships, column memory hotspots.
- **Live fixes (all verified on Windows):**
  - Endpoint detection failed on Windows builds where `Get-NetTCPConnection` reports the Analysis Services socket without state. Now uses a TCP connect probe.
  - ADOMD: the SSMS 22 client (modern .NET) cannot load in Windows PowerShell 5.1. Now Power BI Desktop's own `Microsoft.PowerBI.AdomdClient.dll` is preferred, and candidates are tried until one loads.
  - `Test-PowerBILiveMeasures.ps1` always reported empty values (`PSObject.Properties[0]` indexes by name in PowerShell). Fixed; values now come through.
  - `Get-PowerBILiveVertiPaqAnalyzer.ps1` only counted metadata rows and ignored `-OutputPath` without `-Json`. It now reports dictionary and data size per column and table.
  - `Test-PowerBIEnvironment.ps1` did not find the Microsoft Store edition. Detected via the package manager now.
- **Fixed false positives:** filter aliases (`"Source": "f"`) are resolved; "no date table" only fires when time intelligence is used; KPI trust shows `n/a` instead of 0 when a model has no measures.
- New `scripts/Run-PowerBILiveReview.cmd` launcher.

## What changed from the Codex version (3.0.0 → 3.1.0)

New:

- Python toolkit and Python model wizard (work without PowerShell)
- Five slash-command workflows: review, KPI trust, release gate, forecast, live Desktop
- Real-world fixture `examples/pbip-tmdl-model` (PBIP with TMDL, relationships, RLS, auto date table) and `examples/model-wizard-sources`
- `templates/powerbi-data-sources.example.json` and the `docs/` folder from the GitHub repository
- German and English trigger phrases in every skill description

Fixed:

- **TMDL measures were not detected.** `Invoke-PowerBIInsightScan.ps1`, `New-PowerBIMetricCatalog.ps1`, and `New-PowerBIModelSummary.ps1` only parsed the simplified `'Table'[Measure] =` format. Real PBIP exports (`measure 'Name' = …`) returned 0 measures. They are now parsed, and the fixture model goes from 0 to 6 measures.
- `Resolve-PowerBILiveTarget.ps1` crashed on non-Windows hosts (`Get-CimInstance`, `Get-NetTCPConnection`, `$env:LOCALAPPDATA`). It now reports *NoLiveTarget* instead.
- The model wizard wrote every Power Query draft as `Csv.Document`, even for JSON files and connectors. The Python wizard writes the matching source type.

Adapted:

- Manifest moved to `.claude-plugin/plugin.json`. `openai.yaml` became `disable-model-invocation`. Skills address bundled files through `$PLUGIN_ROOT` (two levels above the skill folder), because `${CLAUDE_PLUGIN_ROOT}` is only substituted in hooks and MCP configs.
- External Tool renamed to *Claude Power BI Workbench*. The stale `external-tools/*.pbitool.json` with a hard-coded `D:\` path was removed; `New-PowerBIExternalToolRegistration.ps1` regenerates it.
- Output schema names (`codex.powerbi.*`) are kept unchanged so existing outputs and dashboards stay compatible.

## License

MIT. Author: Reiner Weisssieker.
