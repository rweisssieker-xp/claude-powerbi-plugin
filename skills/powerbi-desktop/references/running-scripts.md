# Running The Plugin Tools

> **Plugin folder:** `$PLUGIN_ROOT` below is the plugin folder, three levels above this file (`<plugin>/skills/powerbi-desktop/references/`). Set it at the start of every shell command: `PLUGIN_ROOT="$(cd "<folder of this file>/../../.." && pwd)"`.

Everything ships under `$PLUGIN_ROOT`: PowerShell scripts in `scripts/`, Python tools in `scripts/python/` and `scripts/support/`, rules in `rules/`, templates in `templates/`, fixtures in `examples/`, reference docs in `docs/` (start with `docs/script-catalog.md`). Never assume the user's working directory contains them. Write outputs into a folder the user can see, never into the plugin directory.

Pick the first route that works, and say in the result which route produced the evidence.

## Route 1: Python toolkit (always available, no setup)

Standard library only. Handles real PBIP/TMDL exports, `model.bim`, simplified `.dax`, and `.pq` files, using the same rule files and schema names as the PowerShell scripts. Report definitions (PBIR `definition/pages/**/visual.json` and legacy `Report/Layout`) are checked too: broken field references, unused measures, embedded custom visuals, empty or overloaded pages.

**PBIX/PBIT files:** the report layer is read with the standard library. For the semantic model (measures, calculated columns, relationships, Power Query, RLS, VertiPaq statistics), install the optional package once: `pip install --break-system-packages pbixray` (MIT, reads the compressed DataModel; no Power BI Desktop needed). Without it, the review still runs on the report layer and says what is missing. A folder with several `.pbix` files gets a portfolio review: one sub-folder per file plus a comparison table in `index.md`.

```bash
T="$PLUGIN_ROOT/scripts/python/pbi_toolkit.py"
python3 -I "$T" review   <model-folder|file.pbix|folder-of-pbix> --out <output-folder>   # everything below plus index.md
python3 -I "$T" scan     <model-folder> [--json] [--out file]    # Invoke-PowerBIInsightScan.ps1
python3 -I "$T" summary  <model-folder>                          # New-PowerBIModelSummary.ps1
python3 -I "$T" catalog  <model-folder>                          # New-PowerBIMetricCatalog.ps1
python3 -I "$T" trust    <model-folder>                          # New-PowerBIKpiTrustScore.ps1
python3 -I "$T" gate     <model-folder>                          # offline New-PowerBITrustReleaseGate.ps1
python3 -I "$T" dependencies <model-folder>                      # measure impact graph (Mermaid)
python3 -I "$T" structure | best-practices | inventory <model-folder>
```

Model wizard (counterpart of `New-PowerBIModelWizard.ps1`, plus type inference, key/relationship detection, source-specific Power Query, and TMDL drafts):

```bash
python3 -I "$PLUGIN_ROOT/scripts/python/pbi_model_wizard.py" --project-name <Name> --output-directory <out> \
  --business-purpose "<decision>" --source <file.csv> --source <file.json> \
  [--source-config "$PLUGIN_ROOT/templates/powerbi-data-sources.example.json"] [--fact X] [--dimension Y] [--kpi Z] --initialize
```

AI forecast engine:

```bash
python3 "$PLUGIN_ROOT/scripts/support/powerbi_ai_forecast.py" --input <rows.json> --output-directory <out> \
  --as-of-date YYYY-MM-DD --forecast-year 2026 --start-month 5 --end-month 12 --horizon-months 3 [--grain <grain>] [--backtest]
```

Input format: `$PLUGIN_ROOT/examples/ai-forecast/segment-monthly.json`. Run it without `-I`: the worker imports its helper modules from `scripts/support/`. Outputs (semicolon CSV): `ai-forecast-summary.csv`, `-detail`, `-top-deltas`, `-backtest`, `-model-quality`.

Label Python results `local (python direct file analysis)`. The Python gate is an approximation: say so whenever you report it.

**Changing a PBIP project:** `python3 -I "$PLUGIN_ROOT/scripts/python/pbi_apply.py" <command> <PBIP> …` writes measures, columns, tables, relationships, roles and Power Query expressions into TMDL. Dry run by default; `--apply` only after the user approved the change; `undo` restores the zip backup. See `authoring.md`.

## Route 2: PowerShell 7 in the workspace

Use this for any of the ~200 scripts without a Python counterpart (release candidate pack, Fabric snapshot packs, semantic test runner, guided fixes, drafts and apply plans, executive packs).

1. Check `command -v pwsh`.
2. If it is missing, ask the user once whether you may install PowerShell 7 into the workspace. After they agree, follow Microsoft's official instructions for installing PowerShell on Linux (https://learn.microsoft.com/powershell/scripting/install/install-other-linux), using the binary archive from the official releases page (https://github.com/PowerShell/PowerShell/releases).
3. Run: `pwsh -NoProfile -File "$PLUGIN_ROOT/scripts/<Script>.ps1" -Path <model-folder> -OutputDirectory <out>`.

All offline scripts and the full self-test (`tests/Run-PowerBITests.ps1 -SkipPester`) pass on Linux. Pester itself is not installable in the workspace.

## Route 3: Power BI Desktop on the user's Windows computer

Live Desktop and Windows-only steps need the user's machine:

- Live model: `*Live*` scripts, `Get-PowerBIDesktopLiveConnection.ps1`, `Resolve-PowerBILiveTarget.ps1`, `Invoke-PowerBILiveDaxQuery.ps1`, `Get-PowerBILiveVertiPaqAnalyzer.ps1`
- External Tools menu: `Install-PowerBIExternalTool.ps1`, `Uninstall-PowerBIExternalTool.ps1`, `New-PowerBIExternalToolRegistration.ps1`
- Live Fabric (GET-only, token file): `Invoke-PowerBIFabricReadOnly*.ps1`
- Pester tests: `tests/Run-PowerBITests.ps1`

The scripts need a local copy of the plugin on Windows (for example `C:\temp\ClaudeWork\PowerbiPlugin\powerbi-desktop`). Ask where it is if unknown.

Simplest path: the user double-clicks `scripts\Run-PowerBILiveReview.cmd` in that copy while a model is open in Power BI Desktop. It runs environment check, target detection, live auto review, VertiPaq analysis, and metadata governance read-only and writes to `%USERPROFILE%\Documents\PowerBI-Live-Review` (or the folder given as first argument). If several files are open in Power BI Desktop, every open model is reviewed into its own sub-folder (named after the window title) with an `index.md`; a second argument picks one model by title, for example `Run-PowerBILiveReview.cmd C:\out Finoryx`. Works with Windows PowerShell 5.1 and PowerShell 7, the classic installer and the Microsoft Store edition.

Tested behavior (Store edition 2.159, Windows 11): the endpoint is found through `msmdsrv.port.txt` (UTF-16) plus a TCP connect probe, and the ADOMD client is loaded from Power BI Desktop's own `bin\Microsoft.PowerBI.AdomdClient.dll`. Newer SSMS builds ship a modern-.NET ADOMD client that Windows PowerShell 5.1 cannot load; the scripts skip it automatically.

1. **Command for the user (default):** give the exact Windows PowerShell command, with `-OutputDirectory` pointing into a folder connected to this conversation. Example:
   ```powershell
   cd C:\temp\ClaudeWork\PowerbiPlugin\powerbi-desktop
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Invoke-PowerBILiveAutoReview.ps1 -OutputDirectory C:\temp\ClaudeWork\PowerbiPlugin\out\live-review
   ```
   Then read the outputs from the connected folder and continue.
2. **Computer use (only if available and the user agrees):** open Windows PowerShell on their computer, run the same command, and read the outputs from the connected folder. Never type credentials or tokens. Never run `Apply-*` or `Install-*` scripts without explicit approval of that exact step.

Prefer exported Fabric snapshots (`examples/fabric-snapshot/*` shows the format) over live access.

## Safety

- Never modify PBIX/PBIT binaries.
- `Apply-*` scripts change PBIP/TMDL files. Show the change, its dependencies, and the rollback first, and run them only after the user explicitly agrees.
- Do not publish, sign in, refresh credentials, or change Power BI/Fabric content without explicit authorization.
- Label evidence as local, live, snapshot, heuristic, or draft.
